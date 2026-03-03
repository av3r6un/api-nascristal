from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from src.core.security import decode_token
from src.exceptions import JSRError
from src.models.user import User


def extract_bearer_token(authorization: str | None) -> str | None:
  if not authorization:
    return None
  if not authorization.startswith("Bearer "):
    return None
  token = authorization.split(" ", 1)[1].strip()
  return token or None


async def user_from_token(token: str, session: AsyncSession) -> User:
  try:
    payload = decode_token(token)
  except jwt.ExpiredSignatureError as exc:
    raise JSRError("token_expired") from exc
  except jwt.PyJWTError as exc:
    raise JSRError("token_decode_error") from exc

  uid = payload.get("sub")
  if not uid:
    raise JSRError("token_decode_error")

  user = await User.first(session, uid=uid)
  if not user:
    raise JSRError("unauthorized")

  return user


async def user_from_access_credentials(
  credentials: HTTPAuthorizationCredentials | None,
  session: AsyncSession,
) -> User:
  if not credentials:
    raise JSRError("unauthorized")
  return await user_from_token(credentials.credentials, session)
