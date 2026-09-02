from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any
from urllib.parse import urlparse

import httpx

from src.core.config import settings


class MoySkladError(Exception):
  """Ошибка ответа MoySklad с сохранением HTTP-кода и деталей API."""

  def __init__(self, status_code: int, message: str, errors: list[dict[str, Any]] | None = None) -> None:
    super().__init__(message)
    self.status_code = status_code
    self.errors = errors or []


class MoySkladClient:
  BASE_URL = "https://api.moysklad.ru/api/remap/1.2"

  def __init__(self, *, timeout: float = 30.0) -> None:
    if not settings.MOYSKLAD_TOKEN:
      raise ValueError("MoySklad token is required")
    self._http = httpx.AsyncClient(
      base_url=self.BASE_URL,
      timeout=timeout,
      headers={
        "Authorization": f"Bearer {settings.MOYSKLAD_TOKEN}",
        "Accept": "application/json;charset=utf-8",
        "Accept-Encoding": "gzip",
        "Content-Type": "application/json",
      },
    )

  async def __aenter__(self) -> MoySkladClient:
    return self

  async def __aexit__(self, *_: object) -> None:
    await self._http.aclose()

  async def request(
    self,
    method: str,
    path: str,
    *,
    params: Mapping[str, Any] | None = None,
    payload: Any = None,
  ) -> dict[str, Any] | list[Any] | None:
    """Выполнить произвольный запрос к API и разобрать JSON-ответ."""
    self._check_url(path)
    response = await self._http.request(method, path, params=params, json=payload)

    if response.is_error:
      raise self._make_error(response)
    if response.status_code == 204 or not response.content:
      return None
    try:
      return response.json()
    except ValueError as exc:
      raise MoySkladError(response.status_code, "MoySklad returned invalid JSON") from exc

  async def get(self, path: str, **params: Any) -> dict[str, Any] | list[Any] | None:
    return await self.request("GET", path, params=params or None)

  async def create(self, entity: str, payload: Any) -> dict[str, Any] | list[Any] | None:
    return await self.request("POST", f"/entity/{entity}", payload=payload)

  async def update(
    self,
    entity: str,
    entity_id: str,
    payload: Any,
  ) -> dict[str, Any] | list[Any] | None:
    return await self.request("PUT", f"/entity/{entity}/{entity_id}", payload=payload)

  async def delete(self, entity: str, entity_id: str) -> None:
    await self.request("DELETE", f"/entity/{entity}/{entity_id}")

  async def iter_entities(
    self,
    entity: str,
    *,
    limit: int = 1000,
    **params: Any,
  ) -> AsyncIterator[dict[str, Any]]:
    """Получать все страницы списка через ссылку ``meta.nextHref``."""
    if not 1 <= limit <= 1000:
      raise ValueError("limit must be between 1 and 1000")

    path: str | None = f"/entity/{entity}"
    query: Mapping[str, Any] | None = {**params, "limit": limit}
    while path:
      result = await self.request("GET", path, params=query)
      if not isinstance(result, dict) or not isinstance(result.get("rows"), list):
        raise MoySkladError(200, "Expected a collection with a rows array")

      for row in result["rows"]:
        if isinstance(row, dict):
          yield row

      meta = result.get("meta")
      path = meta.get("nextHref") if isinstance(meta, dict) else None
      query = None

  def _check_url(self, path: str) -> None:
    """Не позволяет отправить Bearer-токен на посторонний хост."""
    parsed = urlparse(path)
    if parsed.scheme and parsed.netloc != urlparse(self.BASE_URL).netloc:
      raise ValueError("Refusing to send MoySklad token to an external host")

  @staticmethod
  def _make_error(response: httpx.Response) -> MoySkladError:
    errors: list[dict[str, Any]] = []
    try:
      body = response.json()
      raw_errors = body.get("errors", []) if isinstance(body, dict) else []
      errors = [item for item in raw_errors if isinstance(item, dict)]
    except ValueError:
      pass

    messages = [str(item.get("error") or item.get("error_message") or "") for item in errors]
    message = "; ".join(filter(None, messages))
    if not message:
      message = response.text.strip() or f"MoySklad HTTP {response.status_code}"
    return MoySkladError(response.status_code, message, errors)
