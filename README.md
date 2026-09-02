# nascrystal API

FastAPI backend for the nascrystal storefront and management panel.

## Stack and architecture

- FastAPI with async SQLAlchemy
- Alembic migrations
- SQLite for local development, MySQL for production
- MoySklad as the source of products, variants, sale prices and available stock
- Local database as the storefront catalog projection
- Local purchases and payments with YooKassa integration
- Product image metadata in the database; image objects in S3 and delivery through CDN

The storefront never calls MoySklad directly. Catalog data is imported into the
local `Product`, `ProductVariant`, `Offer`, `Attribute` and `ProductImage` models.
Categories are managed locally.

## Setup and run

Python 3.14+ and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --group dev
uv run uvicorn src.main:app --reload
```

- API: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/docs`
- Health check: `GET /health`

Configuration is read from `src/.env`. Important variables:

```dotenv
STAGE=DEV
DB_URL=sqlite+aiosqlite:///./dev.db
DB_USER=
DB_PASS=
DB_HOST=
DB_PORT=3306
DB_NAME=
SECRET_KEY=
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=
YOOKASSA_RETURN_URL=
```

`DB_URL` has priority over the stage-specific connection. Without it, `DEV`
uses SQLite and `PROD` builds a MySQL URL from `DB_USER`, `DB_PASS`, `DB_HOST`,
`DB_PORT` and `DB_NAME`.

## Database

```bash
# Apply migrations
uv run alembic upgrade head

# Generate a forward migration
uv run alembic revision --autogenerate -m "your message"
```

Existing migration files are immutable; schema changes are added as new forward
migrations.

## API contracts

Pydantic contracts live in `src/schemas/`; generated OpenAPI is the canonical
HTTP reference. Main endpoint groups:

- `/auth/*` — registration, login and token refresh
- `/api/moysklad/import` — manual MoySklad assortment import
- `/api/payments` — payments
- `/api/static`, `/api/i18n`, `/api/settings` — storefront content and settings
- `/api/feedback`, `/api/logs` — operations and diagnostics
- `/webhooks/yookassa` — YooKassa notifications

All `/api/*` routes require `Authorization: Bearer <access-token>`. Successful
JSON responses with status 200 use the common envelope:

```json
{"status": "success", "body": {}}
```

Errors use:

```json
{"status": "error", "message": "..."}
```

## MoySklad catalog import

`src/services/moysklad_import.py` provides composable async functions for:

- idempotent product and variant upserts;
- characteristics, sale price and available-stock synchronization;
- local category assignment;
- S3 object-key and primary-image metadata handling;
- explicit full-import archiving when it is safe to enable.

The service does not commit transactions itself. Callers should wrap a complete
import in `async with session.begin()` and keep `archive_missing=False` until
legacy catalog rows are mapped and verified.

## Tests and Docker

```bash
uv run python -m pytest -q
docker compose up --build -d
docker compose down
```

Action logs are written to `logs/actions.log`; sensitive request fields are
redacted.
