from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PropertyOptionPropertyItem(BaseModel):
  id: int
  eid: str
  index: int
  name: str
  is_active: bool


class PropertyOptionItem(BaseModel):
  id: int
  eid: str
  property_id: int
  value: str
  name: str | None
  icon: str | None
  is_active: bool
  property: PropertyOptionPropertyItem


class PropertyOptionsResponse(BaseModel):
  items: list[PropertyOptionItem]


class PropertyOptionPatchItem(BaseModel):
  model_config = ConfigDict(extra="forbid")

  id: int
  name: str | None = Field(default=None, max_length=255)
  icon: str | None = Field(default=None, max_length=255)

  @field_validator("name")
  @classmethod
  def validate_name(cls, value: str | None) -> str | None:
    if value is None:
      return value
    value = value.strip()
    if not value:
      raise ValueError("Property option name must not be empty")
    return value

  @field_validator("icon")
  @classmethod
  def validate_icon(cls, value: str | None) -> str | None:
    if value is None:
      return value
    value = value.strip()
    if not value:
      raise ValueError("Property option icon must not be empty")
    return value

  @model_validator(mode="after")
  def validate_editable_fields(self) -> "PropertyOptionPatchItem":
    if "name" not in self.model_fields_set and "icon" not in self.model_fields_set:
      raise ValueError("At least one editable field must be provided")
    return self


class PropertyOptionsPatchRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")

  items: list[PropertyOptionPatchItem] = Field(min_length=1)

  @model_validator(mode="after")
  def validate_unique_ids(self) -> "PropertyOptionsPatchRequest":
    ids = [item.id for item in self.items]
    if len(ids) != len(set(ids)):
      raise ValueError("Property option ids must be unique")
    return self
