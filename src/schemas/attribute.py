from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AttributeOptionPatchItem(BaseModel):
  model_config = ConfigDict(extra="forbid")
  id: int
  label: str | None = Field(default=None, max_length=255)

  @field_validator("label")
  @classmethod
  def normalize_label(cls, value: str | None) -> str | None:
    return value.strip() or None if value is not None else None


class AttributeOptionsPatchRequest(BaseModel):
  model_config = ConfigDict(extra="forbid")
  items: list[AttributeOptionPatchItem] = Field(min_length=1)

  @model_validator(mode="after")
  def validate_unique_ids(self) -> "AttributeOptionsPatchRequest":
    ids = [item.id for item in self.items]
    if len(ids) != len(set(ids)):
      raise ValueError("Attribute option ids must be unique")
    return self
