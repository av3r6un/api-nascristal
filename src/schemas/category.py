from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CategoryItem(BaseModel):
  id: int
  eid: str
  uid: str
  parent_id: int | None
  name: str
  index: int
  icon: str


class CategoriesResponse(BaseModel):
  items: list[CategoryItem]


class CategoryPatchItem(BaseModel):
  model_config = ConfigDict(extra="forbid")

  id: int
  name: str | None = Field(default=None, max_length=255)
  index: int | None = Field(default=None, ge=0)
  icon: str | None = Field(default=None, max_length=25)

  @field_validator("name")
  @classmethod
  def validate_name(cls, value: str | None) -> str | None:
    if value is None:
      return value
    value = value.strip()
    if not value:
      raise ValueError("Category name must not be empty")
    return value

  @field_validator("icon")
  @classmethod
  def validate_icon(cls, value: str | None) -> str | None:
    if value is None:
      return value
    value = value.strip()
    if not value:
      raise ValueError("Category icon must not be empty")
    return value

  @model_validator(mode="after")
  def validate_editable_fields(self) -> "CategoryPatchItem":
    if self.name is None and self.index is None and self.icon is None:
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
