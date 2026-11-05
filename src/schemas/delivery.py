from datetime import date, time
from decimal import Decimal
from typing import Literal
import re

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class StrictModel(BaseModel):
  model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Location(StrictModel):
  code: int = Field(gt=0)
  address: str | None = Field(default=None, min_length=1, max_length=255)
  country_code: Literal['RU'] = 'RU'


class Phone(StrictModel):
  number: str = Field(min_length=5, max_length=30)


class Contact(StrictModel):
  name: str = Field(min_length=1, max_length=255)
  phones: list[Phone] = Field(min_length=1, max_length=10)
  company: str | None = Field(default=None, min_length=1, max_length=255)
  contragent_type: Literal['INDIVIDUAL', 'LEGAL_ENTITY'] = 'INDIVIDUAL'
  tin: str | None = Field(default=None, max_length=12)
  email: str | None = Field(default=None, max_length=255)


def normalize_recipient(value):
  if not isinstance(value, dict):
    raise ValueError('Получатель должен быть объектом')
  result = dict(value)
  company_name = result.pop('company_name', None)
  if company_name is not None and 'company' in result and company_name != result['company']:
    raise ValueError('Переданы разные названия компании в company и company_name')
  result.setdefault('company', company_name)
  for key in ('company', 'tin'):
    item = result.get(key)
    if item is not None and not isinstance(item, str):
      raise ValueError('Название компании и ИНН должны передаваться строками')
    result[key] = (item.strip() or None) if item is not None else None
  kind = result.setdefault('contragent_type', 'INDIVIDUAL')
  if kind not in ('INDIVIDUAL', 'LEGAL_ENTITY'):
    raise ValueError('Тип получателя должен быть INDIVIDUAL или LEGAL_ENTITY')
  if kind == 'INDIVIDUAL' and (result['company'] or result['tin']):
    raise ValueError('У физического лица не должны быть заполнены реквизиты компании')
  if kind == 'LEGAL_ENTITY':
    if not result['company']:
      raise ValueError('Для получателя-компании укажите название компании')
    if not result['tin'] or not re.fullmatch(r'(?:[0-9]{10}|[0-9]{12})', result['tin']):
      raise ValueError('Для получателя-компании укажите ИНН из 10 или 12 цифр')
  return result


class Recipient(Contact):
  @model_validator(mode='before')
  @classmethod
  def validate_contragent(cls, value):
    return value if isinstance(value, cls) else normalize_recipient(value)


class Package(StrictModel):
  weight: int = Field(gt=0, le=1_000_000, description='Actual packed weight, grams')
  length: int = Field(gt=0, le=1000)
  width: int = Field(gt=0, le=1000)
  height: int = Field(gt=0, le=1000)


class CdekConfig(StrictModel):
  environment: Literal['test', 'production'] = 'test'
  webhooks_enabled: bool = False
  webhook_url: str | None = Field(default=None, max_length=2048)
  webhook_secret: SecretStr | None = Field(default=None, min_length=32)
  account: str | None = Field(default=None, min_length=1, max_length=255,
    json_schema_extra={'writeOnly': True})
  secure_password: SecretStr | None = None
  from_location: Location | None = None
  sender: Contact | None = None
  shipment_point: str | None = Field(default=None, min_length=1, max_length=30)
  estimated_unit_weight: int = Field(default=100, gt=0, le=100_000)
  estimated_length: int = Field(default=20, gt=0, le=1000)
  estimated_width: int = Field(default=15, gt=0, le=1000)
  estimated_height: int = Field(default=10, gt=0, le=1000)
  service_fee_enabled: bool = False
  service_fee: Decimal = Field(default=Decimal('200'), ge=0, le=100_000, decimal_places=2)

  @model_validator(mode='before')
  @classmethod
  def select_environment(cls, value):
    from src.core.config import settings
    if settings.STAGE != 'DEV' and isinstance(value, dict):
      return {**value, 'environment': 'production'}
    return value

  def stored(self):
    result = self.model_dump(mode='json')
    result['secure_password'] = self.secure_password.get_secret_value() if self.secure_password else None
    result['webhook_secret'] = self.webhook_secret.get_secret_value() if self.webhook_secret else None
    return result


class ModuleUpdate(StrictModel):
  enabled: bool
  config: dict


class PurchaseDelivery(StrictModel):
  module: str = Field(min_length=1, max_length=32)
  data: dict = Field(default_factory=dict)


class QuoteRequest(StrictModel):
  quantity: int = Field(gt=0, le=999)
  to_location: Location | None = None
  delivery_point: str | None = Field(default=None, min_length=1, max_length=30)
  tariff_code: int | None = Field(default=None, gt=0)


class ShipmentRequest(StrictModel):
  tariff_code: int | None = Field(default=None, gt=0)
  recipient: Recipient
  package: Package
  item_costs: dict[str, Decimal] | None = Field(default=None,
    description='Legacy input, ignored: paid prices come from the payment receipt')
  delivery_point: str | None = Field(default=None, min_length=1, max_length=30)
  to_location: Location | None = None
  delivery_cost: Decimal | None = Field(default=None, ge=0, le=1_000_000, decimal_places=2,
    description='Legacy input, ignored: delivery price is always recalculated by CDEK')
  reviewed_and_packed: Literal[True]
  recipient_collection_confirmed: Literal[True]

  @model_validator(mode='after')
  def destination(self):
    if bool(self.delivery_point) == bool(self.to_location):
      raise ValueError('Specify exactly one of delivery_point or to_location')
    if self.to_location and not self.to_location.address:
      raise ValueError('Courier destination requires address')
    return self


class IntakeRequest(StrictModel):
  intake_date: date
  intake_time_from: str = Field(pattern=r'^\d{2}:\d{2}$')
  intake_time_to: str = Field(pattern=r'^\d{2}:\d{2}$')

  @model_validator(mode='after')
  def interval(self):
    time.fromisoformat(self.intake_time_from)
    time.fromisoformat(self.intake_time_to)
    if not ('09:00' <= self.intake_time_from < self.intake_time_to <= '22:00'):
      raise ValueError('Invalid pickup interval')
    return self


class WidgetSelection(StrictModel):
  quantity: int = Field(gt=0, le=999)
  delivery_point: str | None = Field(default=None, min_length=1, max_length=30)
  address: str | None = Field(default=None, min_length=1, max_length=255)
  latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
  longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)

  @model_validator(mode='after')
  def destination(self):
    if self.delivery_point:
      if any(value is not None for value in (self.address, self.latitude, self.longitude)):
        raise ValueError('Specify either a pickup point or a courier address')
    elif self.address is None or self.latitude is None or self.longitude is None:
      raise ValueError('Courier delivery requires address and coordinates')
    return self
