# Unified AssetHero web app (app.py) — Cloud Run.
# Binds to $PORT (Cloud Run injects 8080). The marketing landing is DB-free and
# serves without any secrets; login/app features activate once DATABASE_URL,
# ENCRYPTION_KEY, JWT_SECRET (and optionally GOOGLE_CLIENT_ID/SECRET) are set.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "app.py"]
