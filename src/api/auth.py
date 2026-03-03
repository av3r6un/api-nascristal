from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from jwt import ExpiredSignatureError, PyJWTError
from src.core.database import get_db
from src.core.security import decode_token
from src.exceptions import JSRError
from src.models.user import User
from src.schemas import AuthResponse, LoginRequest, RefreshRequest, RefreshResponse, RegisterRequest, FeedbackResponse
from src.utils.auth import user_from_access_credentials

router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


def _client_ip(request: Request) -> str:
  # Minimal IP resolution: trust X-Forwarded-For first, fallback to direct client.
  forwarded = request.headers.get("x-forwarded-for")
  if forwarded:
    return forwarded.split(",")[0].strip()
  return request.client.host if request.client else "0.0.0.0"


@router.post("/register", response_model=FeedbackResponse, status_code=201)
async def register(payload: RegisterRequest, request: Request, session: AsyncSession = Depends(get_db)) -> dict[str, bool]:
  # Register is intentionally explicit: check conflict -> create uid -> save -> issue tokens.
  existing = await User.first(session, email=payload.email)
  if existing:
    raise JSRError("conflict", message="Email is already registered")

  uid = await User.create_uid(session)
  user = User(
    uid=uid,
    email=payload.email,
    password=payload.password,
    reg_ip=_client_ip(request),
    role=payload.role,
  )
  await user.save(session)
  return dict(processed=True)


@router.post("/", response_model=AuthResponse)
async def login(payload: LoginRequest, request: Request, session: AsyncSession = Depends(get_db)) -> dict[str, Any]:
  login_data = await User.login(session, payload.email, payload.password, _client_ip(request))
  return {"user": {"uid": login_data["uid"], "email": login_data["email"], "role": login_data["role"]}, "tokens": login_data["tokens"]}


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(payload: RefreshRequest, session: AsyncSession = Depends(get_db)) -> dict[str, str]:
  try:
    decoded = decode_token(payload.refresh_token)
  except ExpiredSignatureError as exc:
    raise JSRError("token_expired") from exc
  except PyJWTError as exc:
    raise JSRError("token_decode_error") from exc

  user = await User.first(session, uid=decoded.get("sub"))
  if not user:
    raise JSRError("unauthorized")

  return user.refresh()
