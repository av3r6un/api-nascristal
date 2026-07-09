from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field


class DeliveryInfo(BaseModel):
  type: str
  address: str
  cost: int = Field(ge=0)


def _coerce_delivery_cost(value: Any) -> int:
  if value is None:
    return 0
  try:
    return int(Decimal(str(value)))
  except (InvalidOperation, ValueError):
    return 0


def normalize_delivery_info(delivery: DeliveryInfo | dict[str, Any] | str | None) -> dict:
  if isinstance(delivery, DeliveryInfo):
    return delivery.model_dump()

  if isinstance(delivery, dict):
    cost = next(
      (_coerce_delivery_cost(delivery.get(key)) for key in ("cost", "price", "amount", "value") if delivery.get(key) is not None),
      0,
    )
    return {
      "type": str(delivery.get("type") or delivery.get("id") or "delivery"),
      "address": str(delivery.get("address") or delivery.get("name") or delivery.get("title") or delivery.get("label") or ""),
      "cost": cost,
    }

  return {
    "type": "" if delivery is None else str(delivery),
    "address": "",
    "cost": 0,
  }


def normalize_contact_info(contact_info: dict[str, Any] | None) -> dict:
  normalized = dict(contact_info or {})
  normalized["delivery"] = normalize_delivery_info(normalized.get("delivery"))
  return normalized


class ContactInfo(BaseModel):
  name: str
  phone: str
  delivery: DeliveryInfo
  username: str | None = None
  email: str | None = None
