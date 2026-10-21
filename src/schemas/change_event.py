from pydantic import BaseModel
from uuid import UUID


class ChangeEventItem(BaseModel):
  id: int
  event_type: str
  payload: dict
  actor_uid: str | None
  created: str
  created_ts: int


class ChangeEventsResponse(BaseModel):
  items: list[ChangeEventItem]
  

class SyncUpdateItem(BaseModel):
  id: int
  entity_type: str
  entity_uuid: UUID
  action: str
  status: str
  entity_name: str
  updated_at: int


class LastUpdateResponse(BaseModel):
  last_update: int
  updates: list[SyncUpdateItem]
