# Planning Suite API — Hugging Face Spaces (Docker SDK) at root
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860 \
    APP_ENV=production

WORKDIR /app

# System libraries: Postgres (psycopg2), build tools, R runtime (pyreadr / 6w RDS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    r-base-core \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/app ./app
COPY backend/core ./core
COPY backend/features ./features
COPY backend/scripts ./scripts

# Writable artifact dirs (synced from Google Drive at startup when STORAGE_BACKEND=drive)
RUN mkdir -p data/outputs/sheets_cache data/outputs/cache data/masters data/dp_logics data/analytics data/ff_inputs data/raw_actuals

COPY backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
