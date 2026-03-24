from pydantic import BaseModel


class ChangeEventItem(BaseModel):
  id: int
  action: str
  event_type: str
  payload: dict
  actor_uid: str | None
  created: str
  created_ts: int


class ChangeEventsResponse(BaseModel):
  items: list[ChangeEventItem]
