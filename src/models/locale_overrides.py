from datetime import datetime as dt
import enum

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import DateTime, Enum, Index, Integer, Boolean, JSON, String, func

from .base import Base


class Locale(enum.Enum):
  RU = "ru"
  EN = "en"


class LocaleOverride(Base):
  __table_args__ = (
    Index("uq_locale_overrides_locale_key", "locale", "key", unique=True),
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  locale: Mapped[Locale] = mapped_column(Enum(Locale), nullable=False, default=Locale.RU)
  key: Mapped[str] = mapped_column(String(255), nullable=False)
  value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON, nullable=True)
  is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")

  def __init__(self, locale: str, key_path: str, value_json, is_active: bool = True, **kwargs) -> None:
    self.locale = Locale(locale)
    self.key_path = key_path
    self.value_json = value_json
    self.is_active = is_active

  @property
  def json(self):
    return dict(id=self.id, locale=self.locale.value, key=self.key, value=self.value, is_active=self.is_active)

  async def deactivate(self, session):
    self.is_active = False
    await session.commit()
