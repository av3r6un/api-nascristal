from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Request

from src.core.change_logging import record_change
from src.core.database import get_db
from src.exceptions import JSRError
from src.models import Setting
from src.models.settings import SettingsKeys
from src.schemas import SettingsRequest

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get('/')
async def get_setting(session: AsyncSession = Depends(get_db)) -> dict:
  settings = await Setting.get_json(session)
  return {k: v for d in settings for k, v in d.items()}

@router.post('/{key}', status_code=200)
async def update_setting(key: str, payload: dict, request: Request, session: AsyncSession = Depends(get_db)) -> dict:
  actor_uid = getattr(request.state, "user_uid", None)
  if key not in {sk.value for sk in SettingsKeys}: raise JSRError()
  settings = await Setting.first(session, key=SettingsKeys(key).name)
  if not settings:
    settings = Setting(key, **payload)
    await settings.save(session)
    await record_change(session, "settings.created", payload={"key": key}, actor_uid=actor_uid)
  else:
    await settings.edit(session, key=SettingsKeys(key).name, **payload)
    await record_change(session, "settings.updated", payload={"key": key}, actor_uid=actor_uid)
  return dict(processed=True)
