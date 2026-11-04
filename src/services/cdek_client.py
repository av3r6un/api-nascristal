"""Bounded CDEK v2 transport. Writes are never retried automatically."""
import asyncio
from time import monotonic

import httpx

ERROR_MESSAGES = {
  'v2_orders_number_is_empty': 'СДЭК ещё не присвоил номер накладной. Обновите статус отправления перед печатью.',
  'v2_order_invalid': 'Регистрация отправления в СДЭК не подтверждена. Проверьте статус и ошибки регистрации.',
}

def errors_from(data):
  if not isinstance(data, dict):
    return []
  errors = list(data.get('errors') or [])
  for request in data.get('requests') or []:
    errors.extend(request.get('errors') or [])
  return [dict(code=str(error.get('code', 'unknown'))[:100],
    message=ERROR_MESSAGES.get(error.get('code'), str(error.get('message', 'CDEK rejected the request'))[:500]))
    for error in errors[:20] if isinstance(error, dict)]


class CdekError(Exception):
  def __init__(self, message='CDEK request failed', *, ambiguous=False, not_found=False, errors=None):
    super().__init__(message)
    self.ambiguous = ambiguous
    self.not_found = not_found
    self.errors = errors or []


class CdekClient:
  URLS = {'test': 'https://api.edu.cdek.ru', 'production': 'https://api.cdek.ru'}

  def __init__(self, config, *, transport=None):
    if not config.account or not config.secure_password or not config.secure_password.get_secret_value():
      raise CdekError('CDEK credentials are not configured')
    self.config = config
    self._http = httpx.AsyncClient(base_url=self.URLS[config.environment], timeout=20,
      follow_redirects=False, transport=transport)
    self._token = None
    self._expires = 0
    self._auth_lock = asyncio.Lock()

  async def __aenter__(self):
    return self

  async def __aexit__(self, *args):
    await self._http.aclose()

  async def _authorize(self):
    async with self._auth_lock:
      if self._token and monotonic() < self._expires:
        return
      try:
        response = await self._http.post('/v2/oauth/token', data={
          'grant_type': 'client_credentials', 'client_id': self.config.account,
          'client_secret': self.config.secure_password.get_secret_value()})
        response.raise_for_status()
        data = response.json()
        self._token = data['access_token']
        self._expires = monotonic() + max(0, int(data['expires_in']) - 30)
      except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise CdekError('CDEK authorization failed') from exc

  async def request(self, method, path, *, params=None, json=None, pdf=False):
    await self._authorize()
    write = method not in ('GET', 'HEAD')
    try:
      response = await self._http.request(method, path, params=params, json=json,
        headers={'Authorization': f'Bearer {self._token}'})
      # A rejected authorization has not performed the operation, so one reauth is safe.
      if response.status_code == 401:
        self._token = None
        await self._authorize()
        response = await self._http.request(method, path, params=params, json=json,
          headers={'Authorization': f'Bearer {self._token}'})
      response.raise_for_status()
      if pdf:
        if not response.content.startswith(b'%PDF-'):
          raise CdekError('CDEK document is not ready')
        return response.content
      data = response.json()
    except httpx.HTTPStatusError as exc:
      try:
        errors = errors_from(exc.response.json())
      except ValueError:
        errors = []
      raise CdekError(ambiguous=write and exc.response.status_code >= 500,
        not_found=exc.response.status_code == 404, errors=errors) from exc
    except (httpx.HTTPError, ValueError) as exc:
      raise CdekError(ambiguous=write) from exc
    if not isinstance(data, (dict, list)):
      raise CdekError('Invalid CDEK response', ambiguous=write)
    if isinstance(data, dict) and (data.get('errors') or (write and any(
      r.get('errors') or r.get('state') == 'INVALID' for r in data.get('requests', [])))):
      raise CdekError('CDEK rejected the request', errors=errors_from(data))
    return data
