# Deploying AssetHero (web) — Coolify

The unified web app is `app.py` (FastHTML). It binds to `$PORT` (falls back to
8080) on `0.0.0.0`, so it runs unchanged behind Coolify, Cloud Run, or plain Docker.
The marketing landing (`/`, `/asset-classes`, `/how-it-works`, `/pricing`,
`/contact`) is **database-free** and serves immediately; login and the in-app
chat shell activate once the secrets below are set.

## Coolify

1. **New Resource → Application → your Git repo** (branch `main`).
2. **Build Pack: Dockerfile** — Coolify uses the repo-root `Dockerfile`
   (builds `app.py`; the other `Dockerfile.*` files are for the API/AG-UI/legacy
   web and are ignored).
3. **Port**: set *Ports Exposes* to `8080` (the app reads `$PORT`; Coolify injects
   it and maps the domain to it).
4. **Environment variables** (see `scripts/secrets.env.example`):

   | Var | Needed for | Notes |
   |-----|-----------|-------|
   | `DATABASE_URL` | login, chat, backtests | PostgreSQL, `alpatrade` schema |
   | `ENCRYPTION_KEY` | per-user Alpaca keys | Fernet key — `python scripts/generate_keys.py` |
   | `JWT_SECRET` | API auth | same generator |
   | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | "Continue with Google" | optional; button auto-hides if unset |
   | `ALPACA_PAPER_API_KEY` / `ALPACA_PAPER_SECRET_KEY` | equities data/paper | optional at boot |

5. **Deploy.** Health-check path `/` (returns 200 without any secrets).

### Google OAuth
After the first deploy, add `https://<your-domain>/auth/callback` as an
authorized redirect URI on the OAuth 2.0 Client (GCP → APIs & Services →
Credentials), then set `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` and redeploy.

## Local Docker (parity check)

```bash
docker build -t assethero-web .
docker run --rm -p 8080:8080 -e PORT=8080 assethero-web
# open http://localhost:8080
```

## GCP Cloud Run (alternative)

`scripts/deploy_gcp.sh` deploys to Cloud Run. On a **brand-new** project the
first `gcloud run deploy --source` fails with `PERMISSION_DENIED` until the
default Cloud Build service account is granted the required roles
(`roles/cloudbuild.builds.builder` + storage access) — see
<https://cloud.google.com/run/docs/configuring/services/build-service-account>.
Coolify is the current primary target, so this path is kept only as a fallback.
