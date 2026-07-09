from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Payment, Purchase
from src.models.payment import PaymentStatus as ProviderPaymentStatus
from src.services.yookassa import get_yookassa_payment


async def refresh_payment_state(
  session: AsyncSession,
  payment: Payment,
  purchase: Purchase | None = None,
) -> Payment:
  if not payment.external_payment_id:
    return payment

  if payment.paid or payment.status == ProviderPaymentStatus.SUCCEEDED.value:
    return payment

  provider_payment = await get_yookassa_payment(payment.external_payment_id)
  payment.status = provider_payment.get("status", payment.status)
  payment.paid = bool(provider_payment.get("paid", payment.paid))
  payment.confirmation_url = (provider_payment.get("confirmation") or {}).get("confirmation_url", payment.confirmation_url)
  payment.response_payload = provider_payment

  await session.commit()
  await session.refresh(payment)
  return payment
