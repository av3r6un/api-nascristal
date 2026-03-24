from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, JSON, String

from .base import Base


class ChangeEvent(Base):
  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
  payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
  actor_uid: Mapped[str | None] = mapped_column(String(6), nullable=True)

  def __init__(self, event_type: str, payload: dict | None = None, actor_uid: str | None = None, **kwargs) -> None:
    self.event_type = event_type
    self.payload = payload or {}
    self.actor_uid = actor_uid

  @property
  def json(self) -> dict:
    return {
      "id": self.id,
      "event_type": self.event_type,
      "payload": self.payload,
      "actor_uid": self.actor_uid,
      "created_ts": self.created_ts,
    }
