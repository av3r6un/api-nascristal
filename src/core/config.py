from pathlib import Path
from typing import Literal
import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
  STAGE: Literal["DEV", "PROD"] = os.getenv('STAGE')
  DB_URL: str | None = None

  DB_USER: str
  DB_PASS: str
  DB_HOST: str
  DB_PORT: int
  DB_NAME: str

  SECRET_KEY: str = "change-me"
  JWT_TOKEN_EXPIRES: int = 86400
  JWT_REFRESH_TOKEN_EXPIRES: int = 604800

  model_config = SettingsConfigDict(
    # src/core/config.py -> src/.env
    env_file=Path(__file__).resolve().parents[1] / ".env",
    extra="ignore",
  )

  @property
  def db_url(self) -> str:
    if self.DB_URL:
      return self.DB_URL
    if self.STAGE == "DEV":
      return "sqlite+aiosqlite:///./dev.db"
    return f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


settings = Settings()
