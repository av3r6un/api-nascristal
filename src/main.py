import json
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any

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
BODY_LOG_PREVIEW_LIMIT = 500
BODY_LOG_CAPTURE_LIMIT = 64 * 1024
SENSITIVE_BODY_KEYS = {"authorization", "password", "token", "access_token", "refresh_token" }
PUBLIC_API_ROUTES = {
  ("POST", "/api/purchases"),
  ("POST", "/api/purchases/"),
}


def _is_public_api_route(method: str, path: str) -> bool:
  if (method, path) in PUBLIC_API_ROUTES:
    return True
  return method == "GET" and path.startswith("/api/purchases/by-uuid/")


def _client_ip(request: Request) -> str:
  forwarded = request.headers.get("x-forwarded-for")
  if forwarded:
    return forwarded.split(",")[0].strip()
  return request.client.host if request.client else "0.0.0.0"


def _path_with_query(request: Request) -> str:
  path = str(request.url.path)
  if request.url.query:
    path = f"{path}?{request.url.query}"
  return path


def _sanitize_log_payload(payload: Any) -> Any:
  if isinstance(payload, dict):
    return {
      key: "***" if str(key).lower() in SENSITIVE_BODY_KEYS else _sanitize_log_payload(value)
      for key, value in payload.items()
    }
  if isinstance(payload, list):
    return [_sanitize_log_payload(item) for item in payload]
  return payload


def _short_body(body: bytes, content_type: str) -> str:
  if not body:
    return "-"

  if "application/json" in content_type:
    try:
      payload = _sanitize_log_payload(json.loads(body))
      preview = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except (UnicodeDecodeError, json.JSONDecodeError):
      preview = body.decode("utf-8", errors="replace")
  elif content_type.startswith("text/"):
    preview = body.decode("utf-8", errors="replace")
  else:
    return f"<{len(body)} bytes>"

  preview = " ".join(preview.split())
  if len(preview) > BODY_LOG_PREVIEW_LIMIT:
    return f"{preview[:BODY_LOG_PREVIEW_LIMIT]}...<{len(body)} bytes>"
  return preview


def _can_capture_body(response: Response) -> bool:
  content_type = response.headers.get("content-type", "")
  if "application/json" not in content_type and not content_type.startswith("text/"):
    return False

  content_length = response.headers.get("content-length")
  if content_length is None:
    return True
  try:
    return int(content_length) <= BODY_LOG_CAPTURE_LIMIT
  except ValueError:
    return False


async def _restore_request_body(request: Request, body: bytes) -> None:
  async def receive() -> dict:
    return {"type": "http.request", "body": body, "more_body": False}

  request._receive = receive


@app.middleware("http")
async def jwt_auth_middleware(request: Request, call_next):
  if request.method == "OPTIONS" or not request.url.path.startswith(SECURED):
    return await call_next(request)

  if _is_public_api_route(request.method, request.url.path):
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
  path = _path_with_query(request)
  request_body = await request.body()
  await _restore_request_body(request, request_body)
  request_content_type = request.headers.get("content-type", "")
  actions_logger.info(
    "incoming method=%s path=%s ip=%s user_uid=%s body=%s",
    request.method,
    path,
    client_ip,
    getattr(request.state, "user_uid", None) or "-",
    _short_body(request_body, request_content_type),
  )

  try:
    response = await call_next(request)
  except Exception:
    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    user_uid = getattr(request.state, "user_uid", None)
    actions_logger.exception(
      "outgoing method=%s path=%s status=500 duration_ms=%.2f ip=%s user_uid=%s body=-",
      request.method,
      path,
      duration_ms,
      client_ip,
      user_uid or "-",
    )
    raise

  duration_ms = round((perf_counter() - started_at) * 1000, 2)
  user_uid = getattr(request.state, "user_uid", None)
  response_content_type = response.headers.get("content-type", "")
  response_body_preview = "-"

  if _can_capture_body(response):
    response_body = b""
    async for chunk in response.body_iterator:
      response_body += chunk

    response_body_preview = _short_body(response_body, response_content_type)
    passthrough = Response(
      content=response_body,
      status_code=response.status_code,
      media_type=response.media_type,
    )
    for key, value in response.headers.items():
      if key.lower() != "content-length":
        passthrough.headers[key] = value
    response = passthrough

  actions_logger.info(
    "outgoing method=%s path=%s status=%s duration_ms=%.2f ip=%s user_uid=%s body=%s",
    request.method,
    path,
    response.status_code,
    duration_ms,
    client_ip,
    user_uid or "-",
    response_body_preview,
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
  
