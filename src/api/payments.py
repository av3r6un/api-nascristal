from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.exceptions import JSRError
from src.models import Payment, Purchase
from src.schemas.payment import PaymentResponse
from src.services.payment_sync import refresh_payment_state


router = APIRouter(prefix="/api/payments", tags=["payments"])


def _serialize_payment(payment: Payment, purchase: Purchase | None) -> dict:
  return {
    "id": payment.id,
    "uuid": payment.uuid,
    "purchase": (
      {
        "id": purchase.id,
        "created_ts": purchase.created_ts,
        "payment_method": purchase.payment_method,
        "contact_info": purchase.contact_info,
      }
      if purchase is not None else None
    ),
    "provider": payment.provider,
    "idempotency_key": payment.idempotency_key,
    "external_payment_id": payment.external_payment_id,
    "status": payment.status,
    "amount_value": payment.amount_value,
    "currency": payment.currency,
    "paid": payment.paid,
    "confirmation_url": payment.confirmation_url,
    "return_url": payment.return_url,
    "created_ts": payment.created_ts,
    "updated_ts": payment.updated_ts,
  }

@router.get("/{payment_uuid}", response_model=PaymentResponse, status_code=200)
async def get_payment(payment_uuid: str, session: AsyncSession = Depends(get_db)) -> dict:
  payment = await Payment.first(session, uuid=payment_uuid)
  if not payment:
    raise JSRError("not_found", message=f"Payment not found: {payment_uuid}")

  purchase = await Purchase.first(session, payment_id=payment.id)
  payment = await refresh_payment_state(session, payment, purchase)

  return _serialize_payment(payment, purchase)
