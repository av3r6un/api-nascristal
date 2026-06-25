from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Payment, Purchase
from src.models.payment import PaymentStatus as ProviderPaymentStatus
from src.models.purchase import PaymentStatus as PurchasePaymentStatus
from src.services.yookassa import get_yookassa_payment


def map_purchase_payment_status(payment_status: str) -> PurchasePaymentStatus:
  if payment_status == ProviderPaymentStatus.SUCCEEDED.value:
    return PurchasePaymentStatus.PAID
  if payment_status in {ProviderPaymentStatus.CANCELED.value, ProviderPaymentStatus.FAILED.value}:
    return PurchasePaymentStatus.FAILED
  return PurchasePaymentStatus.PENDING


async def refresh_payment_state(
  session: AsyncSession,
  payment: Payment,
  purchase: Purchase | None = None,
) -> Payment:
  if not payment.external_payment_id:
    if purchase:
      purchase.payment_status = map_purchase_payment_status(payment.status)
      await session.commit()
      await session.refresh(purchase)
    return payment

  if payment.paid or payment.status == ProviderPaymentStatus.SUCCEEDED.value:
    if purchase:
      purchase.payment_status = map_purchase_payment_status(payment.status)
      await session.commit()
      await session.refresh(purchase)
    return payment

  provider_payment = await get_yookassa_payment(payment.external_payment_id)
  payment.status = provider_payment.get("status", payment.status)
  payment.paid = bool(provider_payment.get("paid", payment.paid))
  payment.confirmation_url = (provider_payment.get("confirmation") or {}).get("confirmation_url", payment.confirmation_url)
  payment.response_payload = provider_payment

  if purchase:
    purchase.payment_status = map_purchase_payment_status(payment.status)

  await session.commit()
  await session.refresh(payment)
  if purchase:
    await session.refresh(purchase)
  return payment
