from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ChangeEvent


DEFAULT_CHANGE_LIMIT = 20


async def record_change(
  session: AsyncSession,
  event_type: str,
  payload: dict | None = None,
  actor_uid: str | None = None,
) -> ChangeEvent:
  event = ChangeEvent(event_type=event_type, payload=payload, actor_uid=actor_uid)
  await event.save(session)
  return event


async def fetch_recent_changes(session: AsyncSession, limit: int = DEFAULT_CHANGE_LIMIT) -> Sequence[ChangeEvent]:
  query = select(ChangeEvent).order_by(ChangeEvent.created.desc(), ChangeEvent.id.desc()).limit(limit)
  result = await session.execute(query)
  return result.scalars().all()
