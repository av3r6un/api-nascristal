from pydantic import BaseModel, Field

from src.models.purchase import PurchaseStatus
from src.schemas.contact import ContactInfo
from src.schemas.delivery import PurchaseDelivery
from src.schemas.payment import PaymentInfo, PaymentTrackingInfo


class PurchaseQuantity(BaseModel):
  value: int = Field(ge=1)
  max: int | None = None


class PurchaseCreateItem(BaseModel):
  id: int = Field(gt=0, description="Offer ID")
  properties: list[str] = Field(default_factory=list)
  quantity: PurchaseQuantity


class PurchaseCustomer(BaseModel):
  name: str
  phone: str
  username: str | None = None
  email: str = Field(min_length=3)


class PurchaseCreateRequest(BaseModel):
  customer: PurchaseCustomer
  items: list[PurchaseCreateItem] = Field(min_length=1)
  price: int = Field(ge=0)
  delivery: PurchaseDelivery | None = None

PurchaseContactInfo = ContactInfo


class PurchasePatchRequest(BaseModel):
  product_ids: list[int] | None = Field(default=None, min_length=1)
  properties: dict[int, list[str]] | None = None
  product_quantities: dict[int, int] | None = None
  quantity: int | None = Field(default=None, ge=1)
  contact_info: PurchaseContactInfo | None = None
  final_price: int | None = Field(default=None, ge=0)
  status: PurchaseStatus | None = None


class PurchasePropertyMeta(BaseModel):
  id: int
  name: str


class PurchasePropertyItem(BaseModel):
  value: str
  name: str | None
  property: PurchasePropertyMeta


class PurchasePatchProductItem(BaseModel):
  id: int = Field(gt=0, description="Offer ID")
  sku: str | None = None
  name: str | None = None
  price: int | None = Field(default=None, ge=0)
  quantity: PurchaseQuantity
  properties: list[PurchasePropertyItem] = Field(default_factory=list)


class PurchaseUpdateRequest(BaseModel):
  delivery: PurchaseDelivery | None = None
  contact_info: PurchaseContactInfo | None = None
  products: list[PurchasePatchProductItem] | None = Field(default=None, min_length=1)
  final_price: int | None = Field(default=None, ge=0)


class PurchaseProductItem(BaseModel):
  id: int = Field(gt=0, description="Offer ID")
  sku: str
  name: str
  price: int
  quantity: PurchaseQuantity
  properties: list[PurchasePropertyItem]


class PurchaseItem(BaseModel):
  id: int
  uuid: str
  payment_id: int | None
  products: list[PurchaseProductItem]
  contact_info: PurchaseContactInfo
  delivery: PurchaseDelivery | None = None
  payment: PaymentInfo | None
  status: PurchaseStatus
  created_ts: int
  updated_ts: int


class PurchaseResponse(PurchaseItem):
  delivery_editable: bool = True
  delivery_update_status: str | None = None
  delivery_status: dict | None = None
  delivery_can_dispatch: bool = False


class PurchasesResponse(BaseModel):
  items: list[PurchaseItem]


class PurchaseTrackingPurchaseInfo(BaseModel):
  id: int
  created_ts: int
  price: int | None = None
  final_price: int | None = None
  status: PurchaseStatus
  contact_info: PurchaseContactInfo
  delivery: PurchaseDelivery | None = None


class PurchaseTrackingResponse(BaseModel):
  purchase: PurchaseTrackingPurchaseInfo
  payment: PaymentTrackingInfo | None
