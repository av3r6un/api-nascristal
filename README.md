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
- auth flow: register -> login -> me -> refresh

## Auth endpoints

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `GET /auth/me` (Bearer token)
