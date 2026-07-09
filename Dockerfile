# Unified AssetHero web app (app.py) — Coolify / Docker Compose.
# Binds to $PORT (default 8080) on 0.0.0.0. The marketing landing is DB-free and
# serves without any secrets; login + the chat shell activate once DATABASE_URL,
# ENCRYPTION_KEY, JWT_SECRET (and optionally GOOGLE_CLIENT_ID/SECRET) are set.
FROM python:3.13-slim

WORKDIR /app

# System deps for psycopg2 (+ common build needs).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1 \
    PORT=8090
EXPOSE 8090

# Health check so Coolify's zero-downtime deploy flips the new container green.
# Reads $PORT so it tracks whatever port compose sets.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:'+os.getenv('PORT','8090')+'/')" || exit 1

CMD ["python", "app.py"]
