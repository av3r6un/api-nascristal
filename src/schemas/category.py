from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CategoryItem(BaseModel):
  id: int
  name: str
  sort_order: int


class CategoriesResponse(BaseModel):
  items: list[CategoryItem]


class CategoryPatchItem(BaseModel):
  model_config = ConfigDict(extra="forbid")

  id: int
  name: str | None = Field(default=None, max_length=50)
  sort_order: int | None = Field(default=None, ge=0)

  @field_validator("name")
  @classmethod
  def validate_name(cls, value: str | None) -> str | None:
    if value is None:
      return value
    value = value.strip()
    if not value:
      raise ValueError("Category name must not be empty")
    return value

  @model_validator(mode="after")
  def validate_editable_fields(self) -> "CategoryPatchItem":
    if self.name is None and self.sort_order is None:
      raise ValueError("At least one editable field must be provided")
    return self


class CategoriesPatchRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  items: list[CategoryPatchItem] = Field(min_length=1)

  @model_validator(mode="after")
  def validate_unique_ids(self) -> "CategoriesPatchRequest":
    ids = [item.id for item in self.items]
    if len(ids) != len(set(ids)):
      raise ValueError("Category ids must be unique")
    return self