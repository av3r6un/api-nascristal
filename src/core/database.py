from .config import settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.models.base import Base
import src.models  # Ensure all models are imported before metadata operations.

DATABASE_URL = settings.db_url

engine_kwargs: dict = dict(
  url=DATABASE_URL,
  echo=False,
)

# MySQL-specific pool/connect tuning. SQLite does not support these params.
if DATABASE_URL.startswith("mysql+"):
  engine_kwargs.update(
    connect_args=dict(connect_timeout=30),
    pool_recycle=3600,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
  )

engine = create_async_engine(**engine_kwargs)

session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def create_db():
  async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)


async def drop_db():
  async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.drop_all)


async def get_db():
  async with session_maker() as session:
    yield session
