from collections import deque

from fastapi import APIRouter, Request

from src.core.action_logging import LOG_FILE_PATH


router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/", status_code=200)
async def get_logs(request: Request) -> dict[str, list[str]]:
  if not LOG_FILE_PATH.exists():
    return {"items": []}

  read_all = "all" in request.query_params

  with LOG_FILE_PATH.open("r", encoding="utf-8") as file:
    if read_all:
      lines = [line.rstrip("\n") for line in file]
    else:
      lines = [line.rstrip("\n") for line in deque(file, maxlen=100)]

  return {"items": lines}
