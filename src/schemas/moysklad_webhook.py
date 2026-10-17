from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class WebhookMeta(BaseModel):
  type: Literal['product', 'variant', 'customerorder']
  href: str

  @model_validator(mode='after')
  def validate_href(self):
    prefix = f'https://api.moysklad.ru/api/remap/1.2/entity/{self.type}/'
    if not self.href.startswith(prefix):
      raise ValueError('Invalid MoySklad entity URL')
    UUID(self.href.removeprefix(prefix))
    return self

  @property
  def entity_uuid(self) -> UUID:
    return UUID(self.href.rsplit('/', 1)[1])


class WebhookEvent(BaseModel):
  meta: WebhookMeta
  action: Literal['CREATE', 'UPDATE', 'DELETE']
  accountId: UUID
  updatedFields: list[str] | None = None


class MoyskladWebhook(BaseModel):
  events: list[WebhookEvent] = Field(min_length=1, max_length=1000)
