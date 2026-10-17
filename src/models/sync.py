from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SyncTask(Base):
  __table_args__ = (
    UniqueConstraint('entity_type', 'entity_uuid', name='uq_sync_tasks_entity'),
    Index('ix_sync_tasks_status_updated', 'status', 'updated'),
    Base.__table_args__,
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  entity_type: Mapped[str] = mapped_column(String(32))
  entity_uuid: Mapped[UUID] = mapped_column(Uuid)
  action: Mapped[str] = mapped_column(String(16))
  status: Mapped[str] = mapped_column(String(16))
  request_id: Mapped[UUID] = mapped_column(Uuid)
  payload: Mapped[dict] = mapped_column(JSON)


class SyncAttempt(Base):
  __table_args__ = (
    Index('ix_sync_attempts_task_id', 'task_id'),
    Index('ix_sync_attempts_created', 'created'),
    Base.__table_args__,
  )

  id: Mapped[int] = mapped_column(Integer, primary_key=True)
  task_id: Mapped[int] = mapped_column(ForeignKey('sync_tasks.id'))
  status: Mapped[str] = mapped_column(String(16))
  error: Mapped[str | None] = mapped_column(Text)
