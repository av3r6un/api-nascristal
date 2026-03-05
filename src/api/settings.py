from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends

from src.core.database import get_db
from src.exceptions import JSRError
from src.models import Setting
from src.schemas import SettingsRequest

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get('/')
async def get_setting(session: AsyncSession = Depends(get_db)) -> dict:
  settings = await Setting.get_json(session)
  return {k: v for d in settings for k, v in d.items()}

@router.post('/{key}', status_code=200)
async def update_setting(key: str, payload: dict, session: AsyncSession = Depends(get_db)) -> dict:
  settings = await Setting.first(session, key=key)
  if not settings:
    settings = Setting(key, **payload)
    await settings.save(session)
  else:
    await settings.edit(session, key=key, **payload)
  return dict(processed=True)
