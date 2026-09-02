from typing import Any

from pydantic import BaseModel, Field


class ProductsResponse(BaseModel):
  items: list[dict[str, Any]] = Field(default_factory=list)
  page_index: int
  page_size: int
  has_next_page: bool

class ProductsAttributesResponse(BaseModel):
  categories: list[dict[str, Any]] = Field(default_factory=list)
  attributes: list[dict[str, Any]] = Field(default_factory=list)
