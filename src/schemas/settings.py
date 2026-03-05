from pydantic import BaseModel
from typing import Any

class SettingsRequest(BaseModel):
  key: str
  value: Any
