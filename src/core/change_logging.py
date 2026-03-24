from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ChangeEvent


DEFAULT_CHANGE_LIMIT = 20
SUPPORTED_CHANGE_LOCALES = {"ru", "en"}
CHANGE_EVENT_TEMPLATES = {
  "ru": {
    "settings.created": '\u0421\u043e\u0437\u0434\u0430\u043d\u0430 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430 "{key}"',
    "settings.updated": '\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0430 \u043d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430 "{key}"',
    "static.page.created": '\u0421\u043e\u0437\u0434\u0430\u043d\u0430 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u0430 "{slug}"',
    "static.page.updated": '\u041e\u0431\u043d\u043e\u0432\u043b\u0435\u043d\u0430 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u0430 "{slug}" \u0434\u043b\u044f \u043b\u043e\u043a\u0430\u043b\u0438 "{locale}"',
    "static.page.status_changed": '\u0418\u0437\u043c\u0435\u043d\u0435\u043d \u0441\u0442\u0430\u0442\u0443\u0441 \u0441\u0442\u0440\u0430\u043d\u0438\u0446\u044b "{slug}" \u043d\u0430 "{status}"',
    "auth.user.registered": '\u0417\u0430\u0440\u0435\u0433\u0438\u0441\u0442\u0440\u0438\u0440\u043e\u0432\u0430\u043d \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c "{email}"',
  },
  "en": {
    "settings.created": 'Setting "{key}" was created',
    "settings.updated": 'Setting "{key}" was updated',
    "static.page.created": 'Page "{slug}" was created',
    "static.page.updated": 'Page "{slug}" was updated for locale "{locale}"',
    "static.page.status_changed": 'Page "{slug}" status changed to "{status}"',
    "auth.user.registered": 'User "{email}" was registered',
  },
}


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


def render_change(event: ChangeEvent, locale: str) -> dict:
  target_locale = locale if locale in SUPPORTED_CHANGE_LOCALES else "en"
  template = CHANGE_EVENT_TEMPLATES[target_locale].get(event.event_type, event.event_type)
  payload = event.payload or {}

  try:
    action = template.format(**payload)
  except (KeyError, ValueError):
    action = template

  return {
    "id": event.id,
    "action": action,
    "event_type": event.event_type,
    "payload": payload,
    "actor_uid": event.actor_uid,
    "created": event.created.isoformat(),
    "created_ts": event.created_ts,
  }
