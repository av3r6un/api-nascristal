from pydantic import BaseModel


class ProductCategoryItem(BaseModel):
  id: int
  eid: str
  parent_id: int | None
  name: str
  index: int
  icon: str


class ProductImageItem(BaseModel):
  id: int
  eid: str
  path: str
  sort_order: int
  is_primary: bool


class ProductAttributePropertyItem(BaseModel):
  id: int
  eid: str
  name: str
  is_active: bool


class ProductAttributeOptionItem(BaseModel):
  id: int
  eid: str
  property_id: int
  value: str
  name: str | None
  icon: str | None
  is_active: bool


class ProductAttributeItem(BaseModel):
  id: int
  eid: str
  property_id: int
  option_id: int | None
  property: ProductAttributePropertyItem
  option: ProductAttributeOptionItem | None


class ProductOfferItem(BaseModel):
  id: int
  eid: str
  quantity: float
  unit: str | None
  coefficient: float
  is_active: bool
  amount: float
  currency: str | None


class ProductItem(BaseModel):
  id: int
  eid: str
  sku: str
  code: str
  name: str
  description: str | None
  primary_image: str | None
  is_active: bool
  category: ProductCategoryItem | None
  images: list[ProductImageItem]
  attributes: list[ProductAttributeItem]
  offers: list[ProductOfferItem]


class ProductsResponse(BaseModel):
  items: list[ProductItem]
  page_index: int
  has_next_page: bool
