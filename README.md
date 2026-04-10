# nascrystal API

## Stages

- `DEV`: uses SQLite (`sqlite+aiosqlite:///./dev.db`) and is intended for local work/tests.
- `PROD`: uses MySQL on `localhost:3306` by default.

`DB_URL` always has priority if explicitly provided.

## Run

```bash
uv sync
uv run uvicorn src.main:app --reload
```

Docs: `http://127.0.0.1:8000/docs`

## Docker

Build and run:

```bash
docker compose up --build -d
```

API entrypoint: `http://127.0.0.1:8000`

Scale API replicas:

```bash
docker compose up --build -d --scale api=3
```

Stop stack:

```bash
docker compose down
```

## Alembic (migrations)

Create migration:

```bash
uv run alembic revision --autogenerate -m "your message"
```

Apply latest migration:

```bash
uv run alembic upgrade head
```

Rollback one migration:

```bash
uv run alembic downgrade -1
```

PowerShell stage examples:

```powershell
$env:STAGE="DEV";  uv run alembic upgrade head
$env:STAGE="PROD"; uv run alembic upgrade head
```

## Tests (tiny pytest suite)

```bash
uv sync --group dev
uv run pytest -q
```

The suite covers:

- `GET /health`
- auth flow: register -> login -> refresh
- `GET /api/changes`

## Endpoints

Public:

- `GET /health`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`

Protected (`Bearer` token required for `/api/*`):

- `GET /api/catalog/`
- `GET /api/categories/{locale}`
- `GET /api/category/{uid}/{locale}`
- `POST /api/category`
- `GET /api/colors`
- `GET /api/color/{id}`
- `POST /api/color`
- `GET /api/sizes`
- `GET /api/size/{id}`
- `POST /api/size`
- `GET /api/warehouse/specs?locale=ru|en`
- `POST /api/feedback/`
- `GET /api/i18n/{locale}`
- `GET /api/settings/`
- `POST /api/settings/{key}`
- `GET /api/static/?locale=ru|en`
- `POST /api/static/`
- `GET /api/static/{slug}/{locale}`
- `GET /api/changes/?locale=en&limit=20`
- `GET /api/logs/`
- `GET /api/logs/?all`

Optional 1C exchange endpoints (`ONEC_ENABLED=1`):

- `GET /1c/1c_exchange?type=catalog&mode=checkauth`
- `GET /1c/1c_exchange?type=catalog&mode=init`
- `POST /1c/1c_exchange?type=catalog&mode=file&filename=import.xml`
- `GET /1c/1c_exchange?type=catalog&mode=import&filename=import.xml`

## Logging

- HTTP action log file: `logs/actions.log`
- `GET /api/logs/` returns the last 100 lines from the current log file
- `GET /api/logs/?all` returns the whole current log file
- Business change feed for frontend "last changes": `GET /api/changes/?locale=en&limit=20`

Compatibility note:

- `POST /auth/login` is the primary login endpoint
- `POST /auth` and `POST /auth/` are also accepted for backward compatibility
