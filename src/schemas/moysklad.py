import uuid

from pydantic import BaseModel


class MoySkladSkippedProduct(BaseModel):
  id: uuid.UUID
  name: str


class MoySkladImportResponse(BaseModel):
  products: int
  variants: int
  skipped_products: list[MoySkladSkippedProduct]
