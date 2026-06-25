from pydantic import BaseModel


class PaymentPurchaseContactInfo(BaseModel):
  name: str
  phone: str
  delivery: str
  username: str | None = None


class PaymentPurchaseInfo(BaseModel):
  id: int
  created_ts: int
  payment_method: str
  contact_info: PaymentPurchaseContactInfo


class PaymentInfo(BaseModel):
  id: int
  uuid: str
  purchase: PaymentPurchaseInfo | None
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


class PaymentResponse(PaymentInfo):
  pass
