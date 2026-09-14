from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Payment, Purchase, PurchaseStatus
from src.models.payment import PaymentStatus as ProviderPaymentStatus
from src.services.purchase_sync import lock_purchase, sync_purchase_status
from src.services.yookassa import get_yookassa_payment


async def apply_successful_payment(
  session: AsyncSession, payment: Payment, purchase: Purchase | None = None,
) -> None:
  if payment.status != ProviderPaymentStatus.SUCCEEDED.value:
    return
  if purchase is None:
    purchase = await Purchase.first(session, payment_id=payment.id)
  if purchase is None:
    return
  purchase = await lock_purchase(session, purchase.id)
  if purchase.payment_id != payment.id:
    return  # A superseded payment must not update the current order.
  if purchase.status != PurchaseStatus.FINISHED:
    purchase.status = PurchaseStatus.DELIVERING
  # A provider failure must never roll back the already confirmed payment.
  await session.commit()
  purchase = await lock_purchase(session, purchase.id)
  if purchase.payment_id == payment.id:
    await sync_purchase_status(session, purchase, paid=True)
  await session.commit()
  await session.refresh(purchase)


async def refresh_payment_state(
  session: AsyncSession,
  payment: Payment,
  purchase: Purchase | None = None,
) -> Payment:
  if payment.status == ProviderPaymentStatus.SUCCEEDED.value:
    # Still retry the outbound update if a previous notification failed.
    await apply_successful_payment(session, payment, purchase)
    return payment
  if not payment.external_payment_id:
    return payment

  provider_payment = await get_yookassa_payment(payment.external_payment_id)
  payment.status = provider_payment.get('status', payment.status)
  payment.paid = bool(provider_payment.get('paid', payment.paid))
  payment.confirmation_url = (provider_payment.get('confirmation') or {}).get('confirmation_url', payment.confirmation_url)
  payment.response_payload = provider_payment

  await session.commit()
  await session.refresh(payment)
  await apply_successful_payment(session, payment, purchase)
  return payment
