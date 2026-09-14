from typing import Any
from uuid import UUID
from decimal import Decimal
from pydantic import BaseModel, Field


class ProductsResponse(BaseModel):
  items: list[dict[str, Any]] = Field(default_factory=list)
  page_index: int
  page_size: int
  has_next_page: bool

class ProductsAttributesResponse(BaseModel):
  categories: list[dict[str, Any]] = Field(default_factory=list)
  attributes: list[dict[str, Any]] = Field(default_factory=list)

class ProductResponse(BaseModel):
  id: int
  uuid: UUID
  sku: str | None
  name: str
  description: str | None
  archived: bool
  category: dict[str, Any]
  variants: list[dict[str, Any]]
  images: list[dict[str, Any]]
  variants_count: float
  min_price: Decimal
  
