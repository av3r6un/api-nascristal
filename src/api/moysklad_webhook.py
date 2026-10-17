import secrets
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.schemas.moysklad_webhook import MoyskladWebhook
from src.services.moysklad_webhook import save_webhook_events


router = APIRouter(tags=['moysklad'])
logger = logging.getLogger('uvicorn.error')


@router.post('/webhooks/moysklad', status_code=204)
async def moysklad_webhook(
  request: Request,
  request_id: UUID = Query(alias='requestId'),
  secret: str | None = Query(default=None),
  session: AsyncSession = Depends(get_db),
) -> Response:
  if not settings.MOYSKLAD_WEBHOOK_SECRET or not settings.MOYSKLAD_ACCOUNT_ID:
    raise HTTPException(503, 'MoySklad webhook is not configured')
  try:
    account_id = UUID(settings.MOYSKLAD_ACCOUNT_ID)
  except ValueError:
    raise HTTPException(503, 'Invalid MoySklad account configuration')
  if secret is None or not secrets.compare_digest(
    secret.encode(), settings.MOYSKLAD_WEBHOOK_SECRET.encode(),
  ):
    logger.warning(
      'MoySklad webhook rejected: reason=%s request_id=%s',
      'secret_missing' if secret is None else 'secret_mismatch', request_id,
    )
    raise HTTPException(403, 'Invalid webhook secret')

  # Bound memory use even when Content-Length is absent.
  body = bytearray()
  async for chunk in request.stream():
    body.extend(chunk)
    if len(body) > 1024 * 1024:
      raise HTTPException(413, 'Webhook body is too large')
  try:
    payload = MoyskladWebhook.model_validate_json(body)
  except ValidationError:
    raise HTTPException(422, 'Invalid MoySklad webhook payload')
  if any(event.accountId != account_id for event in payload.events):
    logger.warning('MoySklad webhook rejected: reason=account_mismatch request_id=%s', request_id)
    raise HTTPException(403, 'Unexpected MoySklad account')

  async with session.begin():
    await save_webhook_events(session, payload.events, request_id)
  logger.info(
    'MoySklad webhook accepted: request_id=%s events=%d', request_id, len(payload.events),
  )
  return Response(status_code=204)
