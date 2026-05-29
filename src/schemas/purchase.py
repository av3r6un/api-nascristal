from pydantic import BaseModel, Field

from src.models.purchase import PaymentStatus, PurchaseStatus


class PurchaseQuantity(BaseModel):
  value: int = Field(ge=1)
  max: int | None = None


class PurchaseCreateItem(BaseModel):
  id: int
  properties: list[str] = Field(default_factory=list)
  quantity: PurchaseQuantity


class PurchaseCreateRequest(BaseModel):
  delivery: str
  items: list[PurchaseCreateItem] = Field(min_length=1)
  name: str
  payment: str
  phone: str
  price: int = Field(ge=0)


class PurchaseContactInfo(BaseModel):
  name: str
  phone: str
  delivery: str


class PurchasePatchRequest(BaseModel):
  product_ids: list[int] | None = Field(default=None, min_length=1)
  properties: dict[int, list[str]] | None = None
  product_quantities: dict[int, int] | None = None
  quantity: int | None = Field(default=None, ge=1)
  contact_info: PurchaseContactInfo | None = None
  final_price: int | None = Field(default=None, ge=0)
  payment_method: str | None = None
  payment_status: PaymentStatus | None = None
  status: PurchaseStatus | None = None


class PurchasePropertyMeta(BaseModel):
  id: int
  name: str


class PurchasePropertyItem(BaseModel):
  value: str
  name: str | None
  property: PurchasePropertyMeta


class PurchaseProductItem(BaseModel):
  id: int
  sku: str
  name: str
  quantity: int
  properties: list[PurchasePropertyItem]


class PurchaseItem(BaseModel):
  id: int
  uuid: str
  products: list[PurchaseProductItem]
  quantity: int
  contact_info: PurchaseContactInfo
  final_price: int
  payment_method: str
  payment_status: PaymentStatus
  status: PurchaseStatus
  created_ts: int
  updated_ts: int


class PurchaseResponse(PurchaseItem):
  pass


class PurchasesResponse(BaseModel):
  items: list[PurchaseItem]
