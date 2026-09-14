"""DEV ONLY: removable router for deleting API-created customer orders."""
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.core.config import settings
from src.core.database import get_db
from src.exceptions import JSRError
from src.models import PurchaseSubmission
from src.services.moysklad_client import MoySkladClient, MoySkladError
from src.services.purchase_sync import lock_purchase, sync_uuid, verify_order

router = APIRouter(prefix='/api/purchases', tags=['dev-purchases'])


@router.delete('/{purchase_id}', status_code=200)
async def delete_purchase(purchase_id: int, session: AsyncSession = Depends(get_db)) -> dict[str, bool]:
  if settings.STAGE != 'DEV' or not settings.DEV_PURCHASE_DELETE_ENABLED:
    raise JSRError('not_found')
  purchase = await lock_purchase(session, purchase_id)
  submission = (await session.execute(
    select(PurchaseSubmission).where(PurchaseSubmission.purchase_id == purchase.id)
  )).scalar_one_or_none()
  if submission is None or submission.uuid != sync_uuid(purchase):
    raise JSRError('conflict', message='Deletion requires a matching DEV PurchaseSubmission')
  try:
    order_id = str(UUID(submission.order_id))
  except ValueError as exc:
    raise JSRError('conflict', message='Invalid MoySklad order ID') from exc
  if not settings.MOYSKLAD_TOKEN:
    raise JSRError(status=503, message='MoySklad token is not configured')
  if purchase.payment and (purchase.payment.paid or purchase.payment.status not in {'canceled', 'failed'}):
    raise JSRError('conflict', message='Cannot delete a purchase with a paid or active payment')
  try:
    async with MoySkladClient() as client:
      # A 404 is not proof of ownership; keep both local rows for investigation.
      order = await client.get(f'/entity/customerorder/{order_id}')
      verify_order(order, purchase, submission)
      if any(order.get(field) for field in ('payments', 'demands', 'invoicesOut', 'payedSum', 'shippedSum')):
        raise JSRError('conflict', message='Cannot delete an order with payments or related documents')
      await client.delete('customerorder', order_id)
  except (httpx.HTTPError, MoySkladError) as exc:
    raise JSRError(status=502, message='MoySklad deletion failed; local purchase retained') from exc
  # No cascade into products, counterparties, payments or other remote documents.
  await session.delete(submission)
  await session.flush()
  await session.delete(purchase)
  await session.commit()
  return {'processed': True}
