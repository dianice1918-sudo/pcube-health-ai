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
- Confirm the server can reach Neon over the network
- Confirm `/healthz` and `/readyz` both return 200

## 6. Smoke test
- Run `scripts/validate-live-deploy.ps1 -ApiBase https://api.yourdomain.com -EnvFile .env.production -IncludeAI`

## 7. Manual checks
- Sign up
- Login
- OTP email delivery
- Checker/chat
- Dashboard
- Any integrations you plan to advertise

## 8. Only advertise what is configured
- No wearable credentials: do not advertise wearables
- No WhatsApp sender: do not advertise WhatsApp
- No weather/news keys: expect reduced intel features
