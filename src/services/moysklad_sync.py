import asyncio
import logging
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

  async def sync_stock(self, payload: dict):
    webhook = MoyskladStockWebhook.model_validate(payload)
    url = urlsplit(webhook.reportUrl)
    params = dict(parse_qsl(url.query))
    params.update(stockType='stock', include='zeroLines')
    stocks = await self.client.get('/report/stock/all/current', **params)
    if not isinstance(stocks, list):
      raise MoySkladImportError('Expected current stock report')
    quantities = {UUID(row['assortmentId']): row['stock'] for row in stocks}
    importer = MoySkladImportService(self.session)
    quantities = {key: importer._quantity(value) for key, value in quantities.items()}
    if not quantities:
      return
    offers = (await self.session.execute(
      select(Offer.id, ProductVariant.uuid).join(ProductVariant, ProductVariant.id == Offer.variant_id)
      .where(ProductVariant.uuid.in_(quantities)),
    )).all()
    if offers:
      await self.session.execute(update(Offer), [
        dict(id=offer.id, quantity=quantities[offer.uuid]) for offer in offers
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


async def process_sync_tasks(sessions=session_maker):
  async with sessions() as session:
    query = select(SyncTask.id, SyncTask.entity_type, SyncTask.entity_uuid, SyncTask.status, SyncTask.payload).where(
      SyncTask.entity_type.in_(SYNC_TYPES),
    ).order_by(SyncTask.updated, SyncTask.id).limit(5)
    tasks = (await session.execute(query.where(SyncTask.status == 'pending'))).all()
    if not tasks:
      tasks = (await session.execute(query.where(SyncTask.status == 'failed'))).all()
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


async def run_moysklad_sync():
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
      await process_sync_tasks()
    except Exception as exc:
      recovering = True
      logger.warning('MoySklad sync cycle failed (%s)', type(exc).__name__)
    await asyncio.sleep(settings.MOYSKLAD_SYNC_INTERVAL)
