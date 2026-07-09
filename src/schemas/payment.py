from pydantic import BaseModel

from src.schemas.contact import ContactInfo


class PaymentPurchaseInfo(BaseModel):
  id: int
  created_ts: int
  contact_info: ContactInfo


class PaymentInfo(BaseModel):
  id: int
  uuid: str
  provider: str
  idempotency_key: str
  external_payment_id: str | None
  status: str
  amount_value: str
  currency: str
  paid: bool
  confirmation_url: str | None
  return_url: str | None
  created_ts: int
  updated_ts: int


class PaymentWithPurchaseInfo(PaymentInfo):
  purchase: PaymentPurchaseInfo | None


class PaymentResponse(PaymentWithPurchaseInfo):
  pass


class PaymentTrackingInfo(BaseModel):
  status: str
  amount_value: str
  currency: str
  paid: bool
  confirmation_url: str | None
