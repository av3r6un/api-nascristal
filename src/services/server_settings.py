from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import Setting
from src.models.settings import SettingsKeys


class ServerSettings:
  _values: dict[str, Any] = {}

  @classmethod
  async def load(cls, session: AsyncSession) -> None:
    settings = (await session.execute(select(Setting))).scalars().all()
    cls._values = {setting.key.value: setting.value for setting in settings}

  @classmethod
  def get(cls, key: SettingsKeys | str, default: Any = None) -> Any:
    name = key.value if isinstance(key, SettingsKeys) else key
    return cls._values.get(name, default)

  @classmethod
  def update(cls, key: SettingsKeys | str, value: Any) -> None:
    name = key.value if isinstance(key, SettingsKeys) else key
    cls._values = {**cls._values, name: value}
