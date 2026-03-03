# syntax=docker/dockerfile:1.7
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

CMD ["sh", "-c", "i=0; until uv run python -c \"import asyncio; import src.models; from src.core.database import create_db; asyncio.run(create_db())\"; do i=$((i+1)); if [ $i -ge 30 ]; then echo 'Schema creation failed after 30 attempts'; exit 1; fi; echo 'Waiting for database...'; sleep 2; done; exec uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 1"]
