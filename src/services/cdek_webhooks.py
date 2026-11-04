"""Webhook notifications only trigger authenticated refreshes of local shipments."""
from hmac import compare_digest
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select, or_

from src.exceptions import JSRError
from src.models.delivery import DeliveryShipment
from src.services.integrations import configuration
from src.services.cdek_client import CdekClient
from src.services import cdek

TOPICS = ('ORDER_STATUS', 'ORDER_MODIFIED', 'PRINT_FORM')


class Notification(BaseModel):
  type: str
  uuid: UUID


async def subscribe(session):
  _, config, _ = await configuration(session, require_enabled=True)
  if not config.webhooks_enabled:
    raise JSRError(status=409, message='Вебхуки СДЭК выключены')
  url = urlsplit(config.webhook_url or '')
  if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
    raise JSRError('bad_request', message='Укажите публичный HTTPS URL обработчика /webhooks/cdek')
  if not config.webhook_secret:
    raise JSRError('bad_request', message='Задайте webhook_secret длиной не менее 32 символов')
  query = dict(parse_qsl(url.query))
  query['token'] = config.webhook_secret.get_secret_value()
  callback = urlunsplit((url.scheme, url.netloc, url.path, urlencode(query), ''))
  async with CdekClient(config) as client:
    existing = await client.request('GET', '/v2/webhooks')
    rows = existing if isinstance(existing, list) else existing.get('entity', [])
    if not isinstance(rows, list):
      raise JSRError(status=502, message='Некорректный список подписок СДЭК')
    created = 0
    for topic in TOPICS:
      if any(row.get('type') == topic and row.get('url') == callback for row in rows):
        continue
      await client.request('POST', '/v2/webhooks', json={'type': topic, 'url': callback})
      created += 1
  return {'types': TOPICS, 'created': created}


async def receive(session, token, notification):
  _, config, _ = await configuration(session)
  if not config.webhooks_enabled:
    return {'accepted': True, 'ignored': True}
  secret = config.webhook_secret.get_secret_value() if config.webhook_secret else ''
  if not secret or not token or not compare_digest(token.encode(), secret.encode()):
    raise JSRError(status=403, message='Invalid CDEK webhook token')
  if notification.type not in TOPICS:
    return {'accepted': True, 'ignored': True}
  uuid = str(notification.uuid)
  condition = or_(DeliveryShipment.waybill['uuid'].as_string() == uuid,
    DeliveryShipment.barcode['uuid'].as_string() == uuid) if notification.type == 'PRINT_FORM' else DeliveryShipment.remote_uuid == uuid
  row = await session.scalar(select(DeliveryShipment).where(DeliveryShipment.provider == 'cdek', condition))
  if row is None:
    return {'accepted': True, 'ignored': True}
  # Never apply status, amounts or PDF URLs from an unauthenticated event body.
  await cdek.refresh_shipment(session, row.purchase_id)
  return {'accepted': True}
