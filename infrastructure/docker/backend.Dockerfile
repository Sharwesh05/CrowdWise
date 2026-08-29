# CrowdWise API
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Build tooling for the few packages without wheels, plus curl for the health check.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first so a code change does not invalidate the install layer.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
# Prompt templates live at the repo root and are read at runtime.
COPY ai/ /app/ai/

# Run as a non-root user.
RUN useradd --create-home --shell /bin/bash crowdwise \
    && mkdir -p /app/storage \
    && chown -R crowdwise:crowdwise /app
USER crowdwise

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Migrations are NOT run automatically: schema changes stay an explicit,
# reviewable step (`alembic upgrade head`).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
