"""Outbound customer orders. PurchaseSubmission stores only the remote identity."""
from decimal import Decimal
from uuid import UUID, NAMESPACE_URL, uuid5

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.exceptions import JSRError
from src.models import Purchase, PurchaseSubmission
from src.schemas.contact import normalize_contact_info
from src.services.moysklad_client import MoySkladClient, MoySkladError


def sync_uuid(purchase: Purchase) -> UUID:
  # A copied production database must not allow DEV to delete production orders.
  return uuid5(NAMESPACE_URL, f"https://nascrystal.ru/{settings.STAGE}/purchases/{purchase.uuid}")


def entity_ref(entity: str, entity_id: str | None) -> dict:
  try:
    normalized_id = str(UUID(str(entity_id)))
  except ValueError as exc:
    raise JSRError(status=503, message=f"MoySklad {entity} UUID is not configured correctly") from exc
  return {"meta": {
    "href": f"{MoySkladClient.BASE_URL}/entity/{entity}/{normalized_id}",
    "type": "state" if entity.endswith('/states') else entity,
    "mediaType": "application/json",
  }}


async def lock_purchase(session: AsyncSession, purchase_id: int) -> Purchase:
  # UPDATE also serializes writers on SQLite, where SELECT FOR UPDATE is ignored.
  result = await session.execute(
    update(Purchase).where(Purchase.id == purchase_id).values(id=Purchase.id)
    .execution_options(synchronize_session=False)
  )
  if result.rowcount != 1:
    raise JSRError("not_found", message=f"Purchase not found: {purchase_id}")
  return (await session.execute(
    select(Purchase).where(Purchase.id == purchase_id).execution_options(populate_existing=True)
  )).scalar_one()


def build_order_payload(purchase: Purchase, products_by_id: dict) -> dict:
  contact = normalize_contact_info(purchase.contact_info)
  delivery = contact['delivery']
  positions = []
  total = Decimal(0)
  for product_id in dict.fromkeys(purchase.product_ids):
    product = products_by_id.get(product_id)
    quantity = purchase.product_quantities.get(str(product_id), 0)
    if product is None or product.archived or not product.offer or not product.offer.is_active or quantity < 1:
      raise JSRError("bad_request", message=f"Product {product_id} is unavailable")
    price = Decimal(str(product.offer.amount)) * 100
    if price < 0 or price != price.to_integral_value():
      raise JSRError("bad_request", message=f"Invalid price for product {product_id}")
    positions.append({"quantity": quantity, "price": int(price), "assortment": entity_ref('variant', str(product.uuid))})
    total += price * quantity
  if delivery['cost'] < 0:
    raise JSRError("bad_request", message="Delivery cost cannot be negative")
  if delivery['cost'] < 0:
    raise JSRError("bad_request", message="Delivery cost cannot be negative")
  # Delivery is represented in the YooKassa receipt, not as a MoySklad item.
  if not positions or len(positions) > 1000 or total + Decimal(delivery['cost']) * 100 != Decimal(purchase.final_price) * 100:
    raise JSRError("bad_request", message="Order total does not match items and delivery")
  payload = {
    "externalCode": purchase.uuid,
    "syncId": str(sync_uuid(purchase)),
    "organization": entity_ref('organization', settings.MOYSKLAD_ORGANIZATION_ID),
    "agent": entity_ref('counterparty', settings.MOYSKLAD_COUNTERPARTY_ID),
    "positions": positions,
    "shipmentAddress": delivery['address'],
    "description": '\n'.join([
      'Источник: сайт nascrystal.ru',
      f'Среда: {settings.STAGE}',
      f'Номер заявки сайта: {purchase.id}',
      f'Статус сайта: {purchase.status.value}',
      *[f'{key}: {contact[key]}' for key in ('name', 'phone', 'email', 'username') if contact.get(key)],
    ]),
  }
  for field, entity, value in (
    ('store', 'store', settings.MOYSKLAD_STORE_ID),
    ('salesChannel', 'saleschannel', settings.MOYSKLAD_SALES_CHANNEL_ID),
    ('state', 'customerorder/metadata/states', settings.MOYSKLAD_ORDER_STATES.get(purchase.status.value)),
  ):
    if value:
      payload[field] = entity_ref(entity, value)
  return payload


def verify_order(order: dict, purchase: Purchase, submission: PurchaseSubmission | None = None) -> str:
  try:
    order_id = str(UUID(str(order['id'])))
    remote_sync_id = UUID(str(order['syncId']))
  except (KeyError, TypeError, ValueError) as exc:
    raise JSRError('conflict', message='MoySklad order identity is missing or invalid') from exc
  if remote_sync_id != sync_uuid(purchase) or order.get('externalCode') != purchase.uuid:
    raise JSRError('conflict', message='MoySklad order was not created by this integration in this environment')
  if submission and (
    submission.purchase_id != purchase.id or submission.uuid != remote_sync_id or submission.order_id != order_id
  ):
    raise JSRError('conflict', message='PurchaseSubmission does not match the MoySklad order')
  return order_id


async def sync_purchase(session: AsyncSession, purchase: Purchase, products_by_id: dict, *, patch: bool = False) -> None:
  """Caller holds the purchase lock and commits after success. No hidden commits."""
  submission = (await session.execute(
    select(PurchaseSubmission).where(PurchaseSubmission.purchase_id == purchase.id)
  )).scalar_one_or_none()
  if not settings.MOYSKLAD_TOKEN:
    raise JSRError(status=503, message='MoySklad token is not configured')
  try:
    async with MoySkladClient() as client:
      if submission:
        # Validate before even constructing a remote mutation.
        try:
          order_id = str(UUID(submission.order_id))
        except ValueError as exc:
          raise JSRError('conflict', message='Invalid MoySklad order ID') from exc
        order = await client.get(f'/entity/customerorder/{order_id}')
      else:
        result = await client.get('/entity/customerorder', filter=f'syncId={sync_uuid(purchase)}', limit=2)
        if not isinstance(result, dict) or not isinstance(result.get('rows'), list):
          raise JSRError(status=502, message='Invalid MoySklad order search response')
        if len(result['rows']) > 1:
          raise JSRError('conflict', message='Multiple MoySklad orders match this purchase')
        order = result['rows'][0] if result['rows'] else None
      if order is not None:
        order_id = verify_order(order, purchase, submission)
        if patch:
          payload = build_order_payload(purchase, products_by_id)
          # Preserve the remote organization, counterparty, channel and sync identity.
          for field in ('organization', 'agent', 'store', 'salesChannel', 'syncId', 'externalCode'):
            payload.pop(field, None)
          order = await client.update('customerorder', order_id, payload)
          verify_order(order, purchase, submission)
      else:
        if submission:
          raise JSRError('conflict', message='Linked MoySklad order is unavailable')
        order = await client.create('customerorder', build_order_payload(purchase, products_by_id))
        order_id = verify_order(order, purchase)
      if submission is None:
        session.add(PurchaseSubmission(uuid=sync_uuid(purchase), order_id=order_id, purchase_id=purchase.id))
        await session.flush()
  except (httpx.HTTPError, MoySkladError) as exc:
    # Do not leak provider responses (which may contain customer details).
    raise JSRError(status=502, message=f'MoySklad synchronization failed for purchase {purchase.id}; retry the same purchase') from exc


async def sync_purchase_status(session: AsyncSession, purchase: Purchase, *, paid: bool = False) -> None:
  """Update only integration status lines and an explicitly mapped native state."""
  if not settings.MOYSKLAD_CHECKOUT_SYNC_ENABLED:
    return
  submission = (await session.execute(
    select(PurchaseSubmission).where(PurchaseSubmission.purchase_id == purchase.id)
  )).scalar_one_or_none()
  if submission is None:
    return  # Orders created while exchange was disabled are not created by a payment event.
  if not settings.MOYSKLAD_TOKEN:
    raise JSRError(status=503, message='MoySklad token is not configured')
  try:
    order_id = str(UUID(submission.order_id))
  except ValueError as exc:
    raise JSRError('conflict', message='Invalid MoySklad order ID') from exc
  try:
    async with MoySkladClient() as client:
      order = await client.get(f'/entity/customerorder/{order_id}')
      verify_order(order, purchase, submission)
      lines = (order.get('description') or '').splitlines()
      changes = {'Статус сайта:': purchase.status.value}
      if paid:
        changes['Оплата YooKassa:'] = 'succeeded'
      for prefix, value in changes.items():
        replacement = f'{prefix} {value}'
        if any(line.startswith(prefix) for line in lines):
          lines = [replacement if line.startswith(prefix) else line for line in lines]
        else:
          lines.append(replacement)
      payload = {}
      description = '\n'.join(lines)
      if description != (order.get('description') or ''):
        payload['description'] = description
      state_id = settings.MOYSKLAD_ORDER_STATES.get(purchase.status.value)
      if state_id:
        state = entity_ref('customerorder/metadata/states', state_id)
        if state['meta']['href'] != (order.get('state') or {}).get('meta', {}).get('href'):
          payload['state'] = state
      if payload:
        updated = await client.update('customerorder', order_id, payload)
        verify_order(updated, purchase, submission)
  except (httpx.HTTPError, MoySkladError) as exc:
    raise JSRError(status=502, message=f'MoySklad status synchronization failed for purchase {purchase.id}; retry payment notification or status check') from exc
