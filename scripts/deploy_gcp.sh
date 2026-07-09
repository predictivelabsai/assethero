#!/usr/bin/env bash
# Deploy the unified AssetHero web app (app.py) to Cloud Run.
#
# Prereqs: gcloud authed (`gcloud auth login`) with access to the project below.
# The marketing landing is DB-free and serves immediately; login + in-app
# features activate once the secrets in scripts/secrets.env.example are set
# (see the "Secrets" section at the bottom).
set -euo pipefail

PROJECT_ID="${ASSETHERO_GCP_PROJECT:-assethero-web-260709}"
REGION="${ASSETHERO_GCP_REGION:-europe-west2}"
SERVICE="${ASSETHERO_SERVICE:-assethero}"

echo "▸ Deploying $SERVICE to project=$PROJECT_ID region=$REGION"

gcloud run deploy "$SERVICE" \
  --source . \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 4

echo "▸ Done. URL:"
gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
  --format='value(status.url)'

# ── Secrets (run once you have values) ────────────────────────────────────
# Store each secret in Secret Manager, then attach to the service. Example:
#
#   printf '%s' "$DATABASE_URL"   | gcloud secrets create DATABASE_URL   --data-file=- --project "$PROJECT_ID"
#   printf '%s' "$ENCRYPTION_KEY" | gcloud secrets create ENCRYPTION_KEY --data-file=- --project "$PROJECT_ID"
#   printf '%s' "$JWT_SECRET"     | gcloud secrets create JWT_SECRET     --data-file=- --project "$PROJECT_ID"
#   printf '%s' "$GOOGLE_CLIENT_ID"     | gcloud secrets create GOOGLE_CLIENT_ID     --data-file=- --project "$PROJECT_ID"
#   printf '%s' "$GOOGLE_CLIENT_SECRET" | gcloud secrets create GOOGLE_CLIENT_SECRET --data-file=- --project "$PROJECT_ID"
#
#   gcloud run services update "$SERVICE" --project "$PROJECT_ID" --region "$REGION" \
#     --set-secrets=DATABASE_URL=DATABASE_URL:latest,ENCRYPTION_KEY=ENCRYPTION_KEY:latest,\
# JWT_SECRET=JWT_SECRET:latest,GOOGLE_CLIENT_ID=GOOGLE_CLIENT_ID:latest,GOOGLE_CLIENT_SECRET=GOOGLE_CLIENT_SECRET:latest
#
# For Google OAuth, add this service URL's /auth/callback as an authorized
# redirect URI in the GCP OAuth client (APIs & Services → Credentials).
