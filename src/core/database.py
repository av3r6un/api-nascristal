from .config import settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url
import json
import sys
import tempfile
from pathlib import Path

DATABASE_URL = settings.db_url


def _running_under_pytest() -> bool:
  return "pytest" in sys.modules


def _path_is_under(path: Path, parent: Path) -> bool:
  try:
    path.relative_to(parent.resolve())
  except ValueError:
    return False
  return True


def _assert_pytest_database_url(database_url: str) -> None:
  parsed = make_url(database_url)
  if not parsed.drivername.startswith("sqlite"):
    raise RuntimeError("pytest blocked database access to a non-SQLite URL")

  if parsed.database in (None, "", ":memory:"):
    return

  repo_root = Path(__file__).resolve().parents[2]
  db_path = Path(parsed.database)
  if not db_path.is_absolute():
    db_path = repo_root / db_path
  db_path = db_path.resolve()

  allowed_roots = (
    (repo_root / ".pytest-tmp").resolve(),
    (repo_root / ".pytest-basetemp").resolve(),
    Path(tempfile.gettempdir()).resolve(),
  )
  if db_path == (repo_root / "test.db").resolve() or any(_path_is_under(db_path, root) for root in allowed_roots):
    return

  raise RuntimeError(f"pytest blocked database access to non-test SQLite file: {db_path}")


if _running_under_pytest():
  _assert_pytest_database_url(DATABASE_URL)

engine_kwargs: dict = dict(
  url=DATABASE_URL,
  echo=False,
  json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False, indent=2),
  json_deserializer=json.loads,
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

async def get_db():
  async with session_maker() as session:
    yield session
