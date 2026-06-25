from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from src.core.config import settings
from src.exceptions import JSRError


def _price_to_amount_value(price: int) -> str:
  amount = Decimal(price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
  return format(amount, "f")


def build_yookassa_payment_payload(
  *,
  price: int,
  description: str,
  return_url: str,
  metadata: dict[str, str],
) -> dict[str, Any]:
  return {
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
