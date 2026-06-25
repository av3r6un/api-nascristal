from ipaddress import ip_address, ip_network

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.exceptions import JSRError
from src.models import Payment, Purchase
from src.models.payment import PaymentStatus as ProviderPaymentStatus
from src.models.purchase import PaymentStatus as PurchasePaymentStatus


router = APIRouter(tags=["yookassa"])

_YOOKASSA_ALLOWED_IPS = (
  ip_network("185.71.76.0/27"),
  ip_network("185.71.77.0/27"),
  ip_network("77.75.153.0/25"),
  ip_network("77.75.156.11/32"),
  ip_network("77.75.156.35/32"),
  ip_network("77.75.154.128/25"),
  ip_network("2a02:5180::/32"),
)


def _request_ip(request: Request) -> str:
  forwarded = request.headers.get("x-forwarded-for")
  if forwarded:
    return forwarded.split(",")[0].strip()
  return request.client.host if request.client else "0.0.0.0"


def _is_allowed_yookassa_ip(value: str) -> bool:
  try:
    remote_ip = ip_address(value)
  except ValueError:
    return False
  return any(remote_ip in network for network in _YOOKASSA_ALLOWED_IPS)


def _map_purchase_payment_status(payment_status: str) -> PurchasePaymentStatus:
  mapping = {
    ProviderPaymentStatus.SUCCEEDED.value: PurchasePaymentStatus.PAID,
    ProviderPaymentStatus.CANCELED.value: PurchasePaymentStatus.FAILED,
    ProviderPaymentStatus.FAILED.value: PurchasePaymentStatus.FAILED,
  }
  return mapping.get(payment_status, PurchasePaymentStatus.PENDING)


@router.get("/webhooks/yookassa", status_code=200)
async def yookassa_webhook_info() -> dict[str, str]:
  return {"method": "POST"}


@router.post("/webhooks/yookassa", status_code=200)
async def yookassa_webhook(request: Request, session: AsyncSession = Depends(get_db)) -> Response:
  if not _is_allowed_yookassa_ip(_request_ip(request)):
    raise JSRError("forbidden", message="Forbidden source IP")

  payload = await request.json()
  event = payload.get("event")
  object_payload = payload.get("object") or {}
  external_payment_id = object_payload.get("id")

  if not external_payment_id:
    raise JSRError("bad_request", message="Missing payment id")

  payment = await Payment.first(session, external_payment_id=external_payment_id)
  if not payment:
    raise JSRError("not_found", message=f"Payment not found: {external_payment_id}")

  payment_status = object_payload.get("status", payment.status)
  payment.status = (
    ProviderPaymentStatus(payment_status).value
    if payment_status in {item.value for item in ProviderPaymentStatus}
    else payment.status
  )
  payment.paid = bool(object_payload.get("paid", payment.paid))
  payment.confirmation_url = (object_payload.get("confirmation") or {}).get("confirmation_url", payment.confirmation_url)
  payment.response_payload = object_payload
  payment.notification_payload = payload

  purchase = await Purchase.first(session, payment_id=payment.id)
  if purchase:
    purchase.payment_status = _map_purchase_payment_status(payment.status)

  await session.commit()
  return Response(status_code=200)
