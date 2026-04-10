# PCUBE Production Deployment

## Render deploy
If you deploy this repo to Render, keep the service rooted at `health-intel/` and use the Dockerfile in that folder.

Recommended Blueprint:
- `render.yaml` at the repo root
- `rootDir: health-intel`
- `dockerfilePath: ./Dockerfile`
- `dockerContext: .`

## Local single-server dev (frontend + API on same port)
1. Preferred: run the smart local launcher:
   ```powershell
   scripts/open-local.ps1
   ```
   It will detect if port `5500` is already occupied and move the app to the next free local port automatically.
2. If you want to start the API manually, stop Live Server first (it must not occupy the same port), then run:
   ```powershell
   scripts/run-local-5500.ps1
   ```
3. Open the backend-hosted app page, not a static `frontend/assets/*.html` URL:
   - `http://127.0.0.1:5500/healthz` (should return JSON)
   - `http://127.0.0.1:5500/app/login`

If `5500` is busy, `scripts/open-local.ps1` will choose another local app port such as `5501`, `5502`, `8000`, `8001`, or `8002`.

### Optional: autostart on Windows login
```powershell
scripts/install-local-autostart.ps1
```

To remove:
```powershell
scripts/uninstall-local-autostart.ps1
```

## LLM provider options
Set in `.env` and restart the API:

- OpenAI (default):
  - `LLM_PROVIDER=openai`
  - `OPENAI_API_KEY=...`
  - `OPENAI_CHAT_MODEL=gpt-4o-mini`

- Local Ollama:
  - Install Ollama and run: `ollama serve`
  - Pull a model: `ollama pull llama3.1:8b`
  - Set:
    - `LLM_PROVIDER=ollama`
    - `OLLAMA_MODEL=llama3.1:8b`
    - `OLLAMA_API_BASE=http://127.0.0.1:11434/api/chat`

- xAI Grok:
  - Create an xAI API key and add credits
  - Set:
    - `LLM_PROVIDER=xai`
    - `XAI_API_KEY=...`
    - `XAI_CHAT_MODEL=grok-4`
    - `XAI_API_BASE=https://api.x.ai/v1/chat/completions`

## 1) Prerequisites
- Docker Engine + Docker Compose plugin installed
- A server with ports `80/443` (for reverse proxy) and internal access to `8000` for API container
- Domain names:
  - API: `api.yourdomain.com`
  - Frontend app (if separate): `app.yourdomain.com`

## 2) Environment setup
1. Copy `.env.example` to `.env`.
2. Fill all required secrets:
   - `JWT_SECRET`
   - `DATABASE_URL` (or `DB_*` values)
   - `OPENAI_API_KEY` (if chatbot enabled)
   - SMTP/Twilio/Firebase credentials for notifications
3. Set production values:
   - `APP_ENV=production`
   - `ENABLE_DOCS=false` (recommended in production)
   - `ENABLE_DEMO_TOOLS=false`
   - `ALLOWED_HOSTS` with your real API host
   - `CORS_ALLOW_ORIGINS` with your real frontend origin
   - or `CORS_ALLOW_ORIGIN_REGEX` if you need a controlled wildcard during rollout
4. Generate a production-ready env file with fresh local secrets:
   ```powershell
   scripts/generate-production-env.ps1
   ```
   Then fill in the remaining real values in `.env.production`.

## 2a) Database strategy
- For shipping, use PostgreSQL.
- Recommended: managed/cloud PostgreSQL (Neon, RDS, Cloud SQL, Supabase, Railway Postgres, etc.).
- Acceptable alternative: self-hosted PostgreSQL on the same server/VPS if you are prepared to handle backups, upgrades, and monitoring.
- SQLite is now blocked in production by default.
- Set either:
  - `DATABASE_URL=postgresql+psycopg2://...`
  - or `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`

## 3) Validate env and run migrations
Before booting production, validate the filled env file:
```powershell
scripts/validate-production-env.ps1 -EnvFile .env.production
```

Run migrations explicitly:
```powershell
scripts/run-migrations.ps1 -EnvFile .env.production
```

## 4) Start production stack
Use the dedicated production compose file so the app reads `.env.production` and waits for migrations:
```bash
docker compose -f docker-compose.production.yml up -d --build
```

## 5) Validate health
```bash
docker compose -f docker-compose.production.yml ps
docker compose -f docker-compose.production.yml logs -f api
curl http://127.0.0.1:8000/healthz
curl http://127.0.0.1:8000/readyz
```

Expected:
- `/healthz` returns app status/version/environment
- `/readyz` returns database readiness

## 6) Smoke test
Run the automated smoke test after deploy:
```powershell
scripts/smoke-test.ps1 -ApiBase https://api.yourdomain.com
```

The smoke test now also verifies the backend-hosted frontend routes:
- `/app/`
- `/app/login`
- `/app/checker`
- `/assets/style.css`

If `LOGIN_OTP_ENABLED=true`, use:
```powershell
scripts/smoke-test.ps1 -ApiBase https://api.yourdomain.com -SkipProtectedRoutes
```
That confirms health, readiness, frontend serving, signup, and OTP challenge creation. Protected API checks remain manual until you enter a real delivered verification code.

Optional AI route check:
```powershell
scripts/smoke-test.ps1 -ApiBase https://api.yourdomain.com -IncludeAI
```

For the combined deploy check:
```powershell
scripts/validate-live-deploy.ps1 -ApiBase https://api.yourdomain.com -EnvFile .env.production -IncludeAI
```
If OTP is enabled in `.env.production`, `validate-live-deploy.ps1` now automatically switches to the pre-auth smoke path and leaves OTP completion as a manual step.

## 7) Scaling note (important)
- API service runs with multiple workers.
- Internal scheduler is disabled in API containers (`ENABLE_SCHEDULER=false`).
- Scheduler runs in dedicated `scheduler` service to avoid duplicate jobs.
- Production compose also disables startup schema patching (`RUN_STARTUP_SCHEMA_PATCHES=false`) so Alembic migrations are the source of truth.

## 8) Reverse proxy (recommended)
- Put Nginx/Caddy/Traefik in front of the API container.
- Terminate TLS at proxy.
- Forward requests to `api:8000`.

## 9) Backups and operations
- If you use self-hosted Postgres, PostgreSQL data is persisted in `postgres_data` volume.
- If you use Neon or another managed Postgres provider, configure provider backups and point `DATABASE_URL` at that managed instance.
- Back up DB regularly (daily snapshot minimum).
- Rotate secrets (`JWT_SECRET`, API keys, Twilio, SMTP, Firebase) periodically.
- Never commit populated production `.env` files or service account JSON files.
- If an older production account still fails login after deploy, reset the password before assuming the verifier code is broken. New signups and normalized-email auth should work with the updated backend.

## 10) Common commands
```bash
# Restart services
docker compose -f docker-compose.production.yml restart api scheduler

# Stop stack
docker compose -f docker-compose.production.yml down

# Stop stack and delete DB volume (dangerous)
docker compose down -v
```

## 11) Migration model
- Production now uses Alembic migrations in `migrations/`.
- Run `alembic upgrade head` or `scripts/run-migrations.ps1 -EnvFile .env.production` before starting app containers.
- The startup schema compatibility patches remain available for local/dev only and should stay disabled in production.
