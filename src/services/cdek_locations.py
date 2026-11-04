"""Bounded city search; never downloads the full directory."""
from time import monotonic
from src.services.cdek_client import CdekClient, CdekError
from src.services.integrations import configuration

_cache = {}

async def search_cities(session, name):
  _, config, _ = await configuration(session, require_enabled=True)
  key = (config.environment, config.account, name.strip().casefold())
  cached = _cache.get(key)
  if cached and cached[0] > monotonic():
    return cached[1]
  async with CdekClient(config) as client:
    rows = await client.request('GET', '/v2/location/suggest/cities',
      params={'name': name.strip(), 'country_code': 'RU'})
  if not isinstance(rows, list):
    raise CdekError('Invalid CDEK city search response')
  items = {}
  for row in rows:
    code = row.get('code')
    if not isinstance(code, int) or code <= 0 or row.get('country_code', 'RU') != 'RU':
      continue
    city, region = row.get('city', ''), row.get('region', '')
    items[code] = dict(id=str(code), code=code, city=city, region=region,
      region_code=row.get('region_code'), name=row.get('full_name') or (f'{city}, {region}' if region and region != city else city))
    if len(items) == 20:
      break
  result = list(items.values())
  if len(_cache) >= 512:
    _cache.pop(next(iter(_cache)))
  _cache[key] = (monotonic() + 600, result)
  return result
