from pydantic import BaseModel, Field


class CategoryResponse(BaseModel):
  uid: str
  index: int
  icon: str
  locale: str
  name: str
  description: str | None


class CategoriesResponse(BaseModel):
  items: list[CategoryResponse]


class CategoryRequest(BaseModel):
  uid: str | None = Field(default=None, min_length=8, max_length=8)
  index: int | None = None
  icon: str = Field(default="diamond", max_length=25)
  locale: str = Field(min_length=2, max_length=2)
  name: str = Field(min_length=1, max_length=255)
  description: str | None = None


class CategorySaveResponse(BaseModel):
  processed: bool
  uid: str


class BatchUpdateResponse(BaseModel):
  processed: bool
  updated: int


class ProcessResponse(BaseModel):
  processed: bool


class CategoryBatchUpdateItem(BaseModel):
  uid: str = Field(min_length=8, max_length=8)
  index: int
  icon: str = Field(max_length=25)
  locale: str = Field(min_length=2, max_length=2)
  name: str = Field(min_length=1, max_length=255)
  description: str | None = None


class CategoryBatchUpdateRequest(BaseModel):
  items: list[CategoryBatchUpdateItem] = Field(min_length=1)


class ColorResponse(BaseModel):
  id: int
  sku: str
  name: str


class ColorsResponse(BaseModel):
  items: list[ColorResponse]


class ColorRequest(BaseModel):
  id: int | None = None
  sku: str = Field(min_length=1, max_length=50)
  name: str = Field(min_length=1, max_length=100)


class ColorBatchUpdateItem(BaseModel):
  id: int
  sku: str = Field(min_length=1, max_length=50)
  name: str = Field(min_length=1, max_length=100)


class ColorBatchUpdateRequest(BaseModel):
  items: list[ColorBatchUpdateItem] = Field(min_length=1)


class SizeResponse(BaseModel):
  id: int
  sku: str
  size_min: int
  size_max: int


class SizesResponse(BaseModel):
  items: list[SizeResponse]


class SizeRequest(BaseModel):
  id: int | None = None
  sku: str = Field(min_length=1, max_length=50)
  size_min: int
  size_max: int


class SizeBatchUpdateItem(BaseModel):
  id: int
  sku: str = Field(min_length=1, max_length=50)
  size_min: int
  size_max: int


class SizeBatchUpdateRequest(BaseModel):
  items: list[SizeBatchUpdateItem] = Field(min_length=1)


class WarehouseSpecsResponse(BaseModel):
  categories: list[CategoryResponse]
  colors: list[ColorResponse]
  sizes: list[SizeResponse]
