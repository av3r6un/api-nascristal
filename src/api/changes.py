from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.change_logging import DEFAULT_CHANGE_LIMIT, fetch_recent_changes
from src.core.database import get_db
from src.schemas import ChangeEventsResponse


router = APIRouter(prefix="/api/changes", tags=["changes"])


@router.get("/", response_model=ChangeEventsResponse, status_code=200)
async def get_recent_changes(
  limit: int = DEFAULT_CHANGE_LIMIT,
  session: AsyncSession = Depends(get_db),
) -> dict[str, list[dict]]:
  limit = max(1, min(limit, 100))
  events = await fetch_recent_changes(session, limit=limit)
  print(events)
  return {"items": [event.json for event in events]}
