import json
from contextlib import asynccontextmanager
from time import perf_counter

from starlette.responses import Response
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.action_logging import get_actions_logger
from src.core.database import session_maker
from src.exceptions import JSRError
from src.utils.auth import extract_bearer_token, user_from_token
from src.api import routers
from src.exceptions.base import BaseError

@asynccontextmanager
async def lifespan(app: FastAPI):
  yield


app = FastAPI(title="nascrystal API", version="0.1.0", lifespan=lifespan)
_SUCCESS_WRAP_EXCLUDED_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
SECURED = '/api'
ACTION_LOGGING_PREFIXES = ("/api",)
actions_logger = get_actions_logger()


def _client_ip(request: Request) -> str:
  forwarded = request.headers.get("x-forwarded-for")
  if forwarded:
    return forwarded.split(",")[0].strip()
  return request.client.host if request.client else "0.0.0.0"


@app.middleware("http")
async def jwt_auth_middleware(request: Request, call_next):
  if request.method == "OPTIONS" or not request.url.path.startswith(SECURED):
    return await call_next(request)

  token = extract_bearer_token(request.headers.get("authorization"))
  if not token:
    return JSONResponse(status_code=401, content={"status": "error", "message": "unauthorized"})

  async with session_maker() as session:
    try:
      user = await user_from_token(token, session)
    except JSRError as exc:
      return JSONResponse(status_code=exc.status, content={"status": "error", "message": str(exc).lower()})

  request.state.user_uid = user.uid
  return await call_next(request)


@app.middleware("http")
async def success_response_wrapper(request: Request, call_next):
  response = await call_next(request)

  if request.url.path in _SUCCESS_WRAP_EXCLUDED_PATHS:
    return response

  content_type = response.headers.get("content-type", "")
  if response.status_code != 200 or "application/json" not in content_type:
    return response

  body_bytes = b""
  async for chunk in response.body_iterator:
    body_bytes += chunk

  if not body_bytes:
    payload = None
  else:
    try:
      payload = json.loads(body_bytes)
    except json.JSONDecodeError:
      # If the payload is not valid JSON, keep original payload unchanged.
      passthrough = Response(content=body_bytes, status_code=response.status_code, media_type=response.media_type)
      for key, value in response.headers.items():
        if key.lower() not in {"content-length", "content-type"}:
          passthrough.headers[key] = value
      return passthrough

  if isinstance(payload, dict) and payload.get("status") == "success" and "body" in payload:
    wrapped = payload
  else:
    wrapped = {"status": "success", "body": payload}

  wrapped_response = JSONResponse(status_code=response.status_code, content=wrapped)
  for key, value in response.headers.items():
    if key.lower() not in {"content-length", "content-type"}:
      wrapped_response.headers[key] = value
  return wrapped_response


@app.middleware("http")
async def actions_logging_middleware(request: Request, call_next):
  if not request.url.path.startswith(ACTION_LOGGING_PREFIXES):
    return await call_next(request)

  started_at = perf_counter()
  client_ip = _client_ip(request)
  path = str(request.url.path)
  if request.url.query:
    path = f"{path}?{request.url.query}"

  try:
    response = await call_next(request)
  except Exception:
    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    user_uid = getattr(request.state, "user_uid", None)
    actions_logger.exception(
      "method=%s path=%s status=500 duration_ms=%.2f ip=%s user_uid=%s",
      request.method,
      path,
      duration_ms,
      client_ip,
      user_uid or "-",
    )
    raise

  duration_ms = round((perf_counter() - started_at) * 1000, 2)
  user_uid = getattr(request.state, "user_uid", None)
  actions_logger.info(
    "method=%s path=%s status=%s duration_ms=%.2f ip=%s user_uid=%s",
    request.method,
    path,
    response.status_code,
    duration_ms,
    client_ip,
    user_uid or "-",
  )
  return response


@app.exception_handler(BaseError)
async def base_error_handler(request: Request, exc: BaseError):
  return JSONResponse(status_code=exc.status, content=exc.json)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
  if exc.status_code == 404:
    message = "not found"
  elif isinstance(exc.detail, str):
    message = exc.detail
  else:
    message = "error"
  return JSONResponse(status_code=exc.status_code, content={"status": "error", "message": message})


@app.get("/health")
async def health() -> dict[str, str]:
  return {"status": "ok"}

for r in routers:
  app.include_router(r)
  
