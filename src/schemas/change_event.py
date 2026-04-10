from pydantic import BaseModel


class ChangeEventItem(BaseModel):
  id: int
  event_type: str
  payload: dict
  actor_uid: str | None
  created: str
  created_ts: int


class ChangeEventsResponse(BaseModel):
  items: list[ChangeEventItem]
  

class LastUpdateResponse(BaseModel):
  last_update: int
