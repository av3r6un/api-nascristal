from typing import Any

from pydantic import BaseModel


def normalize_contact_info(contact_info: dict[str, Any] | None) -> dict:
  normalized = dict(contact_info or {})
  # Do not expose legacy delivery data stored by older purchases.
  normalized.pop("delivery", None)
  return normalized


class ContactInfo(BaseModel):
  name: str
  phone: str
  username: str | None = None
  email: str | None = None
