"""Implementations live in memory. Only user-saved connection settings live in SQL."""
from dataclasses import dataclass
import asyncio
import secrets
from types import MappingProxyType

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.exceptions import JSRError
from src.models.delivery import IntegrationConfig
from src.schemas.delivery import CdekConfig, normalize_recipient
from src.services.cdek_client import CdekClient, CdekError


@dataclass(frozen=True)
class ModuleDefinition:
  code: str
  name: str
  config_schema: type
  capabilities: tuple[str, ...]
  type: str


MODULES = MappingProxyType({
  'cdek': ModuleDefinition('cdek', 'СДЭК', CdekConfig,
    ('quote', 'delivery_points', 'shipments', 'tracking', 'documents', 'courier'), 'delivery'),
})


def definition(code: str) -> ModuleDefinition:
  if code not in MODULES:
    raise JSRError('not_found', message='Unknown integration module')
  return MODULES[code]


async def delivery_selection(session, value):
  if value is None:
    return None
  module = definition(value.module)
  row = await session.get(IntegrationConfig, value.module)
  if module.type != 'delivery' or row is None or not row.enabled:
    raise JSRError('bad_request', message='Delivery module is not enabled')
  result = value.model_dump(mode='json')
  if 'recipient' in result['data']:
    try:
      result['data']['recipient'] = normalize_recipient(result['data']['recipient'])
    except ValueError as exc:
      raise JSRError('bad_request', message=str(exc)) from exc
  return result


async def configuration(session: AsyncSession, code: str = 'cdek', *, require_enabled=False):
  module = definition(code)
  row = await session.get(IntegrationConfig, code)
  if row is not None:
    enabled, raw = row.enabled, row.config
  else:
    enabled, raw = False, {}
  try:
    config = module.config_schema.model_validate(raw)
  except ValidationError as exc:
    raise JSRError(status=503, message='Invalid integration configuration') from exc
  if require_enabled:
    if not enabled:
      raise JSRError(status=409, message='Integration is disabled')
    assert_ready(config)
  return enabled, config, row is not None


def assert_ready(config: CdekConfig):
  if not config.account or not config.secure_password or not config.secure_password.get_secret_value():
    raise JSRError(status=503, message='CDEK credentials are not configured')


def describe(module, enabled, config, saved):
  data = config.stored()
  data.pop('secure_password', None)
  data.pop('account', None)
  data.pop('webhook_secret', None)
  return dict(code=module.code, name=module.name, type=module.type, enabled=enabled,
    configured=bool(config.account and config.secure_password), source='database' if saved else 'defaults',
    capabilities=module.capabilities, config=data,
    environment_selectable=settings.STAGE == 'DEV',
    account_configured=bool(config.account), secure_password_configured=bool(config.secure_password),
    webhook_secret_configured=bool(config.webhook_secret),
    config_schema=module.config_schema.model_json_schema(),
    delivery_payment_mode='recipient_collection_under_sender_contract')


async def save_configuration(session, code, payload):
  module = definition(code)
  # Null/omitted secret values preserve the current values, allowing masked UI edits.
  previous_row = await session.get(IntegrationConfig, code)
  previous_raw = previous_row.config if previous_row else {}
  # Panel edits may contain only the fields that changed.
  raw = dict(previous_raw) | payload.config
  for key in ('account', 'secure_password', 'webhook_secret'):
    if raw.get(key) is None:
      raw[key] = previous_raw.get(key)
  if raw.get('webhook_url') and not raw.get('webhook_secret'):
    raw['webhook_secret'] = secrets.token_urlsafe(32)
  try:
    config = module.config_schema.model_validate(raw)
  except ValidationError as exc:
    raise JSRError('bad_request', message='Invalid integration settings') from exc
  if payload.enabled:
    assert_ready(config)
  if code == 'cdek' and (config.stored() != previous_raw or (payload.enabled and (not previous_row or not previous_row.enabled))):
    await check_cdek_connection(config)
  row = await session.get(IntegrationConfig, code)
  if row is None:
    row = IntegrationConfig(code=code)
    session.add(row)
  row.enabled, row.config = payload.enabled, config.stored()
  await session.commit()
  return describe(module, row.enabled, config, True)


async def check_cdek_connection(config):
  assert_ready(config)
  try:
    async with asyncio.timeout(25), CdekClient(config) as client:
      params = {'code': config.from_location.code} if config.from_location else {'size': 1}
      cities = await client.request('GET', '/v2/location/cities', params=params)
      if not isinstance(cities, list) or not cities:
        raise JSRError('bad_request', message='CDEK origin city was not found')
      if config.from_location and not any(c.get('code') == config.from_location.code for c in cities):
        raise JSRError('bad_request', message='CDEK origin city was not found')
      if config.shipment_point:
        points = await client.request('GET', '/v2/deliverypoints', params={'code': config.shipment_point})
        point = next((p for p in points if p.get('code') == config.shipment_point), None) if isinstance(points, list) else None
        if not point:
          raise JSRError('bad_request', message=f'CDEK shipment point {config.shipment_point} not found in {config.environment} environment')
        city_code = point.get('location', {}).get('city_code')
        if config.from_location and city_code != config.from_location.code:
          raise JSRError('bad_request', message=f'CDEK shipment point city {city_code} does not match origin city {config.from_location.code}')
  except (CdekError, TimeoutError) as exc:
    raise JSRError(status=502, message='CDEK connection check failed; settings were not saved') from exc
