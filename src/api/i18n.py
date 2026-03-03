from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends

from src.core.database import get_db
from src.exceptions import JSRError
from src.models.locale_overrides import Locale, LocaleOverride
from src.schemas import I18nPatchResponse

router = APIRouter(prefix="/api/i18n", tags=["i18n"])


def _build_patch(overrides: list[LocaleOverride]) -> dict:
  patch: dict = {}

  for item in overrides:
    keys = [part for part in item.key.split(".") if part]
    if not keys:
      continue

    cursor = patch
    for key in keys[:-1]:
      node = cursor.get(key)
      if not isinstance(node, dict):
        node = {}
        cursor[key] = node
      cursor = node

    cursor[keys[-1]] = item.value

  return patch


@router.get("/{locale}", response_model=I18nPatchResponse)
async def get_i18n_patch(locale: str, session: AsyncSession = Depends(get_db)) -> dict:
  if locale not in {Locale.EN.value, Locale.RU.value}:
    raise JSRError("bad_request", message="Locale must be 'en' or 'ru'")

  rows = await LocaleOverride.all(session, locale=Locale(locale), is_active=True)
  return _build_patch(rows)
