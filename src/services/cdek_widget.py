"""Service contract of the official CDEK 4.x widget."""
from collections import OrderedDict
from time import monotonic

from pydantic import ValidationError

from src.exceptions import JSRError
from src.schemas.delivery import Package, Location, QuoteRequest
from src.services.cdek import estimated_package, quote
from src.services.cdek_client import CdekClient, CdekError
from src.services.cdek_routing import point
from src.services.integrations import configuration

_cache = OrderedDict()
VERSION = '4.1.0'


async def service(session, data):
  action = data.get('action')
  if action not in ('offices', 'byCoordinate', 'calculate'):
    raise JSRError('bad_request', message='Unknown widget action')
  _, config, _ = await configuration(session, require_enabled=True)
  if not config.from_location:
    raise JSRError(status=409, message='Sender city is not configured')
  try:
    if action == 'calculate':
      package = Package.model_validate(data['packages'][0]).model_dump()
      if len(data['packages']) != 1:
        raise ValueError()
      target = data['to_location']
      destination = {'country_code': 'RU'}
      if target.get('code'):
        destination['code'] = int(target['code'])
        if destination['code'] < 1:
          raise ValueError()
      elif isinstance(target.get('address'), str) and 1 <= len(target['address']) <= 255:
        destination['address'] = target['address']
      else:
        raise ValueError()
      async with CdekClient(config) as client:
        body = dict(type=1, currency=1, packages=[package], to_location=destination,
          from_location=config.from_location.model_dump(exclude_none=True))
        modes = (1, 2, 6)
        if config.shipment_point:
          origin = await point(client, config.shipment_point, package, sender=True)
          if origin.get('location', {}).get('city_code') != config.from_location.code:
            raise ValueError()
          modes = (8, 9, 10) if origin['type'] == 'POSTAMAT' else (3, 4, 7)
          body['shipment_point'] = config.shipment_point
        result = await client.request('POST', '/v2/calculator/tarifflist', json=body)
      return {'tariff_codes': [row for row in result.get('tariff_codes', []) if row.get('delivery_mode') in modes]}
    params = {'type': data.get('type', 'ALL')}
    if params['type'] not in ('ALL', 'PVZ', 'POSTAMAT'):
      raise ValueError()
    for key in ('have_cashless', 'have_cash', 'is_dressing_room', 'allowed_cod'):
      if data.get(key) is not None:
        value = str(data[key]).lower()
        if value not in ('0', '1', 'true', 'false'):
          raise ValueError()
        params[key] = value
    path = '/v2/deliverypoints'
    if action == 'byCoordinate':
      path += '/byPolygons'
      for key in ('latitude_right_top', 'latitude_left_bottom', 'longitude_right_top', 'longitude_left_bottom'):
        value = float(data[key])
        bound = 90 if key.startswith('latitude') else 180
        if not -bound <= value <= bound:
          raise ValueError()
        params[key] = round(value, 6)
      lat = params['latitude_right_top'] - params['latitude_left_bottom']
      lon = params['longitude_right_top'] - params['longitude_left_bottom']
      if lat <= 0 or lon <= 0:
        raise ValueError()
      if lat > 10 or lon > 10:
        return []
    else:
      params.update(country_code='RU', is_handout='true', size=1000,
        city_code=int(data.get('city_code') or config.from_location.code))
      if params['city_code'] < 1:
        raise ValueError()
      if data.get('code'):
        if not isinstance(data['code'], str) or len(data['code']) > 30:
          raise ValueError()
        params['code'] = data['code']
        params.pop('city_code')
      params['page'] = int(data.get('page') or 0)
      params['size'] = min(1000, max(1, int(data.get('size') or 1000)))
      if not 0 <= params['page'] <= 100:
        raise ValueError()
  except (KeyError, TypeError, ValueError, ValidationError, IndexError) as exc:
    raise JSRError('bad_request', message='Invalid widget parameters') from exc
  key = (config.environment, config.account, path, tuple(sorted(params.items())))
  cached = _cache.get(key)
  if cached and cached[0] > monotonic():
    return cached[1]
  async with CdekClient(config) as client:
    rows = await client.request('GET', path, params=params)
  if isinstance(rows, dict):
    rows = rows.get('delivery_points', rows.get('items', []))
  rows = [row for row in rows if row.get('status') == 'ACTIVE' and row.get('is_handout')
    and row.get('location', {}).get('country_code') == 'RU'][:1000]
  _cache[key] = (monotonic() + 300, rows)
  _cache.move_to_end(key)
  while len(_cache) > 32:
    _cache.popitem(last=False)
  return rows


async def selection(session, payload):
  _, config, _ = await configuration(session, require_enabled=True)
  data = {}
  if payload.delivery_point:
    data['delivery_point'] = payload.delivery_point
  else:
    async with CdekClient(config) as client:
      city = await client.request('GET', '/v2/location/coordinates',
        params={'latitude': payload.latitude, 'longitude': payload.longitude})
      if (not isinstance(city, dict) or not isinstance(city.get('code'), int) or city['code'] <= 0
        or not isinstance(city.get('city'), str) or not city['city']):
        raise CdekError('CDEK did not resolve the destination city')
      # Coordinates must resolve to a Russian city before accepting the address.
      cities = await client.request('GET', '/v2/location/cities', params={'code': city['code'], 'country_codes': 'RU', 'size': 1})
    if not isinstance(cities, list) or not any(row.get('country_code') == 'RU' and row.get('code') == city['code'] for row in cities):
      raise JSRError('bad_request', message='Доступна доставка только по России')
    data.update(to_location=Location(code=city['code'], address=payload.address).model_dump(),
      city_name=city['city'])
  result = await quote(session, QuoteRequest(quantity=payload.quantity, **{
    key: value for key, value in data.items() if key in ('delivery_point', 'to_location')}))
  data.update(tariff_code=result['tariff_code'], package=result['package'],
    delivery_cost=result['result']['total_sum'])
  return {'module': 'cdek', 'data': data}
