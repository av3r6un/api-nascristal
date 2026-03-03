from datetime import datetime as dt, timedelta as delta
import hashlib
import hmac

import bcrypt
import jwt

from src.core.config import settings

ALG = "HS256"


def hash_password(password: str) -> str:
  return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_pw(password: str, hash_value: str) -> bool:
  return bcrypt.checkpw(password.encode(), hash_value.encode())


def _create_token(user_uid: str, expired_delta: delta = delta(hours=1)) -> str:
  payload = dict(sub=user_uid, exp=dt.now() + expired_delta)
  return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALG)


def decode_token(token: str) -> dict:
  return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALG])


def create_token(user_uid: str, fresh: bool = True) -> str:
  exp_seconds = settings.JWT_TOKEN_EXPIRES if fresh else settings.JWT_REFRESH_TOKEN_EXPIRES
  return _create_token(user_uid, delta(seconds=int(exp_seconds)))


def hash_token(token: str) -> str:
  return hashlib.sha256(token.encode()).hexdigest()


def check_token(token: str, token_hash: str) -> bool:
  return hmac.compare_digest(hash_token(token), token_hash)
