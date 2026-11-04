"""Validate exact offices, select a compatible tariff and calculate the current price."""
from decimal import Decimal, InvalidOperation

from src.exceptions import JSRError
from src.services.cdek_client import CdekClient, CdekError


def money(value):
  try:
    result = Decimal(str(value))
  except (InvalidOperation, TypeError, ValueError) as exc:
    raise CdekError('CDEK did not return a valid delivery price') from exc
  if not result.is_finite() or not 0 <= result <= 1_000_000:
    raise CdekError('CDEK did not return a valid delivery price')
  return result


async def point(client, code, package, *, sender=False):
  rows = await client.request('GET', '/v2/deliverypoints', params={
    'code': code, **{key: package[key] for key in ('length', 'width', 'height')}})
  office = next((row for row in rows if row.get('code') == code), None) if isinstance(rows, list) else None
  if not office or office.get('status') != 'ACTIVE' or not office.get('is_reception' if sender else 'is_handout'):
    raise JSRError('bad_request', message='Пункт СДЭК недоступен для приёма или выдачи этой посылки')
  if office.get('type') not in ('PVZ', 'POSTAMAT'):
    raise JSRError('bad_request', message='Неизвестный тип пункта СДЭК')
  weight = Decimal(package['weight']) / 1000
  low, high = office.get('weight_min'), office.get('weight_max')
  if (low is not None and weight <= Decimal(str(low))) or (high and weight > Decimal(str(high))):
    raise JSRError('bad_request', message='Вес посылки превышает ограничения пункта СДЭК')
  if office['type'] == 'POSTAMAT' and weight > 15:
    raise JSRError('bad_request', message='Вес посылки для постамата не должен превышать 15 кг')
  return office


async def calculate(config, package, *, to_location=None, delivery_point=None, tariff_code=None):
  if not config.from_location:
    raise JSRError(status=409, message='Sender city is not configured')
  request = dict(type=1, currency=1, packages=[package], from_location=config.from_location.model_dump(exclude_none=True))
  async with CdekClient(config) as client:
    origin = 'door'
    if config.shipment_point:
      office = await point(client, config.shipment_point, package, sender=True)
      if office.get('location', {}).get('city_code') != config.from_location.code:
        raise JSRError('bad_request', message='Пункт отправления не соответствует городу склада')
      origin = 'postamat' if office['type'] == 'POSTAMAT' else 'warehouse'
      request['shipment_point'] = config.shipment_point
    destination = 'door'
    if delivery_point:
      office = await point(client, delivery_point, package)
      city = office.get('location', {}).get('city_code')
      if not city:
        raise CdekError('CDEK point has no city code')
      destination = 'postamat' if office['type'] == 'POSTAMAT' else 'warehouse'
      request.update(delivery_point=delivery_point, to_location={'code': city})
    elif to_location:
      request['to_location'] = to_location.model_dump(exclude_none=True)
    else:
      raise JSRError('bad_request', message='Укажите пункт получения или адрес доставки')
    modes = {('door','door'):1, ('door','warehouse'):2, ('warehouse','door'):3,
      ('warehouse','warehouse'):4, ('door','postamat'):6, ('warehouse','postamat'):7,
      ('postamat','door'):8, ('postamat','warehouse'):9, ('postamat','postamat'):10}
    mode = modes[origin, destination]
    result = await client.request('POST', '/v2/calculator/tarifflist', json=request)
    tariffs = [row for row in result.get('tariff_codes', []) if row.get('delivery_mode') == mode
      and (tariff_code is None or row.get('tariff_code') == tariff_code)]
    if not tariffs:
      raise JSRError('bad_request', message='Нет доступного тарифа СДЭК для выбранного маршрута и упаковки')
    chosen = min(tariffs, key=lambda row: (money(row.get('delivery_sum')), row['tariff_code']))
    request['tariff_code'] = chosen['tariff_code']
    price = await client.request('POST', '/v2/calculator/tariff', json=request)
    return dict(tariff_code=chosen['tariff_code'], delivery_mode=mode, price=money(price.get('total_sum')),
      result=price, tariffs=tariffs)
