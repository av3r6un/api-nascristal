from pydantic import BaseModel


class StockCategoryItem(BaseModel):
  id: int
  name: str
  index: int


class StockOptionItem(BaseModel):
  id: int
  value: str
  name: str | None


class StockImageItem(BaseModel):
  id: int
  eid: str
  path: str
  sort_order: int
  is_primary: bool


class StockVariantItem(BaseModel):
  value: str
  name: str | None


class StockOfferItem(BaseModel):
  id: int
  sku: str
  name: str
  description: str | None
  primary_image: str | None
  product_is_active: bool
  quantity: float
  unit: str | None
  is_active: bool
  amount: float
  currency: str | None
  variant: dict[int, StockVariantItem] | None


class StockItem(BaseModel):
  name: str
  images: list[StockImageItem]
  category: StockCategoryItem | None
  options: list[StockOptionItem]
  offers: list[StockOfferItem]


class StockResponse(BaseModel):
  items: list[StockItem]
  page_index: int
  has_next_page: bool


class StockOptionsResponse(BaseModel):
  filters: dict[str, list[dict[str, str | None]]] | None = None
