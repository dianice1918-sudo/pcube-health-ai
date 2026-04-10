# Launch Checklist

## 1. Rotate secrets
- Rotate Neon database password
- Rotate OpenAI API key
- Rotate Pinecone API key
- Rotate Twilio SID/auth token if exposed
- Rotate SMTP app password
- Rotate Google API key
- Rotate Firebase/service account credentials if exposed

## 2. Update production env
- Open [`.env.production`](./.env.production)
- Replace every `REPLACE_WITH_...` value
- Set `ALLOWED_HOSTS` to your real API domain
- Set `CORS_ALLOW_ORIGINS` to your real frontend domain
- Keep `DATABASE_URL` pointed at Neon/Postgres
- Set `RUN_STARTUP_SCHEMA_PATCHES=false`

## 3. Deployment files
- Make sure `service-account.json` exists in production if you use push notifications
- Or switch to env-based Firebase credentials before deploy
- Ensure your hosting platform loads `.env.production`, not local `.env`

## 4. Validate env and migrate
- Run `scripts/validate-production-env.ps1 -EnvFile .env.production`
- Run `scripts/run-migrations.ps1 -EnvFile .env.production`

## 5. Deploy
- Start backend with `docker compose -f docker-compose.production.yml up -d --build`
- On Render, trigger a fresh image rebuild so pinned auth dependencies are reinstalled
- Confirm the server can reach Neon over the network
- Confirm `/healthz` and `/readyz` both return 200

## 6. Smoke test
- Run `scripts/validate-live-deploy.ps1 -ApiBase https://api.yourdomain.com -EnvFile .env.production -IncludeAI`
- This now checks backend-hosted frontend routes too: `/app/`, `/app/login`, `/app/checker`, `/assets/style.css`
- If `LOGIN_OTP_ENABLED=true`, the automated script will stop after the pre-auth checks and tell you to complete the real OTP flow manually

## 7. Manual checks
- Sign up
- Login with a real delivered OTP code
- OTP email delivery
- Checker/chat
- Dashboard
- Refresh on `/app/login`, `/app/checker`, and `/app/dashboard`
- Open one page directly from the address bar instead of navigating from the homepage
- Any integrations you plan to advertise

## 8. Auth recovery
- If an older existing account still cannot log in after deploy, reset that account's password
- Treat "signup says already exists but login still fails" as a probable legacy-hash or stale-user issue, not a routing issue
- Check backend logs for the new auth diagnostics before changing code again

## 9. Only advertise what is configured
- No wearable credentials: do not advertise wearables
- No WhatsApp sender: do not advertise WhatsApp
- No weather/news keys: expect reduced intel features
