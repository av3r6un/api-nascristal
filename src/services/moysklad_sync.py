import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy import select, update

from src.core.config import settings
from src.core.database import session_maker
from src.models import Offer, Product, ProductVariant
from src.models.sync import SyncTask
from src.schemas.moysklad_webhook import MoyskladStockWebhook
from src.services.moysklad_client import MoySkladClient, MoySkladError
from src.services.moysklad_import import MoySkladImportError, MoySkladImportService


logger = logging.getLogger('uvicorn.error')
CATALOG_TYPES = ('product', 'variant')
SYNC_TYPES = (*CATALOG_TYPES, 'stock')
MOSCOW = timezone(timedelta(hours=3))


def stock_report_expired(payload: dict) -> bool:
  try:
    changed_since = dict(parse_qsl(urlsplit(payload['reportUrl']).query))['changedSince']
    moment = datetime.fromisoformat(changed_since)
  except (KeyError, TypeError, ValueError):
    return False
  # MoySklad timestamps without an offset use Moscow time.
  if moment.tzinfo is None:
    moment = moment.replace(tzinfo=MOSCOW)
  return datetime.now(timezone.utc) - moment > timedelta(hours=24)


class MoySkladSyncService:
  def __init__(self, session, client):
    self.session = session
    self.client = client

  async def sync_entity(self, entity_type: str, entity_uuid: UUID):
    if entity_type not in CATALOG_TYPES:
      return
    try:
      data = await self.client.get(f'/entity/{entity_type}/{entity_uuid}')
    except MoySkladError as exc:
      if exc.status_code != 404:
        raise
      await self.archive_entity(entity_type, entity_uuid)
      return
    if not isinstance(data, dict) or UUID(data['id']) != entity_uuid:
      raise MoySkladImportError('Unexpected catalog entity response')
    if data.get('archived'):
      await self.archive_entity(entity_type, entity_uuid)
      return

    if entity_type == 'product':
      product = data
      variants = [row async for row in self.client.iter_entities(
        'variant', filter=f'productid={entity_uuid};archived=false',
      )]
    else:
      variants = [data]
      product_uuid = MoySkladImportService(self.session)._relation_uuid(data['product'], 'variant.product')
      product = await self.client.get(f'/entity/product/{product_uuid}')

    if variants:
      stocks = await self.client.get('/report/stock/all/current',
        stockType='stock', include='zeroLines',
        filter='assortmentId=' + ','.join(row['id'] for row in variants),
      )
      if not isinstance(stocks, list):
        raise MoySkladImportError('Expected current variant stock report')
      quantities = {row['assortmentId']: row['stock'] for row in stocks}
      for variant in variants:
        # The full report omits positions that have never participated in operations.
        variant['quantity'] = quantities.get(variant['id'], 0)
    await MoySkladImportService(self.session).sync_product(product, variants, complete=entity_type == 'product')

  async def sync_stock(self, payload: dict | None = None):
    params = dict(stockType='stock')
    if payload is None:
      params['include'] = 'zeroLines'
    else:
      webhook = MoyskladStockWebhook.model_validate(payload)
      if stock_report_expired(payload):
        raise MoySkladImportError('Stock report interval exceeds 24 hours')
      url = urlsplit(webhook.reportUrl)
      params['changedSince'] = dict(parse_qsl(url.query))['changedSince']
    stocks = await self.client.get('/report/stock/all/current', **params)
    if not isinstance(stocks, list):
      raise MoySkladImportError('Expected current stock report')
    quantities = {UUID(row['assortmentId']): row['stock'] for row in stocks}
    importer = MoySkladImportService(self.session)
    quantities = {key: importer._quantity(value) for key, value in quantities.items()}
    if not quantities and payload is not None:
      return
    query = select(Offer.id, ProductVariant.uuid).join(ProductVariant, ProductVariant.id == Offer.variant_id)
    if payload is not None:
      query = query.where(ProductVariant.uuid.in_(quantities))
    offers = (await self.session.execute(query)).all()
    if offers:
      await self.session.execute(update(Offer), [
        dict(id=offer.id, quantity=quantities.get(offer.uuid, 0)) for offer in offers
      ])

  async def archive_entity(self, entity_type: str, entity_uuid: UUID):
    if entity_type == 'product':
      product_ids = select(Product.id).where(Product.uuid == entity_uuid)
      condition = ProductVariant.product_id.in_(product_ids)
      await self.session.execute(update(Product).where(Product.uuid == entity_uuid).values(archived=True))
    else:
      condition = ProductVariant.uuid == entity_uuid
    variants = select(ProductVariant.id).where(condition)
    await self.session.execute(update(Offer).where(Offer.variant_id.in_(variants)).values(is_active=False))
    await self.session.execute(update(ProductVariant).where(condition).values(archived=True))


async def select_sync_tasks(session, status: str):
  query = select(SyncTask.id, SyncTask.entity_type, SyncTask.entity_uuid, SyncTask.status, SyncTask.payload, SyncTask.request_id).where(
    SyncTask.entity_type.in_(SYNC_TYPES), SyncTask.status == status,
  ).order_by(SyncTask.updated, SyncTask.id)
  tasks = []
  for task in (await session.execute(query)).all():
    if task.entity_type == 'stock' and stock_report_expired(task.payload):
      if status == 'pending':
        await session.execute(update(SyncTask).where(
          SyncTask.id == task.id, SyncTask.status == status, SyncTask.request_id == task.request_id,
        ).values(status='failed'))
      continue
    tasks.append(task)
    if len(tasks) == 5:
      break
  return tasks


async def process_sync_tasks(sessions=session_maker):
  async with sessions() as session:
    tasks = await select_sync_tasks(session, 'pending')
    if not tasks:
      tasks = await select_sync_tasks(session, 'failed')
    await session.commit()
  if not tasks:
    return
  async with MoySkladClient() as client:
    for task in tasks:
      async with sessions() as session:
        claimed = await session.execute(update(SyncTask).where(
          SyncTask.id == task.id, SyncTask.status == task.status,
        ).values(status='processing'))
        await session.commit()
        if not claimed.rowcount:
          continue
      try:
        async with sessions() as session:
          service = MoySkladSyncService(session, client)
          if task.entity_type == 'stock':
            await service.sync_stock(task.payload)
          else:
            await service.sync_entity(task.entity_type, task.entity_uuid)
          await session.execute(update(SyncTask).where(
            SyncTask.id == task.id, SyncTask.status == 'processing',
          ).values(status='synced'))
          await session.commit()
      except Exception as exc:
        async with sessions() as session:
          await session.execute(update(SyncTask).where(
            SyncTask.id == task.id, SyncTask.status == 'processing',
          ).values(status='failed'))
          await session.commit()
        detail = getattr(exc, 'orig', exc)
        logger.warning('MoySklad sync failed: entity_uuid=%s error=%s detail=%s',
          task.entity_uuid, type(exc).__name__, detail)


async def reconcile_stock(sessions=session_maker):
  async with MoySkladClient() as client, sessions() as session:
    await MoySkladSyncService(session, client).sync_stock()
    await session.commit()


async def run_moysklad_sync():
  now = datetime.now(MOSCOW)
  next_reconciliation = now.replace(hour=5, minute=0, second=0, microsecond=0)
  if now > next_reconciliation:
    next_reconciliation += timedelta(days=1)
  recovering = True
  while True:
    try:
      if recovering:
        async with session_maker() as session:
          await session.execute(update(SyncTask).where(
            SyncTask.status == 'processing', SyncTask.entity_type.in_(SYNC_TYPES),
          ).values(status='pending'))
          await session.commit()
        recovering = False
      now = datetime.now(MOSCOW)
      if now >= next_reconciliation:
        next_reconciliation = now.replace(hour=5, minute=0, second=0, microsecond=0) + timedelta(days=1)
        try:
          await reconcile_stock()
        except Exception as exc:
          logger.warning('MoySklad stock reconciliation failed: error=%s detail=%s',
            type(exc).__name__, getattr(exc, 'orig', exc))
      await process_sync_tasks()
    except Exception as exc:
      recovering = True
      logger.warning('MoySklad sync cycle failed (%s)', type(exc).__name__)
    await asyncio.sleep(settings.MOYSKLAD_SYNC_INTERVAL)
