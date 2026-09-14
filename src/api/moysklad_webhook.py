from secrets import compare_digest
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.exceptions import JSRError
from src.services.moysklad_address_sync import refresh_address
from src.services.moysklad_client import MoySkladClient

router = APIRouter(tags=['moysklad-webhooks'])


class EventMeta(BaseModel):
  type: str
  href: str


class OrderEvent(BaseModel):
  meta: EventMeta
  action: str
  updatedFields: list[str] | None = None


class Notification(BaseModel):
  events: list[OrderEvent] = Field(max_length=1000)


async def authorize_webhook(token: str = Query(default='')):
  secret = settings.MOYSKLAD_WEBHOOK_SECRET
  if not secret or not compare_digest(token.encode(), secret.encode()):
    raise JSRError('forbidden', message='Invalid webhook token')


@router.post('/webhooks/moysklad', status_code=204, dependencies=[Depends(authorize_webhook)])
async def moysklad_webhook(payload: Notification, session: AsyncSession = Depends(get_db)):
  base = urlsplit(MoySkladClient.BASE_URL)
  prefix = base.path + '/entity/customerorder/'
  order_ids = set()
  for event in payload.events:
    if event.action != 'UPDATE' or event.meta.type != 'customerorder':
      continue
    if event.updatedFields is not None and not {'shipmentAddress', 'shipmentAddressFull'}.intersection(event.updatedFields):
      continue
    url = urlsplit(event.meta.href)
    if url.scheme != base.scheme or url.netloc != base.netloc or not url.path.startswith(prefix) or url.query or url.fragment:
      raise JSRError('bad_request', message='Invalid customerorder URL')
    try:
      order_ids.add(str(UUID(url.path[len(prefix):])))
    except ValueError as exc:
      raise JSRError('bad_request', message='Invalid customerorder UUID') from exc
  for order_id in order_ids:
    await refresh_address(session, order_id)
  return Response(status_code=204)
