from pydantic import BaseModel


class CatalogPropertyItem(BaseModel):
  id: int
  index: int
  name: str
  is_active: bool


class CatalogOptionItem(BaseModel):
  id: int
  property_id: int
  value: str
  name: str | None
  icon: str | None


class CatalogResponse(BaseModel):
  properties: list[CatalogPropertyItem]
  options: list[CatalogOptionItem]
