from typing import Literal
from urllib.parse import parse_qs, urlsplit
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


class MoyskladStockWebhook(BaseModel):
  accountId: UUID
  stockType: Literal['stock']
  reportType: Literal['all']
  reportUrl: str

  @model_validator(mode='after')
  def validate_report_url(self):
    url = urlsplit(self.reportUrl)
    if (url.scheme != 'https' or url.netloc != 'api.moysklad.ru'
        or url.path != '/api/remap/1.2/report/stock/all/current'
        or url.fragment or not parse_qs(url.query).get('changedSince')):
      raise ValueError('Invalid MoySklad stock report URL')
    return self
