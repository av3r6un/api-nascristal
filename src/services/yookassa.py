from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from src.core.config import settings
from src.exceptions import JSRError


def _price_to_amount_value(price: int | Decimal) -> str:
  amount = Decimal(price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
  return format(amount, "f")


def build_yookassa_payment_payload(
  *,
  price: int | Decimal,
  description: str,
  return_url: str,
  metadata: dict[str, str],
  receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
  payload = {
    "amount": {
      "value": _price_to_amount_value(price),
      "currency": "RUB",
    },
    "capture": True,
    "confirmation": {
      "type": "redirect",
      "return_url": return_url,
    },
    "description": description,
    "metadata": metadata,
  }
  if receipt is not None:
    payload["receipt"] = receipt
  return payload


def build_purchase_return_url(base_url: str, purchase_uuid: str) -> str:
  parsed = urlsplit(base_url)
  query = dict(parse_qsl(parsed.query, keep_blank_values=True))
  query["purchase"] = purchase_uuid
  return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


async def create_yookassa_payment(
  *,
  idempotency_key: str,
  payload: dict[str, Any],
) -> dict[str, Any]:
  if not settings.YOOKASSA_SHOP_ID or not settings.YOOKASSA_SECRET_KEY or not settings.YOOKASSA_RETURN_URL:
    raise JSRError(status=500, message="YooKassa is not configured")

  headers = {
    "Idempotence-Key": idempotency_key,
    "Content-Type": "application/json",
  }

  async with httpx.AsyncClient(
    base_url=settings.YOOKASSA_API_URL,
    auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
    timeout=30.0,
  ) as client:
    response = await client.post("/payments", headers=headers, json=payload)

  try:
    response_payload = response.json()
  except ValueError:
    response_payload = {"raw": response.text}

  if response.is_error:
    description = response_payload.get("description") if isinstance(response_payload, dict) else None
    raise JSRError(status=502, message=description or "YooKassa payment creation failed")

  return response_payload


async def cancel_yookassa_payment(
  *,
  idempotency_key: str,
  external_payment_id: str,
) -> dict[str, Any]:
  if not settings.YOOKASSA_SHOP_ID or not settings.YOOKASSA_SECRET_KEY or not settings.YOOKASSA_RETURN_URL:
    raise JSRError(status=500, message="YooKassa is not configured")

  headers = {
    "Idempotence-Key": idempotency_key,
    "Content-Type": "application/json",
  }

  async with httpx.AsyncClient(
    base_url=settings.YOOKASSA_API_URL,
    auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
    timeout=30.0,
  ) as client:
    response = await client.post(f"/payments/{external_payment_id}/cancel", headers=headers, json={})

  try:
    response_payload = response.json()
  except ValueError:
    response_payload = {"raw": response.text}

  if response.is_error:
    description = response_payload.get("description") if isinstance(response_payload, dict) else None
    raise JSRError(status=502, message=description or "YooKassa payment cancellation failed")

  return response_payload


async def get_yookassa_payment(external_payment_id: str) -> dict[str, Any]:
  if not settings.YOOKASSA_SHOP_ID or not settings.YOOKASSA_SECRET_KEY or not settings.YOOKASSA_RETURN_URL:
    raise JSRError(status=500, message="YooKassa is not configured")

  async with httpx.AsyncClient(
    base_url=settings.YOOKASSA_API_URL,
    auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
    timeout=30.0,
  ) as client:
    response = await client.get(f"/payments/{external_payment_id}")

  try:
    response_payload = response.json()
  except ValueError:
    response_payload = {"raw": response.text}

  if response.is_error:
    description = response_payload.get("description") if isinstance(response_payload, dict) else None
    raise JSRError(status=502, message=description or "YooKassa payment fetch failed")

  return response_payload


async def get_yookassa_receipt(external_payment_id: str) -> dict:
  if not settings.YOOKASSA_SHOP_ID or not settings.YOOKASSA_SECRET_KEY:
    raise JSRError(status=409, message="YooKassa credentials are required to recover the receipt")
  try:
    async with httpx.AsyncClient(
      base_url=settings.YOOKASSA_API_URL,
      auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
      timeout=30.0,
    ) as client:
      response = await client.get("/receipts", params={"payment_id": external_payment_id, "limit": 100})
    response.raise_for_status()
    data = response.json()
  except (httpx.HTTPError, ValueError) as exc:
    raise JSRError(status=502, message="Could not recover the paid receipt from YooKassa") from exc
  receipts = [r for r in data.get("items", []) if r.get("type") == "payment"
    and r.get("status") == "succeeded" and r.get("payment_id") == external_payment_id]
  if data.get("next_cursor") or len(receipts) != 1:
    raise JSRError(status=409, message="A unique successful payment receipt is required")
  return receipts[0]
