import logging
import os
import time
import json
import base64
import binascii
import hmac
import hashlib
import secrets
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict, deque
from typing import List

from fastapi import FastAPI, Depends, HTTPException, Request, Header, Response, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import func, inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import DATABASE_URL, engine, get_db
from app.dependencies import get_current_user
from app.explain import explain_risk
from app.forecast import linear_forecast
from app.models import (
    ApiKey,
    Base,
    ChatMessage,
    DailyPlanCheck,
    HealthRecord,
    LoginVerificationCode,
    NutritionLog,
    OAuthState,
    PushDevice,
    RiskHistory,
    ShareLink,
    StepSensorState,
    Tenant,
    User,
    UserNotification,
    WearableConnection,
    WebhookEndpoint,
)
from app.risk_history import user_risk_summary
from app.schemas import (
    AdminSystemStatsOut,
    AdminUserRiskOut,
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    AssistantFileOut,
    AssistantFilesResponse,
    AssistantFileUploadResponse,
    ChatAskRequest,
    ChatAskImageRequest,
    ChatAskResponse,
    ChatLoopRequest,
    ChatLoopResponse,
    ChatMessageOut,
    CoachSummaryOut,
    DailyPlanOut,
    DailyTaskOut,
    DailyTaskUpdate,
    DashboardOut,
    DemoSeedOut,
    EngagementOut,
    ForecastOut,
    HealthIngestResponse,
    HealthRecordCreate,
    HealthRecordOut,
    LoginCodeChallengeOut,
    LoginCodeVerifyIn,
    LiveIntelOut,
    MedicationPlanRequest,
    MedicationPlanResponse,
    NutritionLogCreate,
    NutritionLogOut,
    NutritionPlanRequest,
    NutritionPlanResponse,
    NutritionSummaryOut,
    NotificationOut,
    NotificationStatusUpdate,
    OAuthStartOut,
    PeerInsightItem,
    CommunityInsightsResponse,
    PushTokenOut,
    PushTokenRegister,
    RiskHistoryOut,
    ShareLinkCreate,
    ShareLinkOut,
    StepSyncRequest,
    StepSyncResponse,
    TenantCreate,
    TenantPlanUpdate,
    TenantOut,
    TrendOut,
    UserCreate,
    UserLocationOut,
    UserLocationPermissionUpdate,
    UserLocationUpdate,
    UserLogin,
    WearableConnectionOut,
    WearableConnectRequest,
    WearableSyncRequest,
    WearableSyncResponse,
    WebhookCreate,
    WebhookOut,
    WebhookSecretRotateOut,
)
from app.security import create_access_token, hash_password, verify_password
from app.services.alert_engine import should_trigger_alert
from app.services.alert_dispatcher import process_risk_alert
from app.services.email_service import send_email
from app.services.llm_chat import (
    ask_llm,
    list_pinecone_assistant_files,
    pinecone_supported_file_extensions,
    upload_pinecone_assistant_file,
)
from app.services.live_intel import collect_live_intel, fetch_weather_and_air
from app.services.nutrition_support import build_nutrition_summary
from app.services.peer_insights import build_peer_insights
from app.services.push_service import send_push_notification
from app.services.risk_engine import calculate_risk, classify_risk
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.wellness_advisor import (
    activity_tip as build_activity_tip,
    environment_tips as build_environment_tips,
    hydration_tip,
    outbreak_alerts as build_outbreak_alerts,
)
from app.trend_analysis import risk_trend


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: str = "") -> List[str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        raw = default
    return [item.strip() for item in raw.split(",") if item.strip()]


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
APP_VERSION = os.getenv("APP_VERSION", "1.0.0").strip() or "1.0.0"
ENABLE_DOCS = _env_bool("ENABLE_DOCS", APP_ENV != "production")
ENABLE_SCHEDULER = _env_bool("ENABLE_SCHEDULER", True)
RUN_STARTUP_SCHEMA_PATCHES = _env_bool("RUN_STARTUP_SCHEMA_PATCHES", APP_ENV != "production")
DEFAULT_DEV_CORS = "http://127.0.0.1:5500,http://localhost:5500,http://127.0.0.1:5501,http://localhost:5501,http://127.0.0.1:5502,http://localhost:5502,http://127.0.0.1:8000,http://localhost:8000"

app = FastAPI(
    title="PCUBE Health API",
    version=APP_VERSION,
    docs_url="/docs" if ENABLE_DOCS else None,
    redoc_url="/redoc" if ENABLE_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_DOCS else None,
)
logger = logging.getLogger("pcube")
logging.basicConfig(level=logging.INFO)
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))
ENABLE_DEMO_TOOLS = os.getenv("ENABLE_DEMO_TOOLS", "false").strip().lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = _env_csv("ALLOWED_HOSTS", "localhost,127.0.0.1")
if APP_ENV != "production":
    ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ORIGINS = _env_csv("CORS_ALLOW_ORIGINS", DEFAULT_DEV_CORS if APP_ENV != "production" else "")
CORS_ALLOW_ORIGIN_REGEX = (os.getenv("CORS_ALLOW_ORIGIN_REGEX") or "").strip()
CORS_ALLOW_METHODS = _env_csv("CORS_ALLOW_METHODS", "GET,POST,PUT,PATCH,DELETE,OPTIONS")
CORS_ALLOW_HEADERS = _env_csv("CORS_ALLOW_HEADERS", "*")
CORS_ALLOW_CREDENTIALS = _env_bool("CORS_ALLOW_CREDENTIALS", True)
if APP_ENV != "production":
    for local_origin in [
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:5501",
        "http://localhost:5501",
        "http://127.0.0.1:5502",
        "http://localhost:5502",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ]:
        if local_origin not in CORS_ALLOW_ORIGINS:
            CORS_ALLOW_ORIGINS.append(local_origin)
_request_window = defaultdict(deque)
PLAN_DEFAULTS = {
    "FREE": {"daily_record_limit": 10, "monthly_alert_limit": 20, "monthly_chat_limit": 20, "monthly_image_chat_limit": 0},
    "PRO": {"daily_record_limit": 200, "monthly_alert_limit": 500, "monthly_chat_limit": 400, "monthly_image_chat_limit": 40},
    "ENTERPRISE": {"daily_record_limit": 5000, "monthly_alert_limit": 20000, "monthly_chat_limit": 5000, "monthly_image_chat_limit": 500},
}
DEFAULT_WEBHOOK_EVENTS = {"health_record.ingested", "risk.alert_triggered"}
SUPPORTED_WEARABLES = {"google_fit", "apple_health", "fitbit"}
SUPPORTED_PUSH_PROVIDERS = {"fcm"}
SUPPORTED_STEP_SENSORS = {"STEP_COUNTER", "STEP_DETECTOR", "ACCELEROMETER"}
NOTIFICATION_STATUSES = {"NEW", "RESOLVED", "SNOOZED"}
DAILY_TASK_KEYS = {"hydrate_goal", "step_goal", "mindful_break"}
LOGIN_OTP_ENABLED = _env_bool("LOGIN_OTP_ENABLED", True)
LOGIN_OTP_TTL_MINUTES = max(2, int(os.getenv("LOGIN_OTP_TTL_MINUTES", "10")))
LOGIN_OTP_DIGITS = min(8, max(4, int(os.getenv("LOGIN_OTP_DIGITS", "6"))))
LOGIN_OTP_MAX_ATTEMPTS = min(10, max(3, int(os.getenv("LOGIN_OTP_MAX_ATTEMPTS", "5"))))
LOGIN_OTP_MAX_ISSUES_PER_10_MIN = min(20, max(3, int(os.getenv("LOGIN_OTP_MAX_ISSUES_PER_10_MIN", "6"))))
LOGIN_OTP_REQUIRED_DETAIL = "OTP verification required for this account. Use /login/request-code then /login/verify-code."
PRIORITY_USER_EMAILS = {"dianice1918@gmail.com"}
PRIORITY_USER_CHAT_LIMIT = 5000
PRIORITY_USER_IMAGE_CHAT_LIMIT = 500

if ALLOWED_HOSTS and "*" not in ALLOWED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
if CORS_ALLOW_ORIGINS or CORS_ALLOW_ORIGIN_REGEX:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_origin_regex=CORS_ALLOW_ORIGIN_REGEX or None,
        allow_credentials=CORS_ALLOW_CREDENTIALS,
        allow_methods=CORS_ALLOW_METHODS or ["*"],
        allow_headers=CORS_ALLOW_HEADERS or ["*"],
    )
app.add_middleware(GZipMiddleware, minimum_size=1024)


def _validate_runtime_config() -> None:
    if APP_ENV != "production":
        return

    jwt_secret = (os.getenv("JWT_SECRET") or "").strip()
    if len(jwt_secret) < 32 or "replace-with-strong-random-secret" in jwt_secret.lower():
        raise RuntimeError("Production JWT_SECRET is missing or too weak.")

    if DATABASE_URL.startswith("sqlite"):
        raise RuntimeError("SQLite is not allowed in production. Configure PostgreSQL before launch.")

    non_local_hosts = [host for host in ALLOWED_HOSTS if host not in {"localhost", "127.0.0.1"}]
    if not non_local_hosts:
        raise RuntimeError("ALLOWED_HOSTS must include your real production host.")

    non_local_cors = [
        origin
        for origin in CORS_ALLOW_ORIGINS
        if "localhost" not in origin and "127.0.0.1" not in origin
    ]
    if not non_local_cors and not CORS_ALLOW_ORIGIN_REGEX:
        raise RuntimeError(
            "Set CORS_ALLOW_ORIGINS or CORS_ALLOW_ORIGIN_REGEX for your real frontend origin."
        )

    if LOGIN_OTP_ENABLED:
        smtp_required = [
            (os.getenv("SMTP_HOST") or "").strip(),
            (os.getenv("SMTP_USER") or "").strip(),
            (os.getenv("SMTP_PASS") or "").strip(),
        ]
        if not all(smtp_required):
            raise RuntimeError(
                "LOGIN_OTP_ENABLED is true, but SMTP settings are incomplete for production."
            )


def _is_admin(user: User) -> bool:
    admins = [email.strip().lower() for email in os.getenv("ADMIN_EMAILS", "").split(",") if email.strip()]
    return bool(user.email and user.email.lower() in admins)


def _require_admin(user: User) -> None:
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")


def _effective_chat_limits(tenant: Tenant, user: User) -> tuple[int, int]:
    base_chat_limit = int(tenant.monthly_chat_limit or 0)
    base_image_limit = int(tenant.monthly_image_chat_limit or 0)
    email = (getattr(user, "email", "") or "").strip().lower()
    if email in PRIORITY_USER_EMAILS:
        return (
            max(base_chat_limit, PRIORITY_USER_CHAT_LIMIT),
            max(base_image_limit, PRIORITY_USER_IMAGE_CHAT_LIMIT),
        )
    return base_chat_limit, base_image_limit


def _public_provider_error_message(default_message: str) -> str:
    return default_message


def _risk_scores_for_user(db: Session, user_id: int) -> List[float]:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return []
    records = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == user_id, HealthRecord.tenant_id == user.tenant_id)
        .order_by(HealthRecord.record_date)
        .all()
    )
    scores: List[float] = []
    for record in records:
        score = calculate_risk(record)
        if score is not None:
            scores.append(float(score))
    return scores


def _risk_series_for_user(db: Session, user: User) -> List[tuple[str, float]]:
    records = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == user.id, HealthRecord.tenant_id == user.tenant_id)
        .order_by(HealthRecord.record_date)
        .all()
    )
    points: List[tuple[str, float]] = []
    for record in records:
        score = calculate_risk(record)
        if score is not None:
            points.append((record.record_date.isoformat(), float(score)))
    return points


def _build_trend_svg(points: List[tuple[str, float]]) -> str:
    width = 860
    height = 340
    pad_left = 60
    pad_right = 20
    pad_top = 20
    pad_bottom = 55
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    if not points:
        return (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>"
            "<rect width='100%' height='100%' fill='#ffffff'/>"
            "<text x='50%' y='50%' text-anchor='middle' fill='#334155' font-size='12' font-family='Arial'>"
            "No trend data yet"
            "</text></svg>"
        )

    scores = [p[1] for p in points]
    min_y = min(0.0, min(scores) - 0.05)
    max_y = max(1.0, max(scores) + 0.05)
    y_range = max(max_y - min_y, 0.01)

    def px(i: int) -> float:
        if len(points) == 1:
            return pad_left + plot_w / 2
        return pad_left + (i / (len(points) - 1)) * plot_w

    def py(v: float) -> float:
        return pad_top + (max_y - v) / y_range * plot_h

    polyline = " ".join([f"{px(i):.1f},{py(v):.1f}" for i, (_, v) in enumerate(points)])
    circles = "".join(
        [
            f"<circle cx='{px(i):.1f}' cy='{py(v):.1f}' r='4' fill='#0ea5e9'/>"
            for i, (_, v) in enumerate(points)
        ]
    )
    x_labels = "".join(
        [
            (
                f"<text x='{px(i):.1f}' y='{height-18}' text-anchor='middle' fill='#475569' "
                f"font-size='10' font-family='Arial'>{d}</text>"
                if i in {0, len(points) - 1} or len(points) <= 6
                else ""
            )
            for i, (d, _) in enumerate(points)
        ]
    )
    y_ticks = []
    for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
        y = py(t)
        y_ticks.append(
            f"<line x1='{pad_left}' y1='{y:.1f}' x2='{width-pad_right}' y2='{y:.1f}' stroke='#e2e8f0'/>"
            f"<text x='{pad_left-8}' y='{y+4:.1f}' text-anchor='end' fill='#475569' font-size='10' font-family='Arial'>{t:.2f}</text>"
        )

    latest = points[-1][1]
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}'>"
        "<rect width='100%' height='100%' fill='#ffffff'/>"
        f"<text x='{pad_left}' y='16' fill='#0f172a' font-size='14' font-family='Arial'>Risk Trend (Latest: {latest:.2f})</text>"
        + "".join(y_ticks)
        + f"<line x1='{pad_left}' y1='{height-pad_bottom}' x2='{width-pad_right}' y2='{height-pad_bottom}' stroke='#64748b'/>"
        + f"<line x1='{pad_left}' y1='{pad_top}' x2='{pad_left}' y2='{height-pad_bottom}' stroke='#64748b'/>"
        + f"<polyline points='{polyline}' fill='none' stroke='#0ea5e9' stroke-width='3'/>"
        + circles
        + x_labels
        + "</svg>"
    )


def _ensure_multitenancy_schema() -> None:
    if engine.dialect.name == "sqlite":
        return
    statements = [
        "CREATE TABLE IF NOT EXISTS tenants (id SERIAL PRIMARY KEY, name VARCHAR(255) UNIQUE NOT NULL, created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW() NOT NULL)",
        "ALTER TABLE tenants ALTER COLUMN created_at SET DEFAULT NOW()",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS subscription_tier VARCHAR(20)",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS daily_record_limit INTEGER",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS monthly_alert_limit INTEGER",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS monthly_chat_limit INTEGER",
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS monthly_image_chat_limit INTEGER",
        "UPDATE tenants SET created_at = NOW() WHERE created_at IS NULL",
        "UPDATE tenants SET subscription_tier = 'FREE' WHERE subscription_tier IS NULL",
        "UPDATE tenants SET daily_record_limit = 10 WHERE daily_record_limit IS NULL",
        "UPDATE tenants SET monthly_alert_limit = 20 WHERE monthly_alert_limit IS NULL",
        "UPDATE tenants SET monthly_chat_limit = 20 WHERE monthly_chat_limit IS NULL",
        "UPDATE tenants SET monthly_image_chat_limit = 0 WHERE monthly_image_chat_limit IS NULL",
        "INSERT INTO tenants (name, created_at, subscription_tier, daily_record_limit, monthly_alert_limit, monthly_chat_limit, monthly_image_chat_limit) VALUES ('default', NOW(), 'FREE', 10, 20, 20, 0) ON CONFLICT (name) DO NOTHING",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS tenant_id INTEGER",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS location_permission_granted BOOLEAN",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS location_label VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS location_updated_at TIMESTAMP WITHOUT TIME ZONE",
        "UPDATE users SET location_permission_granted = FALSE WHERE location_permission_granted IS NULL",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS tenant_id INTEGER",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS steps_count INTEGER",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS activity_minutes INTEGER",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS resting_heart_rate DOUBLE PRECISION",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS hydration_liters DOUBLE PRECISION",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS city VARCHAR(255)",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS weather_condition VARCHAR(255)",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS temperature_c DOUBLE PRECISION",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS uv_index DOUBLE PRECISION",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS aqi INTEGER",
        "ALTER TABLE risk_history ADD COLUMN IF NOT EXISTS tenant_id INTEGER",
        "ALTER TABLE risk_predictions ADD COLUMN IF NOT EXISTS tenant_id INTEGER",
        "ALTER TABLE risk_history ADD COLUMN IF NOT EXISTS alert_triggered BOOLEAN",
        "UPDATE risk_history SET alert_triggered = FALSE WHERE alert_triggered IS NULL",
        "CREATE TABLE IF NOT EXISTS api_keys (id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL, name VARCHAR(255) NOT NULL, key_prefix VARCHAR(255) NOT NULL, key_hash VARCHAR(255) UNIQUE NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE, last_used_at TIMESTAMP WITHOUT TIME ZONE NULL, created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW())",
        "CREATE TABLE IF NOT EXISTS webhook_endpoints (id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL, url VARCHAR(1024) NOT NULL, events_csv VARCHAR(1024) NOT NULL DEFAULT 'health_record.ingested,risk.alert_triggered', signing_secret VARCHAR(255) NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW())",
        "CREATE TABLE IF NOT EXISTS chat_messages (id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL, llm_model VARCHAR(255) NULL, prompt_tokens INTEGER NULL, completion_tokens INTEGER NULL, created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW())",
        "CREATE TABLE IF NOT EXISTS nutrition_logs (id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER NOT NULL, entry_date DATE NOT NULL, meal_type VARCHAR(40) NULL, calories INTEGER NULL, water_liters DOUBLE PRECISION NULL, symptoms TEXT NULL, goals TEXT NULL, notes TEXT NULL, created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW())",
        "CREATE TABLE IF NOT EXISTS push_devices (id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER NOT NULL, provider VARCHAR(32) NOT NULL DEFAULT 'fcm', platform VARCHAR(32) NOT NULL, device_label VARCHAR(255) NULL, push_token TEXT NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(), last_seen_at TIMESTAMP WITHOUT TIME ZONE NULL)",
        "CREATE TABLE IF NOT EXISTS wearable_connections (id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER NOT NULL, provider VARCHAR(64) NOT NULL, external_user_id VARCHAR(255) NULL, access_token TEXT NULL, refresh_token TEXT NULL, scope VARCHAR(1024) NULL, token_expires_at TIMESTAMP WITHOUT TIME ZONE NULL, last_sync_at TIMESTAMP WITHOUT TIME ZONE NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW())",
        "CREATE TABLE IF NOT EXISTS daily_plan_checks (id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER NOT NULL, plan_date DATE NOT NULL, task_key VARCHAR(255) NOT NULL, completed BOOLEAN NOT NULL DEFAULT FALSE, updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(), CONSTRAINT uq_daily_plan_check UNIQUE (user_id, plan_date, task_key))",
        "CREATE TABLE IF NOT EXISTS user_notifications (id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER NOT NULL, event_type VARCHAR(255) NOT NULL, title VARCHAR(255) NOT NULL, message TEXT NOT NULL, severity VARCHAR(20) NOT NULL DEFAULT 'INFO', status VARCHAR(20) NOT NULL DEFAULT 'NEW', metadata_json TEXT NULL, created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(), resolved_at TIMESTAMP WITHOUT TIME ZONE NULL, snoozed_until TIMESTAMP WITHOUT TIME ZONE NULL)",
        "CREATE TABLE IF NOT EXISTS share_links (id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER NOT NULL, token VARCHAR(255) NOT NULL UNIQUE, lookback_days INTEGER NOT NULL DEFAULT 30, expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(), last_accessed_at TIMESTAMP WITHOUT TIME ZONE NULL)",
        "CREATE TABLE IF NOT EXISTS oauth_states (id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER NOT NULL, provider VARCHAR(64) NOT NULL, state VARCHAR(255) NOT NULL UNIQUE, code_verifier VARCHAR(255) NULL, expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, is_used BOOLEAN NOT NULL DEFAULT FALSE, created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW())",
        "CREATE TABLE IF NOT EXISTS login_verification_codes (id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER NOT NULL, challenge_id VARCHAR(255) NOT NULL UNIQUE, code_hash VARCHAR(255) NOT NULL, expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 5, is_used BOOLEAN NOT NULL DEFAULT FALSE, delivery_channel VARCHAR(64) NOT NULL DEFAULT 'email', created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(), consumed_at TIMESTAMP WITHOUT TIME ZONE NULL)",
        "ALTER TABLE login_verification_codes ADD COLUMN IF NOT EXISTS tenant_id INTEGER",
        "ALTER TABLE login_verification_codes ADD COLUMN IF NOT EXISTS user_id INTEGER",
        "ALTER TABLE login_verification_codes ADD COLUMN IF NOT EXISTS challenge_id VARCHAR(255)",
        "ALTER TABLE login_verification_codes ADD COLUMN IF NOT EXISTS code_hash VARCHAR(255)",
        "ALTER TABLE login_verification_codes ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITHOUT TIME ZONE",
        "ALTER TABLE login_verification_codes ADD COLUMN IF NOT EXISTS attempts INTEGER",
        "ALTER TABLE login_verification_codes ADD COLUMN IF NOT EXISTS max_attempts INTEGER",
        "ALTER TABLE login_verification_codes ADD COLUMN IF NOT EXISTS is_used BOOLEAN",
        "ALTER TABLE login_verification_codes ADD COLUMN IF NOT EXISTS delivery_channel VARCHAR(64)",
        "ALTER TABLE login_verification_codes ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITHOUT TIME ZONE",
        "ALTER TABLE login_verification_codes ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMP WITHOUT TIME ZONE",
        "UPDATE login_verification_codes SET attempts = 0 WHERE attempts IS NULL OR attempts < 0",
        "UPDATE login_verification_codes SET max_attempts = 5 WHERE max_attempts IS NULL OR max_attempts < 1",
        "UPDATE login_verification_codes SET is_used = FALSE WHERE is_used IS NULL",
        "UPDATE login_verification_codes SET delivery_channel = 'email' WHERE delivery_channel IS NULL OR LENGTH(TRIM(delivery_channel)) = 0",
        "UPDATE login_verification_codes SET created_at = NOW() WHERE created_at IS NULL",
        "ALTER TABLE login_verification_codes ALTER COLUMN tenant_id SET NOT NULL",
        "ALTER TABLE login_verification_codes ALTER COLUMN user_id SET NOT NULL",
        "ALTER TABLE login_verification_codes ALTER COLUMN challenge_id SET NOT NULL",
        "ALTER TABLE login_verification_codes ALTER COLUMN code_hash SET NOT NULL",
        "ALTER TABLE login_verification_codes ALTER COLUMN expires_at SET NOT NULL",
        "ALTER TABLE login_verification_codes ALTER COLUMN attempts SET NOT NULL",
        "ALTER TABLE login_verification_codes ALTER COLUMN max_attempts SET NOT NULL",
        "ALTER TABLE login_verification_codes ALTER COLUMN is_used SET NOT NULL",
        "ALTER TABLE login_verification_codes ALTER COLUMN delivery_channel SET NOT NULL",
        "ALTER TABLE login_verification_codes ALTER COLUMN created_at SET NOT NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_login_verification_codes_challenge_id ON login_verification_codes (challenge_id)",
        "CREATE INDEX IF NOT EXISTS ix_login_verification_codes_user_id ON login_verification_codes (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_login_verification_codes_tenant_id ON login_verification_codes (tenant_id)",
        "CREATE TABLE IF NOT EXISTS step_sensor_states (id SERIAL PRIMARY KEY, tenant_id INTEGER NOT NULL, user_id INTEGER NOT NULL, device_id VARCHAR(120) NOT NULL, sensor_type VARCHAR(40) NOT NULL DEFAULT 'STEP_COUNTER', timezone_name VARCHAR(64) NULL, last_boot_id VARCHAR(120) NULL, baseline_date DATE NULL, baseline_total_since_boot BIGINT NULL, last_total_since_boot BIGINT NULL, daily_steps INTEGER NOT NULL DEFAULT 0, last_sync_mode VARCHAR(50) NULL, algorithm_version VARCHAR(60) NULL, confidence DOUBLE PRECISION NULL, last_event_at TIMESTAMP WITHOUT TIME ZONE NULL, created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(), updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(), CONSTRAINT uq_step_sensor_state_user_device UNIQUE (user_id, device_id))",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS had_image BOOLEAN",
        "UPDATE chat_messages SET had_image = FALSE WHERE had_image IS NULL",
        "UPDATE users SET tenant_id = (SELECT id FROM tenants WHERE name='default') WHERE tenant_id IS NULL",
        "UPDATE health_records hr SET tenant_id = u.tenant_id FROM users u WHERE hr.user_id = u.id AND hr.tenant_id IS NULL",
        "UPDATE risk_history rh SET tenant_id = u.tenant_id FROM users u WHERE rh.user_id = u.id AND rh.tenant_id IS NULL",
        "UPDATE risk_predictions rp SET tenant_id = u.tenant_id FROM users u WHERE rp.user_id = u.id AND rp.tenant_id IS NULL",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def _ensure_sqlite_compat_schema() -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    sqlite_column_fixes = {
        "health_records": [
            ("tenant_id", "INTEGER"),
            ("steps_count", "INTEGER"),
            ("activity_minutes", "INTEGER"),
            ("resting_heart_rate", "FLOAT"),
            ("hydration_liters", "FLOAT"),
            ("city", "VARCHAR"),
            ("weather_condition", "VARCHAR"),
            ("temperature_c", "FLOAT"),
            ("uv_index", "FLOAT"),
            ("aqi", "INTEGER"),
        ],
        "risk_history": [("tenant_id", "INTEGER")],
        "risk_predictions": [("tenant_id", "INTEGER")],
        "chat_messages": [("tenant_id", "INTEGER"), ("had_image", "BOOLEAN DEFAULT FALSE")],
        "api_keys": [("tenant_id", "INTEGER")],
        "nutrition_logs": [("tenant_id", "INTEGER")],
        "webhook_endpoints": [("tenant_id", "INTEGER")],
        "push_devices": [("tenant_id", "INTEGER")],
        "wearable_connections": [("tenant_id", "INTEGER")],
        "daily_plan_checks": [("tenant_id", "INTEGER")],
        "user_notifications": [("tenant_id", "INTEGER")],
        "share_links": [("tenant_id", "INTEGER")],
        "oauth_states": [("tenant_id", "INTEGER")],
        "login_verification_codes": [("tenant_id", "INTEGER")],
        "step_sensor_states": [("tenant_id", "INTEGER")],
    }

    with engine.begin() as conn:
        for table_name, columns in sqlite_column_fixes.items():
            if table_name not in table_names:
                continue
            existing_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            for column_name, definition in columns:
                if column_name in existing_columns:
                    continue
                conn.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
                )

    with Session(engine) as db:
        default_tenant = _get_default_tenant(db)
        tenant_id = int(default_tenant.id)

    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET tenant_id = :tenant_id WHERE tenant_id IS NULL"),
            {"tenant_id": tenant_id},
        )
        for table_name in [
            "health_records",
            "risk_history",
            "risk_predictions",
            "chat_messages",
            "nutrition_logs",
            "push_devices",
            "wearable_connections",
            "daily_plan_checks",
            "user_notifications",
            "share_links",
            "oauth_states",
            "login_verification_codes",
            "step_sensor_states",
        ]:
            if table_name not in table_names:
                continue
            conn.execute(
                text(
                    f"UPDATE {table_name} "
                    "SET tenant_id = (SELECT tenant_id FROM users WHERE users.id = "
                    f"{table_name}.user_id) "
                    "WHERE tenant_id IS NULL"
                )
            )


def _ensure_login_otp_flag_schema() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "users" not in table_names:
        return

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    with engine.begin() as conn:
        if "tenant_id" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN tenant_id INTEGER"))
        if "location_permission_granted" not in user_columns:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN location_permission_granted BOOLEAN DEFAULT FALSE")
            )
        if "latitude" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN latitude FLOAT"))
        if "longitude" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN longitude FLOAT"))
        if "location_label" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN location_label VARCHAR"))
        if "location_updated_at" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN location_updated_at DATETIME"))
        if "login_otp_required" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN login_otp_required BOOLEAN"))
        conn.execute(
            text(
                "UPDATE users SET location_permission_granted = FALSE "
                "WHERE location_permission_granted IS NULL"
            )
        )
        conn.execute(text("UPDATE users SET login_otp_required = FALSE WHERE login_otp_required IS NULL"))
        if conn.dialect.name != "sqlite":
            conn.execute(text("ALTER TABLE users ALTER COLUMN login_otp_required SET DEFAULT FALSE"))
            conn.execute(text("ALTER TABLE users ALTER COLUMN login_otp_required SET NOT NULL"))

    with Session(engine) as db:
        default_tenant = _get_default_tenant(db)
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE users SET tenant_id = :tenant_id WHERE tenant_id IS NULL"),
                {"tenant_id": default_tenant.id},
            )


def _get_default_tenant(db: Session) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.name == "default").first()
    if tenant:
        return tenant
    defaults = PLAN_DEFAULTS["FREE"]
    tenant = Tenant(
        name="default",
        subscription_tier="FREE",
        daily_record_limit=defaults["daily_record_limit"],
        monthly_alert_limit=defaults["monthly_alert_limit"],
        monthly_chat_limit=defaults["monthly_chat_limit"],
        monthly_image_chat_limit=defaults["monthly_image_chat_limit"],
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def _resolve_tenant(db: Session, requested_name: str | None) -> Tenant:
    if requested_name:
        tenant = db.query(Tenant).filter(Tenant.name == requested_name.strip()).first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return tenant
    return _get_default_tenant(db)


def _commit_or_503(db: Session, detail: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database error during auth flow: %s", exc)
        raise HTTPException(status_code=503, detail=detail)


def _current_month_bounds() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc).replace(tzinfo=None)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
    return start, end


def _hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _parse_events(events_csv: str) -> List[str]:
    return [item.strip() for item in events_csv.split(",") if item.strip()]


def _deliver_webhook(url: str, signing_secret: str, event: str, payload: dict) -> bool:
    body = json.dumps({"event": event, "data": payload}).encode("utf-8")
    signature = hmac.new(signing_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        url=url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-PCUBE-Signature": signature,
            "X-PCUBE-Event": event,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def _dispatch_webhooks(db: Session, tenant_id: int, event: str, payload: dict) -> int:
    hooks = (
        db.query(WebhookEndpoint)
        .filter(WebhookEndpoint.tenant_id == tenant_id, WebhookEndpoint.is_active.is_(True))
        .all()
    )
    delivered = 0
    for hook in hooks:
        events = set(_parse_events(hook.events_csv))
        if event not in events:
            continue
        if _deliver_webhook(hook.url, hook.signing_secret, event, payload):
            delivered += 1
    return delivered


def _get_tenant_from_api_key(db: Session, x_api_key: str | None) -> Tenant:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    key_hash = _hash_api_key(x_api_key.strip())
    api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True)).first()
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    api_key.last_used_at = datetime.utcnow()
    db.commit()
    tenant = db.query(Tenant).filter(Tenant.id == api_key.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=401, detail="Tenant for API key not found")
    return tenant


def _monthly_chat_usage(db: Session, tenant_id: int, user_id: int) -> int:
    month_start, month_end = _current_month_bounds()
    used = (
        db.query(func.count(ChatMessage.id))
        .filter(
            ChatMessage.tenant_id == tenant_id,
            ChatMessage.user_id == user_id,
            ChatMessage.created_at >= month_start,
            ChatMessage.created_at < month_end,
        )
        .scalar()
    )
    return int(used or 0)


def _monthly_image_chat_usage(db: Session, tenant_id: int, user_id: int) -> int:
    month_start, month_end = _current_month_bounds()
    used = (
        db.query(func.count(ChatMessage.id))
        .filter(
            ChatMessage.tenant_id == tenant_id,
            ChatMessage.user_id == user_id,
            ChatMessage.had_image.is_(True),
            ChatMessage.created_at >= month_start,
            ChatMessage.created_at < month_end,
        )
        .scalar()
    )
    return int(used or 0)


def _require_pro_tier(tenant: Tenant, detail: str) -> None:
    tier = str(getattr(tenant, "subscription_tier", "") or "").strip().upper()
    if tier not in {"PRO", "ENTERPRISE"}:
        raise HTTPException(status_code=403, detail=detail)


def _nutrition_log_out(item: NutritionLog) -> NutritionLogOut:
    return NutritionLogOut(
        id=item.id,
        entry_date=item.entry_date,
        meal_type=item.meal_type,
        calories=item.calories,
        water_liters=item.water_liters,
        symptoms=item.symptoms,
        goals=item.goals,
        notes=item.notes,
        created_at=item.created_at,
    )


def _build_chat_context(db: Session, user: User) -> dict:
    latest_record = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == user.id, HealthRecord.tenant_id == user.tenant_id)
        .order_by(HealthRecord.record_date.desc(), HealthRecord.id.desc())
        .first()
    )
    latest_risk = (
        db.query(RiskHistory)
        .filter(RiskHistory.user_id == user.id, RiskHistory.tenant_id == user.tenant_id)
        .order_by(RiskHistory.created_at.desc(), RiskHistory.id.desc())
        .first()
    )
    return {
        "risk_score": getattr(latest_risk, "risk_score", None),
        "risk_level": getattr(latest_risk, "risk_level", None),
        "trend": getattr(latest_risk, "trend", None),
        "systolic_bp": getattr(latest_record, "systolic_bp", None),
        "diastolic_bp": getattr(latest_record, "diastolic_bp", None),
        "bmi": getattr(latest_record, "bmi", None),
        "blood_glucose": getattr(latest_record, "blood_glucose", None),
        "cholesterol": getattr(latest_record, "cholesterol", None),
        "activity_level": getattr(latest_record, "activity_level", None),
        "steps_count": getattr(latest_record, "steps_count", None),
        "activity_minutes": getattr(latest_record, "activity_minutes", None),
        "resting_heart_rate": getattr(latest_record, "resting_heart_rate", None),
        "hydration_liters": getattr(latest_record, "hydration_liters", None),
        "weather_condition": getattr(latest_record, "weather_condition", None),
        "temperature_c": getattr(latest_record, "temperature_c", None),
        "uv_index": getattr(latest_record, "uv_index", None),
        "aqi": getattr(latest_record, "aqi", None),
        "location_label": "regional data enabled" if bool(getattr(user, "location_permission_granted", False)) else None,
        "latitude": None,
        "longitude": None,
    }


def _build_medication_plan_prompt(payload: MedicationPlanRequest) -> str:
    lines = [
        "Create an educational medication guidance plan for this case.",
        f"- Primary complaint: {payload.primary_complaint.strip()}",
        f"- Age range: {(payload.age_range or 'not provided').strip()}",
        f"- Self-reported risk level: {(payload.risk_level or 'not provided').strip()}",
        f"- Known allergies: {(payload.allergies or 'none reported').strip()}",
        f"- Current medications: {(payload.current_medications or 'none reported').strip()}",
    ]
    notes = (payload.additional_notes or "").strip()
    if notes:
        lines.append(f"- Additional notes: {notes}")
    lines.append(
        "Keep the response practical, safety-first, and educational. Mention when to seek urgent or same-day care."
    )
    return "\n".join(lines)


def _build_nutrition_plan_prompt(payload: NutritionPlanRequest, nutrition_summary: NutritionSummaryOut) -> str:
    lines = [
        "Create an educational meal-planning guide for this user.",
        f"- Goal: {payload.goal.strip()}",
        f"- Symptom or health focus: {(payload.symptom_focus or 'not provided').strip()}",
        f"- Dietary preferences: {(payload.dietary_preferences or 'none provided').strip()}",
        f"- Allergies or foods to avoid: {(payload.allergies or 'none reported').strip()}",
        f"- Budget level: {(payload.budget_level or 'not provided').strip()}",
        f"- Cooking time available: {(payload.cooking_time or 'not provided').strip()}",
        f"- Suggested calorie target from recent records: {nutrition_summary.calorie_goal}",
        f"- Suggested water target from recent records: {nutrition_summary.water_goal_liters:.1f} L",
    ]
    if nutrition_summary.health_context:
        lines.append("- Recent health context:")
        for item in nutrition_summary.health_context[:4]:
            lines.append(f"  - {item}")
    notes = (payload.additional_notes or "").strip()
    if notes:
        lines.append(f"- Additional notes: {notes}")
    lines.append(
        "Keep the response practical, safety-first, and educational. Include meal priorities, simple recipe starters, and when symptoms or chronic conditions need clinician review."
    )
    return "\n".join(lines)


def _location_privacy_out(current_user: User) -> UserLocationOut:
    enabled = bool(
        current_user.location_permission_granted
        and current_user.latitude is not None
        and current_user.longitude is not None
    )
    if enabled:
        msg = "Location access granted. Regional health safety and outbreak alerts are enabled."
    elif current_user.location_permission_granted:
        msg = "Location permission granted. Awaiting region sync from your device."
    else:
        msg = "Location access is disabled. Enable it to receive regional health safety updates."
    return UserLocationOut(
        location_permission_granted=bool(current_user.location_permission_granted),
        location_updated_at=current_user.location_updated_at,
        region_monitoring_enabled=enabled,
        status_message=msg,
    )


def _normalize_wearable_provider(provider: str) -> str:
    base = (provider or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "googlefit": "google_fit",
        "google_health_connect": "google_fit",
        "applehealth": "apple_health",
        "healthkit": "apple_health",
    }
    return aliases.get(base, base)


def _upsert_wearable_activity_record(
    *,
    db: Session,
    user: User,
    record_date,
    steps_count: int | None,
    activity_minutes: int | None,
    hydration_liters: float | None,
    resting_heart_rate: float | None,
) -> tuple[HealthRecord, List[str]]:
    record = (
        db.query(HealthRecord)
        .filter(
            HealthRecord.user_id == user.id,
            HealthRecord.tenant_id == user.tenant_id,
            HealthRecord.record_date == record_date,
        )
        .order_by(HealthRecord.id.desc())
        .first()
    )
    if not record:
        record = HealthRecord(
            user_id=user.id,
            tenant_id=user.tenant_id,
            record_date=record_date,
            smoking_status="unknown",
            activity_level="wearable_auto",
        )
        db.add(record)
        db.flush()

    synced: List[str] = []
    if steps_count is not None:
        incoming = max(0, int(steps_count))
        record.steps_count = max(int(record.steps_count or 0), incoming)
        synced.append("steps_count")
    if activity_minutes is not None:
        incoming = max(0, int(activity_minutes))
        record.activity_minutes = max(int(record.activity_minutes or 0), incoming)
        synced.append("activity_minutes")
    if hydration_liters is not None:
        incoming = max(0.0, float(hydration_liters))
        record.hydration_liters = max(float(record.hydration_liters or 0.0), incoming)
        synced.append("hydration_liters")
    if resting_heart_rate is not None:
        record.resting_heart_rate = max(0.0, float(resting_heart_rate))
        synced.append("resting_heart_rate")

    if not record.activity_level:
        record.activity_level = "wearable_auto"

    return record, synced


def _normalize_step_sensor(sensor_type: str | None) -> str:
    base = (sensor_type or "").strip().upper()
    aliases = {
        "TYPE_STEP_COUNTER": "STEP_COUNTER",
        "TYPE_STEP_DETECTOR": "STEP_DETECTOR",
        "TYPE_ACCELEROMETER": "ACCELEROMETER",
        "STEP_COUNTER": "STEP_COUNTER",
        "STEP_DETECTOR": "STEP_DETECTOR",
        "ACCELEROMETER": "ACCELEROMETER",
    }
    normalized = aliases.get(base, base)
    if normalized not in SUPPORTED_STEP_SENSORS:
        raise HTTPException(status_code=400, detail="Unsupported sensor_type")
    return normalized


def _resolve_step_record_day(payload: StepSyncRequest) -> date:
    if payload.record_date is not None:
        return payload.record_date
    if payload.event_time is None:
        return datetime.utcnow().date()

    event_at = payload.event_time
    if event_at.tzinfo is None:
        event_at = event_at.replace(tzinfo=timezone.utc)
    tz_name = (payload.timezone or "").strip()
    if tz_name:
        try:
            event_at = event_at.astimezone(ZoneInfo(tz_name))
        except Exception:
            pass
    return event_at.date()


def _safe_json_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _notification_out(item: UserNotification) -> NotificationOut:
    return NotificationOut(
        id=item.id,
        event_type=item.event_type,
        title=item.title,
        message=item.message,
        severity=item.severity,
        status=item.status,
        metadata=_safe_json_dict(item.metadata_json),
        created_at=item.created_at,
        resolved_at=item.resolved_at,
        snoozed_until=item.snoozed_until,
    )


def _create_notification(
    *,
    db: Session,
    user: User,
    event_type: str,
    title: str,
    message: str,
    severity: str = "INFO",
    metadata: dict | None = None,
) -> UserNotification:
    item = UserNotification(
        tenant_id=user.tenant_id,
        user_id=user.id,
        event_type=event_type,
        title=title,
        message=message,
        severity=severity.upper(),
        status="NEW",
        metadata_json=json.dumps(metadata or {}),
    )
    db.add(item)
    db.flush()
    return item


def _daily_plan_for_user(db: Session, user: User, plan_day: date | None = None) -> DailyPlanOut:
    current_day = plan_day or datetime.utcnow().date()
    latest_record = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == user.id, HealthRecord.tenant_id == user.tenant_id)
        .order_by(HealthRecord.record_date.desc(), HealthRecord.id.desc())
        .first()
    )
    latest_risk = (
        db.query(RiskHistory)
        .filter(RiskHistory.user_id == user.id, RiskHistory.tenant_id == user.tenant_id)
        .order_by(RiskHistory.created_at.desc(), RiskHistory.id.desc())
        .first()
    )

    hydration_target = 2.0
    if latest_record and latest_record.temperature_c is not None and latest_record.temperature_c >= 32:
        hydration_target = 2.5
    step_target = 7000
    if latest_risk and latest_risk.risk_level in {"HIGH", "CRITICAL"}:
        step_target = 6000

    mindful_text = "Take a 10-minute mindful break and deep breathing session."
    if latest_record and latest_record.aqi is not None and latest_record.aqi > 100:
        mindful_text = "Air quality is poor. Do a 10-minute indoor breathing and stretch session."

    tasks = [
        DailyTaskOut(
            key="hydrate_goal",
            title="Hydration",
            description="Keep hydration steady through the day to reduce fatigue and headaches.",
            target=f"Drink at least {hydration_target:.1f} L today",
            completed=False,
        ),
        DailyTaskOut(
            key="step_goal",
            title="Movement Goal",
            description="Frequent walking improves circulation and cardiometabolic health.",
            target=f"Reach at least {step_target} steps today",
            completed=False,
        ),
        DailyTaskOut(
            key="mindful_break",
            title="Stress Reset",
            description="Lower stress can improve heart rate and blood pressure control.",
            target=mindful_text,
            completed=False,
        ),
    ]

    done_rows = (
        db.query(DailyPlanCheck)
        .filter(
            DailyPlanCheck.tenant_id == user.tenant_id,
            DailyPlanCheck.user_id == user.id,
            DailyPlanCheck.plan_date == current_day,
        )
        .all()
    )
    done_map = {row.task_key: bool(row.completed) for row in done_rows}
    for task in tasks:
        task.completed = bool(done_map.get(task.key, False))

    completed_count = sum(1 for task in tasks if task.completed)
    completion_ratio = round(completed_count / max(len(tasks), 1), 2)
    return DailyPlanOut(plan_date=current_day, completion_ratio=completion_ratio, tasks=tasks)


def _streak(records: List[HealthRecord], predicate) -> int:
    if not records:
        return 0
    latest_by_day: dict[date, HealthRecord] = {}
    for rec in records:
        if rec.record_date not in latest_by_day:
            latest_by_day[rec.record_date] = rec
    ordered_days = sorted(latest_by_day.keys(), reverse=True)
    if not ordered_days:
        return 0

    streak = 0
    expected_day = ordered_days[0]
    for day_value in ordered_days:
        if day_value != expected_day:
            break
        rec = latest_by_day[day_value]
        if not predicate(rec):
            break
        streak += 1
        expected_day = expected_day - timedelta(days=1)
    return streak


def _engagement_for_user(db: Session, user: User) -> EngagementOut:
    records = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == user.id, HealthRecord.tenant_id == user.tenant_id)
        .order_by(HealthRecord.record_date.desc(), HealthRecord.id.desc())
        .all()
    )
    hydration_streak = _streak(records, lambda r: (r.hydration_liters or 0) >= 2.0)
    activity_streak = _streak(records, lambda r: (r.steps_count or 0) >= 7000 or (r.activity_minutes or 0) >= 30)
    current_streak = max(hydration_streak, activity_streak)

    week_start = datetime.utcnow().date() - timedelta(days=6)
    weekly_records = [rec for rec in records if rec.record_date >= week_start]
    unique_days = len({rec.record_date for rec in weekly_records})

    checks = (
        db.query(DailyPlanCheck)
        .filter(
            DailyPlanCheck.tenant_id == user.tenant_id,
            DailyPlanCheck.user_id == user.id,
            DailyPlanCheck.plan_date >= week_start,
        )
        .all()
    )
    completed_checks = sum(1 for row in checks if row.completed)
    plan_score = 0.0
    if checks:
        plan_score = completed_checks / len(checks)
    weekly_score = int(min(100, round((unique_days / 7) * 60 + plan_score * 40)))

    milestones: List[str] = []
    if len(records) >= 1:
        milestones.append("First health record logged")
    if current_streak >= 3:
        milestones.append("3-day wellness streak")
    if current_streak >= 7:
        milestones.append("7-day consistency streak")
    if weekly_score >= 80:
        milestones.append("Weekly score above 80")

    return EngagementOut(
        current_streak_days=current_streak,
        hydration_streak_days=hydration_streak,
        activity_streak_days=activity_streak,
        weekly_score=weekly_score,
        milestones=milestones,
    )


def _collect_share_bundle(db: Session, user: User, lookback_days: int) -> dict:
    since_day = datetime.utcnow().date() - timedelta(days=max(lookback_days - 1, 0))
    records = (
        db.query(HealthRecord)
        .filter(
            HealthRecord.user_id == user.id,
            HealthRecord.tenant_id == user.tenant_id,
            HealthRecord.record_date >= since_day,
        )
        .order_by(HealthRecord.record_date.desc(), HealthRecord.id.desc())
        .all()
    )
    risks = (
        db.query(RiskHistory)
        .filter(
            RiskHistory.user_id == user.id,
            RiskHistory.tenant_id == user.tenant_id,
            RiskHistory.created_at >= datetime.combine(since_day, datetime.min.time()),
        )
        .order_by(RiskHistory.created_at.desc(), RiskHistory.id.desc())
        .all()
    )
    return {
        "patient": {
            "full_name": user.full_name,
            "email": user.email,
        },
        "lookback_days": lookback_days,
        "generated_at": datetime.utcnow().isoformat(),
        "records": [
            {
                "record_date": rec.record_date.isoformat(),
                "systolic_bp": rec.systolic_bp,
                "diastolic_bp": rec.diastolic_bp,
                "bmi": rec.bmi,
                "blood_glucose": rec.blood_glucose,
                "cholesterol": rec.cholesterol,
                "steps_count": rec.steps_count,
                "activity_minutes": rec.activity_minutes,
                "hydration_liters": rec.hydration_liters,
            }
            for rec in records[:120]
        ],
        "risk_history": [
            {
                "created_at": item.created_at.isoformat(),
                "risk_score": item.risk_score,
                "risk_level": item.risk_level,
                "trend": item.trend,
            }
            for item in risks[:200]
        ],
        "engagement": _engagement_for_user(db, user).model_dump(),
    }


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_simple_pdf(lines: List[str]) -> bytes:
    rendered = []
    for line in lines[:48]:
        rendered.append(f"({_pdf_escape(line[:100])}) Tj T*")
    stream = ("BT /F1 11 Tf 40 800 Td 14 TL " + " ".join(rendered) + " ET").encode("latin-1", errors="ignore")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    payload = b"%PDF-1.4\n"
    offsets = []
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload += f"{idx} 0 obj\n".encode("latin-1") + obj + b"\nendobj\n"
    xref_pos = len(payload)
    payload += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1")
    for off in offsets:
        payload += f"{off:010} 00000 n \n".encode("latin-1")
    payload += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("latin-1")
    return payload


def _oauth_provider_config(provider: str, request: Request | None) -> dict:
    normalized = _normalize_wearable_provider(provider)
    if normalized == "google_fit":
        client_id = os.getenv("GOOGLE_FIT_CLIENT_ID", "").strip()
        client_secret = os.getenv("GOOGLE_FIT_CLIENT_SECRET", "").strip()
        redirect_uri = os.getenv("GOOGLE_FIT_REDIRECT_URI", "").strip()
        if not redirect_uri and request is not None:
            redirect_uri = str(request.base_url) + "integrations/wearables/google_fit/oauth/callback"
        scopes = os.getenv(
            "GOOGLE_FIT_SCOPES",
            "https://www.googleapis.com/auth/fitness.activity.read https://www.googleapis.com/auth/fitness.heart_rate.read",
        )
        return {
            "provider": normalized,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "scopes": scopes,
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
        }
    if normalized == "fitbit":
        client_id = os.getenv("FITBIT_CLIENT_ID", "").strip()
        client_secret = os.getenv("FITBIT_CLIENT_SECRET", "").strip()
        redirect_uri = os.getenv("FITBIT_REDIRECT_URI", "").strip()
        if not redirect_uri and request is not None:
            redirect_uri = str(request.base_url) + "integrations/wearables/fitbit/oauth/callback"
        scopes = os.getenv("FITBIT_SCOPES", "activity heartrate profile sleep")
        return {
            "provider": normalized,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "scopes": scopes,
            "auth_url": "https://www.fitbit.com/oauth2/authorize",
            "token_url": "https://api.fitbit.com/oauth2/token",
        }
    raise HTTPException(status_code=400, detail="OAuth flow is supported for google_fit and fitbit only")


@app.middleware("http")
async def request_guard(request: Request, call_next):
    client_host = request.client.host if request.client else "unknown"
    now = time.time()
    window = _request_window[client_host]
    while window and (now - window[0]) > 60:
        window.popleft()
    if len(window) >= RATE_LIMIT_PER_MINUTE:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Try again later."},
        )
    window.append(now)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(self), microphone=()")
    logger.info("%s %s -> %s", request.method, request.url.path, response.status_code)
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.on_event("startup")
def start_background_tasks():
    logger.info("Starting PCUBE API environment=%s version=%s", APP_ENV, APP_VERSION)
    _validate_runtime_config()
    if RUN_STARTUP_SCHEMA_PATCHES:
        logger.info("Running startup schema compatibility patches")
        Base.metadata.create_all(bind=engine)
        _ensure_multitenancy_schema()
        _ensure_sqlite_compat_schema()
        _ensure_login_otp_flag_schema()
    else:
        logger.info("Skipping startup schema compatibility patches; expecting migrations to be applied already")
    if ENABLE_SCHEDULER:
        start_scheduler()
        logger.info("Background scheduler enabled")
    else:
        logger.info("Background scheduler disabled by ENABLE_SCHEDULER")


@app.on_event("shutdown")
def shutdown_background_tasks():
    if ENABLE_SCHEDULER:
        stop_scheduler()


@app.get("/")
def root():
    return RedirectResponse(url="/app/login", status_code=307)


@app.get("/healthz", tags=["system"])
def healthz():
    return {
        "status": "ok",
        "service": "Health-Intel API",
        "version": APP_VERSION,
        "environment": APP_ENV,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/readyz", tags=["system"])
def readyz(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="Database is not ready")
    return {"status": "ready", "database": "ok"}


def _serve_frontend_asset(asset_name: str) -> FileResponse:
    file_path = FRONTEND_DIR / "assets" / asset_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Frontend asset not found: {asset_name}")
    return FileResponse(str(file_path))


@app.get("/app", include_in_schema=False)
def frontend_app():
    return RedirectResponse(url="/frontend/assets/pcube.html", status_code=307)


@app.get("/app/login", include_in_schema=False)
def frontend_login_page():
    return RedirectResponse(url="/frontend/assets/login.html", status_code=307)


@app.get("/app/signup", include_in_schema=False)
def frontend_signup_page():
    return RedirectResponse(url="/frontend/assets/signup.html", status_code=307)


@app.get("/app/otp", include_in_schema=False)
def frontend_otp_page():
    return RedirectResponse(url="/frontend/assets/otp.html", status_code=307)


@app.get("/app/checker", include_in_schema=False)
def frontend_checker_page():
    return RedirectResponse(url="/frontend/assets/checker.html", status_code=307)


@app.get("/app/location", include_in_schema=False)
def frontend_location_page():
    return RedirectResponse(url="/frontend/assets/location.html", status_code=307)


@app.get("/app/dashboard", include_in_schema=False)
def frontend_dashboard_page():
    return RedirectResponse(url="/frontend/assets/dashboard.html", status_code=307)


@app.get("/app/auth", include_in_schema=False)
def frontend_auth_page():
    return RedirectResponse(url="/frontend/assets/index.html", status_code=307)


def _mask_email(email: str) -> str:
    try:
        local, domain = email.split("@", 1)
    except ValueError:
        return "***"
    if len(local) <= 2:
        masked_local = local[:1] + "*"
    else:
        masked_local = local[:2] + ("*" * (len(local) - 2))
    return f"{masked_local}@{domain}"


def _otp_secret_bytes() -> bytes:
    secret = os.getenv("LOGIN_OTP_SECRET") or os.getenv("JWT_SECRET") or "pcube-default-otp-secret"
    return secret.encode("utf-8")


def _generate_login_code() -> str:
    upper = 10 ** LOGIN_OTP_DIGITS
    return f"{secrets.randbelow(upper):0{LOGIN_OTP_DIGITS}d}"


def _hash_login_code(challenge_id: str, code: str) -> str:
    payload = f"{challenge_id}:{code.strip()}".encode("utf-8")
    return hmac.new(_otp_secret_bytes(), payload, hashlib.sha256).hexdigest()


@app.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    if not user.full_name.strip():
        raise HTTPException(status_code=400, detail="Full name is required")
    password = user.password or ""
    if len(password) < 8 or not any(ch.isdigit() for ch in password) or not any(ch.isalpha() for ch in password):
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters and include letters and numbers",
        )
    try:
        existing = db.query(User).filter(User.email == user.email).first()
    except OperationalError:
        raise HTTPException(status_code=503, detail="Database unavailable. Check database configuration.")
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    tenant = _resolve_tenant(db, user.tenant_name)
    new_user = User(
        email=user.email,
        full_name=user.full_name,
        password_hash=hash_password(user.password),
        tenant_id=tenant.id,
        login_otp_required=bool(LOGIN_OTP_ENABLED),
    )
    db.add(new_user)
    try:
        db.commit()
        db.refresh(new_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered")
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create user")

    if LOGIN_OTP_ENABLED:
        return {
            "message": "User created. Verify the one-time code to finish signing in.",
            "user_id": new_user.id,
            "otp_required": True,
        }

    token = create_access_token({"user_id": new_user.id, "tenant_id": new_user.tenant_id})
    return {
        "message": "User created",
        "access_token": token,
        "user_id": new_user.id,
        "otp_required": False,
    }


def _authenticate_user_credentials(user: UserLogin, db: Session) -> User:
    try:
        db_user = db.query(User).filter(User.email == user.email).first()
    except OperationalError:
        raise HTTPException(status_code=503, detail="Database unavailable. Check database configuration.")
    if not db_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    try:
        password_ok = verify_password(user.password, db_user.password_hash)
    except Exception as exc:
        logger.warning("Password verification failed for user_id=%s: %s", db_user.id, exc)
        password_ok = False
    if not password_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return db_user


def _user_requires_login_otp(db_user: User) -> bool:
    return bool(LOGIN_OTP_ENABLED)


@app.post("/login/request-code", response_model=LoginCodeChallengeOut)
def login_request_code(user: UserLogin, db: Session = Depends(get_db)):
    db_user = _authenticate_user_credentials(user, db)
    if not LOGIN_OTP_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="One-time verification is currently disabled.",
        )
    now = datetime.utcnow()
    try:
        recent_issue_count = (
            db.query(func.count(LoginVerificationCode.id))
            .filter(
                LoginVerificationCode.user_id == db_user.id,
                LoginVerificationCode.created_at >= (now - timedelta(minutes=10)),
            )
            .scalar()
            or 0
        )
        if int(recent_issue_count) >= LOGIN_OTP_MAX_ISSUES_PER_10_MIN:
            raise HTTPException(status_code=429, detail="Too many verification code requests. Please try again later.")

        db.query(LoginVerificationCode).filter(
            LoginVerificationCode.user_id == db_user.id,
            LoginVerificationCode.is_used == False,
        ).update({"is_used": True, "consumed_at": now}, synchronize_session=False)

        challenge_id = secrets.token_urlsafe(24)
        code = _generate_login_code()
        expires_at = now + timedelta(minutes=LOGIN_OTP_TTL_MINUTES)
        code_hash = _hash_login_code(challenge_id, code)

        challenge = LoginVerificationCode(
            tenant_id=db_user.tenant_id,
            user_id=db_user.id,
            challenge_id=challenge_id,
            code_hash=code_hash,
            expires_at=expires_at,
            attempts=0,
            max_attempts=LOGIN_OTP_MAX_ATTEMPTS,
            is_used=False,
            delivery_channel="email",
        )
        db.add(challenge)
        _commit_or_503(db, "Database unavailable. Unable to create verification challenge.")
        db.refresh(challenge)
    except HTTPException:
        raise
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database unavailable. Unable to process login verification.")

    message = (
        f"Your PCUBE verification code is {code}. "
        f"It expires in {LOGIN_OTP_TTL_MINUTES} minute(s). "
        "If you did not request this login, ignore this message."
    )
    email_ok = send_email(
        to_email=db_user.email,
        subject="PCUBE Login Verification Code",
        body=message,
    )
    if not email_ok:
        if APP_ENV != "production":
            logger.warning(
                "Email unavailable for login_request_code user_id=%s tenant_id=%s; returning dev code",
                db_user.id,
                db_user.tenant_id,
            )
            return LoginCodeChallengeOut(
                challenge_id=challenge_id,
                otp_required=True,
                delivery_channel="local-dev",
                destination_masked="local-dev",
                expires_at=expires_at,
                expires_in_seconds=max(0, int((expires_at - datetime.utcnow()).total_seconds())),
                message="Dev verification code generated. Sign-in will complete automatically.",
                debug_code=code,
            )

        challenge.is_used = True
        challenge.consumed_at = datetime.utcnow()
        _commit_or_503(db, "Database unavailable. Unable to finalize verification challenge.")
        raise HTTPException(status_code=503, detail="Unable to send verification code. Check email configuration.")

    masked = _mask_email(db_user.email)
    return LoginCodeChallengeOut(
        challenge_id=challenge_id,
        otp_required=True,
        delivery_channel="email",
        destination_masked=masked,
        expires_at=expires_at,
        expires_in_seconds=max(0, int((expires_at - datetime.utcnow()).total_seconds())),
        message=f"Verification code sent to {masked}",
    )


@app.post("/login/verify-code")
def login_verify_code(payload: LoginCodeVerifyIn, db: Session = Depends(get_db)):
    try:
        challenge = (
            db.query(LoginVerificationCode)
            .filter(LoginVerificationCode.challenge_id == payload.challenge_id)
            .first()
        )
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable. Unable to verify code.")
    if not challenge:
        raise HTTPException(status_code=401, detail="Invalid verification challenge")

    now = datetime.utcnow()
    try:
        max_attempts = int(challenge.max_attempts or LOGIN_OTP_MAX_ATTEMPTS)
    except (TypeError, ValueError):
        max_attempts = LOGIN_OTP_MAX_ATTEMPTS
    if max_attempts < 1:
        max_attempts = LOGIN_OTP_MAX_ATTEMPTS
    if challenge.max_attempts != max_attempts:
        challenge.max_attempts = max_attempts
    try:
        attempts = int(challenge.attempts or 0)
    except (TypeError, ValueError):
        attempts = 0
    if attempts < 0:
        attempts = 0
    if challenge.attempts != attempts:
        challenge.attempts = attempts

    if challenge.is_used:
        raise HTTPException(status_code=401, detail="Verification code already used")
    if not challenge.expires_at:
        challenge.is_used = True
        challenge.consumed_at = now
        _commit_or_503(db, "Database unavailable. Unable to update verification challenge.")
        raise HTTPException(status_code=401, detail="Verification code expired")
    if challenge.expires_at < now:
        challenge.is_used = True
        challenge.consumed_at = now
        _commit_or_503(db, "Database unavailable. Unable to update verification challenge.")
        raise HTTPException(status_code=401, detail="Verification code expired")
    if attempts >= max_attempts:
        challenge.is_used = True
        challenge.consumed_at = now
        _commit_or_503(db, "Database unavailable. Unable to update verification challenge.")
        raise HTTPException(status_code=429, detail="Too many invalid attempts. Request a new code.")

    expected_hash = _hash_login_code(challenge.challenge_id, payload.code)
    if not challenge.code_hash or not hmac.compare_digest(expected_hash, challenge.code_hash):
        challenge.attempts = attempts + 1
        if challenge.attempts >= max_attempts:
            challenge.is_used = True
            challenge.consumed_at = now
        _commit_or_503(db, "Database unavailable. Unable to update verification challenge.")
        raise HTTPException(status_code=401, detail="Invalid verification code")

    try:
        db_user = (
            db.query(User)
            .filter(User.id == challenge.user_id, User.tenant_id == challenge.tenant_id)
            .first()
        )
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable. Unable to complete login.")
    if not db_user:
        challenge.is_used = True
        challenge.consumed_at = now
        _commit_or_503(db, "Database unavailable. Unable to update verification challenge.")
        raise HTTPException(status_code=404, detail="User account not found")

    challenge.is_used = True
    challenge.consumed_at = now
    _commit_or_503(db, "Database unavailable. Unable to complete login.")

    token = create_access_token({"user_id": db_user.id, "tenant_id": db_user.tenant_id})
    return {"access_token": token, "token_type": "bearer"}


@app.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = _authenticate_user_credentials(user, db)
    if LOGIN_OTP_ENABLED:
        raise HTTPException(
            status_code=403,
            detail=LOGIN_OTP_REQUIRED_DETAIL,
        )
    token = create_access_token({"user_id": db_user.id, "tenant_id": db_user.tenant_id})
    return {"access_token": token, "token_type": "bearer"}


@app.get("/users/me/location", response_model=UserLocationOut)
def get_my_location(current_user: User = Depends(get_current_user)):
    return _location_privacy_out(current_user)


@app.patch("/users/me/location-permission", response_model=UserLocationOut)
def update_location_permission(
    payload: UserLocationPermissionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.location_permission_granted = bool(payload.granted)
    if not payload.granted:
        current_user.latitude = None
        current_user.longitude = None
        current_user.location_label = None
        current_user.location_updated_at = None
    db.commit()
    db.refresh(current_user)
    return _location_privacy_out(current_user)


@app.put("/users/me/location", response_model=UserLocationOut)
def update_my_location(
    payload: UserLocationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.location_permission_granted:
        raise HTTPException(status_code=403, detail="Location permission not granted")
    current_user.latitude = payload.latitude
    current_user.longitude = payload.longitude
    label = (payload.label or "").strip()
    if label and "lat " in label.lower() and "lon " in label.lower():
        label = ""
    current_user.location_label = label or "local region"
    current_user.location_updated_at = datetime.utcnow()
    db.commit()
    db.refresh(current_user)
    return _location_privacy_out(current_user)


@app.get("/users/me/live-intel", response_model=LiveIntelOut)
def users_live_intel(
    current_user: User = Depends(get_current_user),
):
    if not current_user.location_permission_granted:
        raise HTTPException(status_code=403, detail="Location permission not granted")
    if current_user.latitude is None or current_user.longitude is None:
        raise HTTPException(status_code=400, detail="User location is not set")

    payload = collect_live_intel(
        current_user.latitude,
        current_user.longitude,
        None,
        datetime.utcnow().date(),
    )
    payload["city"] = "your region"
    if not payload.get("outbreak_alerts"):
        payload["outbreak_alerts"] = build_outbreak_alerts(datetime.utcnow().date())
    return LiveIntelOut(**payload)


@app.post("/device/steps/sync", response_model=StepSyncResponse)
def device_steps_sync(
    payload: StepSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device_id = (payload.device_id or "").strip()
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id is required")

    sensor_type = _normalize_step_sensor(payload.sensor_type)
    record_day = _resolve_step_record_day(payload)
    activity_delta = max(0, int(payload.activity_minutes_delta or 0))

    state = (
        db.query(StepSensorState)
        .filter(
            StepSensorState.tenant_id == current_user.tenant_id,
            StepSensorState.user_id == current_user.id,
            StepSensorState.device_id == device_id,
        )
        .first()
    )
    if not state:
        state = StepSensorState(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            device_id=device_id,
            sensor_type=sensor_type,
            baseline_date=record_day,
            daily_steps=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(state)
        db.flush()

    previous_daily_steps = int(state.daily_steps or 0)
    day_changed = state.baseline_date != record_day
    if day_changed:
        state.baseline_date = record_day
        state.daily_steps = 0
        previous_daily_steps = 0

    state.sensor_type = sensor_type
    if payload.timezone:
        state.timezone_name = payload.timezone.strip()
    if payload.algorithm_version:
        state.algorithm_version = payload.algorithm_version.strip()
    if payload.confidence is not None:
        state.confidence = float(payload.confidence)

    if payload.event_time is not None:
        event_at = payload.event_time
        if event_at.tzinfo is not None:
            event_at = event_at.astimezone(timezone.utc).replace(tzinfo=None)
        state.last_event_at = event_at
    else:
        state.last_event_at = datetime.utcnow()

    warning = None
    accepted_step_delta = 0
    processing_mode = "manual_delta"

    if payload.total_steps_since_boot is not None:
        processing_mode = "hardware_step_counter"
        incoming_total = max(0, int(payload.total_steps_since_boot))
        incoming_boot_id = (payload.boot_id or "").strip() or None
        boot_changed = bool(state.last_boot_id and incoming_boot_id and incoming_boot_id != state.last_boot_id)
        counter_reset = state.last_total_since_boot is not None and incoming_total < int(state.last_total_since_boot)
        baseline_missing = state.baseline_total_since_boot is None

        if baseline_missing or day_changed or boot_changed or counter_reset:
            state.baseline_total_since_boot = incoming_total
            state.daily_steps = 0
            accepted_step_delta = 0
            if day_changed:
                warning = "Daily baseline reset at midnight"
            elif boot_changed or counter_reset:
                warning = "Device reboot/counter reset detected; baseline restarted"
            else:
                warning = "Baseline initialized for step counter"
        else:
            daily_steps = max(incoming_total - int(state.baseline_total_since_boot or incoming_total), 0)
            accepted_step_delta = max(daily_steps - previous_daily_steps, 0)
            state.daily_steps = daily_steps

        state.last_total_since_boot = incoming_total
        state.last_boot_id = incoming_boot_id or state.last_boot_id
    elif payload.detected_steps_delta is not None:
        processing_mode = "step_detector_delta" if sensor_type == "STEP_DETECTOR" else "accelerometer_delta"
        accepted_step_delta = max(0, int(payload.detected_steps_delta))
        state.daily_steps = max(0, int(state.daily_steps or 0) + accepted_step_delta)
        if sensor_type == "ACCELEROMETER":
            warning = "Accelerometer mode is fallback and less accurate than hardware step counter"
    elif payload.step_delta is not None:
        processing_mode = "legacy_manual_delta"
        accepted_step_delta = max(0, int(payload.step_delta))
        state.daily_steps = max(0, int(state.daily_steps or 0) + accepted_step_delta)
        warning = "Legacy manual delta mode is less accurate than sensor-based sync"
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide total_steps_since_boot, detected_steps_delta, or step_delta",
        )

    if accepted_step_delta == 0 and activity_delta == 0 and warning is None:
        raise HTTPException(status_code=400, detail="No new steps or activity minutes to sync")

    record = (
        db.query(HealthRecord)
        .filter(
            HealthRecord.user_id == current_user.id,
            HealthRecord.tenant_id == current_user.tenant_id,
            HealthRecord.record_date == record_day,
        )
        .order_by(HealthRecord.id.desc())
        .first()
    )
    if not record:
        record = HealthRecord(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            record_date=record_day,
            smoking_status="unknown",
            activity_level="sensor_mobile",
            steps_count=0,
            activity_minutes=0,
        )
        db.add(record)
        db.flush()

    if processing_mode == "hardware_step_counter":
        record.steps_count = max(int(record.steps_count or 0), int(state.daily_steps or 0))
    else:
        record.steps_count = max(0, int((record.steps_count or 0) + accepted_step_delta))
        record.steps_count = max(int(record.steps_count or 0), int(state.daily_steps or 0))
    record.activity_minutes = max(0, int((record.activity_minutes or 0) + activity_delta))
    record.activity_level = "sensor_mobile"

    state.last_sync_mode = processing_mode
    state.updated_at = datetime.utcnow()
    db.commit()

    return StepSyncResponse(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        device_id=device_id,
        sensor_type=sensor_type,
        processing_mode=processing_mode,
        record_date=record.record_date,
        accepted_step_delta=int(accepted_step_delta),
        daily_steps_from_sensor=int(state.daily_steps or 0),
        total_steps=int(record.steps_count or 0),
        total_activity_minutes=int(record.activity_minutes or 0),
        warning=warning,
    )


@app.post("/users/me/push-tokens", response_model=PushTokenOut)
def register_push_token(
    payload: PushTokenRegister,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    provider = (payload.provider or "").strip().lower()
    if provider not in SUPPORTED_PUSH_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported push provider")
    platform = (payload.platform or "").strip().lower()
    if not platform:
        raise HTTPException(status_code=400, detail="Platform is required")
    token = (payload.push_token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="push_token is required")

    existing = (
        db.query(PushDevice)
        .filter(
            PushDevice.tenant_id == current_user.tenant_id,
            PushDevice.user_id == current_user.id,
            PushDevice.push_token == token,
        )
        .first()
    )
    now = datetime.utcnow()
    if existing:
        existing.provider = provider
        existing.platform = platform
        existing.device_label = payload.device_label.strip() if payload.device_label else existing.device_label
        existing.is_active = True
        existing.last_seen_at = now
        db.commit()
        db.refresh(existing)
        return existing

    device = PushDevice(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        provider=provider,
        platform=platform,
        device_label=payload.device_label.strip() if payload.device_label else None,
        push_token=token,
        is_active=True,
        last_seen_at=now,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@app.get("/users/me/push-tokens", response_model=List[PushTokenOut])
def list_push_tokens(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(PushDevice)
        .filter(PushDevice.tenant_id == current_user.tenant_id, PushDevice.user_id == current_user.id)
        .order_by(PushDevice.created_at.desc())
        .all()
    )


@app.delete("/users/me/push-tokens/{device_id}")
def deactivate_push_token(
    device_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = (
        db.query(PushDevice)
        .filter(
            PushDevice.id == device_id,
            PushDevice.tenant_id == current_user.tenant_id,
            PushDevice.user_id == current_user.id,
        )
        .first()
    )
    if not device:
        raise HTTPException(status_code=404, detail="Push device not found")
    device.is_active = False
    device.last_seen_at = datetime.utcnow()
    db.commit()
    return {"id": device.id, "deactivated": True}


@app.post("/users/me/push-tokens/test")
def test_push_tokens(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    devices = (
        db.query(PushDevice)
        .filter(
            PushDevice.tenant_id == current_user.tenant_id,
            PushDevice.user_id == current_user.id,
            PushDevice.is_active.is_(True),
        )
        .all()
    )
    if not devices:
        raise HTTPException(status_code=404, detail="No active push device tokens registered")

    sent = 0
    for device in devices:
        ok = send_push_notification(
            push_token=device.push_token,
            title="PCUBE Test Notification",
            body="Push channel is connected. You will now receive risk alerts here.",
            data={"type": "test"},
        )
        if ok:
            sent += 1
            device.last_seen_at = datetime.utcnow()
    db.commit()
    return {"registered_devices": len(devices), "sent": sent}


@app.post("/integrations/wearables/connect", response_model=WearableConnectionOut)
def connect_wearable(
    payload: WearableConnectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    provider = _normalize_wearable_provider(payload.provider)
    if provider not in SUPPORTED_WEARABLES:
        raise HTTPException(status_code=400, detail="Unsupported wearable provider")

    conn = (
        db.query(WearableConnection)
        .filter(
            WearableConnection.tenant_id == current_user.tenant_id,
            WearableConnection.user_id == current_user.id,
            WearableConnection.provider == provider,
        )
        .first()
    )
    if not conn:
        conn = WearableConnection(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            provider=provider,
            is_active=True,
        )
        db.add(conn)

    conn.external_user_id = payload.external_user_id.strip() if payload.external_user_id else conn.external_user_id
    conn.access_token = payload.access_token if payload.access_token else conn.access_token
    conn.refresh_token = payload.refresh_token if payload.refresh_token else conn.refresh_token
    conn.scope = payload.scope.strip() if payload.scope else conn.scope
    conn.token_expires_at = payload.token_expires_at or conn.token_expires_at
    conn.is_active = True
    db.commit()
    db.refresh(conn)
    return conn


@app.get("/integrations/wearables", response_model=List[WearableConnectionOut])
def list_wearable_connections(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(WearableConnection)
        .filter(WearableConnection.tenant_id == current_user.tenant_id, WearableConnection.user_id == current_user.id)
        .order_by(WearableConnection.created_at.desc())
        .all()
    )


@app.delete("/integrations/wearables/{provider}")
def disconnect_wearable(
    provider: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized = _normalize_wearable_provider(provider)
    conn = (
        db.query(WearableConnection)
        .filter(
            WearableConnection.tenant_id == current_user.tenant_id,
            WearableConnection.user_id == current_user.id,
            WearableConnection.provider == normalized,
        )
        .first()
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Wearable connection not found")
    conn.is_active = False
    conn.access_token = None
    conn.refresh_token = None
    db.commit()
    return {"provider": normalized, "disconnected": True}


@app.post("/integrations/wearables/sync", response_model=WearableSyncResponse)
def sync_wearable_data(
    payload: WearableSyncRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    provider = _normalize_wearable_provider(payload.provider)
    if provider not in SUPPORTED_WEARABLES:
        raise HTTPException(status_code=400, detail="Unsupported wearable provider")

    conn = (
        db.query(WearableConnection)
        .filter(
            WearableConnection.tenant_id == current_user.tenant_id,
            WearableConnection.user_id == current_user.id,
            WearableConnection.provider == provider,
            WearableConnection.is_active.is_(True),
        )
        .first()
    )
    if not conn:
        raise HTTPException(status_code=403, detail="Wearable provider is not connected for this user")

    if (
        payload.steps_count is None
        and payload.activity_minutes is None
        and payload.hydration_liters is None
        and payload.resting_heart_rate is None
    ):
        raise HTTPException(status_code=400, detail="No wearable metrics provided to sync")

    record_day = payload.record_date or datetime.utcnow().date()
    record, synced_fields = _upsert_wearable_activity_record(
        db=db,
        user=current_user,
        record_date=record_day,
        steps_count=payload.steps_count,
        activity_minutes=payload.activity_minutes,
        hydration_liters=payload.hydration_liters,
        resting_heart_rate=payload.resting_heart_rate,
    )
    conn.last_sync_at = datetime.utcnow()
    db.commit()
    db.refresh(record)

    return WearableSyncResponse(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        provider=provider,
        record_id=record.id,
        record_date=record.record_date,
        synced_fields=synced_fields,
    )


@app.post("/device/wearables/sync", response_model=WearableSyncResponse)
def device_sync_wearable_data(
    payload: WearableSyncRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    user_id: int | None = None,
    db: Session = Depends(get_db),
):
    provider = _normalize_wearable_provider(payload.provider)
    if provider not in SUPPORTED_WEARABLES:
        raise HTTPException(status_code=400, detail="Unsupported wearable provider")
    tenant = _get_tenant_from_api_key(db, x_api_key)

    if user_id is None:
        actor_user = db.query(User).filter(User.tenant_id == tenant.id).order_by(User.id.asc()).first()
    else:
        actor_user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant.id).first()
    if not actor_user:
        raise HTTPException(status_code=404, detail="No eligible tenant user found for wearable sync")

    if (
        payload.steps_count is None
        and payload.activity_minutes is None
        and payload.hydration_liters is None
        and payload.resting_heart_rate is None
    ):
        raise HTTPException(status_code=400, detail="No wearable metrics provided to sync")

    record_day = payload.record_date or datetime.utcnow().date()
    record, synced_fields = _upsert_wearable_activity_record(
        db=db,
        user=actor_user,
        record_date=record_day,
        steps_count=payload.steps_count,
        activity_minutes=payload.activity_minutes,
        hydration_liters=payload.hydration_liters,
        resting_heart_rate=payload.resting_heart_rate,
    )

    conn = (
        db.query(WearableConnection)
        .filter(
            WearableConnection.tenant_id == actor_user.tenant_id,
            WearableConnection.user_id == actor_user.id,
            WearableConnection.provider == provider,
        )
        .first()
    )
    if conn:
        conn.last_sync_at = datetime.utcnow()

    db.commit()
    db.refresh(record)
    return WearableSyncResponse(
        user_id=actor_user.id,
        tenant_id=actor_user.tenant_id,
        provider=provider,
        record_id=record.id,
        record_date=record.record_date,
        synced_fields=synced_fields,
    )


def _assistant_file_out(payload: dict) -> AssistantFileOut:
    raw_error = str(payload.get("error_message") or "").strip()
    return AssistantFileOut(
        id=str(payload.get("id") or "") or None,
        name=str(payload.get("name") or "uploaded-file"),
        status=str(payload.get("status") or "").strip() or None,
        percent_done=float(payload.get("percent_done")) if payload.get("percent_done") is not None else None,
        error_message=(
            _public_provider_error_message("File processing is unavailable right now. Please try again later.")
            if raw_error
            else None
        ),
        created_on=str(payload.get("created_on") or "").strip() or None,
        updated_on=str(payload.get("updated_on") or "").strip() or None,
    )


@app.get("/chatbot/assistant-files", response_model=AssistantFilesResponse)
def chatbot_assistant_files(current_user: User = Depends(get_current_user)):
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    assistant_name = os.getenv("PINECONE_ASSISTANT_NAME", "").strip() or None
    supported_types = pinecone_supported_file_extensions()
    if provider not in {"pinecone", "assistant"}:
        return AssistantFilesResponse(
            provider=provider or "openai",
            assistant_name=assistant_name,
            upload_enabled=False,
            supported_types=supported_types,
            files=[],
        )

    try:
        files = list_pinecone_assistant_files()
    except RuntimeError as exc:
        logger.warning("Assistant file list unavailable for user_id=%s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=502,
            detail=_public_provider_error_message(
                "Document uploads are temporarily unavailable. Please try again later."
            ),
        )

    return AssistantFilesResponse(
        provider="pinecone",
        assistant_name=assistant_name,
        upload_enabled=True,
        supported_types=supported_types,
        files=[_assistant_file_out(item) for item in files],
    )


@app.post("/chatbot/assistant-files", response_model=AssistantFileUploadResponse)
async def chatbot_upload_assistant_file(
    upload: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider not in {"pinecone", "assistant"}:
        raise HTTPException(
            status_code=400,
            detail="Assistant file uploads are only enabled when LLM_PROVIDER is pinecone.",
        )

    file_name = str(upload.filename or "").strip()
    if not file_name:
        raise HTTPException(status_code=400, detail="A file name is required.")

    max_bytes = int(os.getenv("PINECONE_FILE_MAX_BYTES", "20971520"))
    file_bytes = await upload.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(file_bytes) > max_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is too large.")

    try:
        item = upload_pinecone_assistant_file(
            file_name=file_name,
            file_bytes=file_bytes,
            content_type=upload.content_type,
        )
    except RuntimeError as exc:
        logger.warning("Assistant file upload unavailable for user_id=%s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=502,
            detail=_public_provider_error_message(
                "Document upload is temporarily unavailable. Please try again later."
            ),
        )
    finally:
        await upload.close()

    assistant_name = os.getenv("PINECONE_ASSISTANT_NAME", "").strip() or "assistant"
    return AssistantFileUploadResponse(
        provider="pinecone",
        assistant_name=assistant_name,
        message="File uploaded. Wait for its status to become Available before asking questions about it.",
        file=_assistant_file_out(item),
    )


@app.post("/chatbot/ask", response_model=ChatAskResponse)
def chatbot_ask(
    payload: ChatAskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required")

    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=400, detail="User tenant is not configured")

    used = _monthly_chat_usage(db, tenant.id, current_user.id)
    limit, image_limit = _effective_chat_limits(tenant, current_user)
    if used >= limit:
        raise HTTPException(status_code=429, detail="Monthly chatbot limit reached for your subscription plan")
    image_used = _monthly_image_chat_usage(db, tenant.id, current_user.id)

    recent = (
        db.query(ChatMessage)
        .filter(ChatMessage.tenant_id == tenant.id, ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(6)
        .all()
    )
    history = []
    for item in reversed(recent):
        history.append({"role": "user", "content": item.question})
        history.append({"role": "assistant", "content": item.answer})

    context = _build_chat_context(db, current_user)
    try:
        answer, model_used, prompt_tokens, completion_tokens = ask_llm(
            question=question,
            context=context,
            history=history,
        )
    except RuntimeError as e:
        logger.warning(
            "LLM unavailable for chatbot_ask user_id=%s tenant_id=%s: %s",
            current_user.id,
            tenant.id,
            e,
        )
        raise HTTPException(
            status_code=502,
            detail="Pinecone chat is unavailable right now. Please try again in a moment.",
        ) from e

    msg = ChatMessage(
        tenant_id=tenant.id,
        user_id=current_user.id,
        question=question,
        answer=answer,
        had_image=False,
        llm_model=model_used,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    db.add(msg)
    db.commit()

    used_after = used + 1
    remaining = max(limit - used_after, 0)
    return ChatAskResponse(
        answer=answer,
        llm_model=model_used,
        plan_tier=tenant.subscription_tier,
        used_this_month=used_after,
        monthly_limit=limit,
        remaining=remaining,
        image_used=False,
        image_used_this_month=image_used,
        image_monthly_limit=image_limit,
        image_remaining=max(image_limit - image_used, 0),
    )


@app.post("/chat", response_model=ChatLoopResponse)
def chat_loop(
    payload: ChatLoopRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    result = chatbot_ask(payload=ChatAskRequest(question=message), current_user=current_user, db=db)
    return ChatLoopResponse(
        response=result.answer,
        llm_model=result.llm_model,
        remaining=result.remaining,
    )


@app.get("/nutrition/summary", response_model=NutritionSummaryOut)
def nutrition_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=400, detail="User tenant is not configured")

    latest_record = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == current_user.id, HealthRecord.tenant_id == current_user.tenant_id)
        .order_by(HealthRecord.record_date.desc(), HealthRecord.id.desc())
        .first()
    )
    logs = (
        db.query(NutritionLog)
        .filter(NutritionLog.user_id == current_user.id, NutritionLog.tenant_id == current_user.tenant_id)
        .order_by(NutritionLog.entry_date.desc(), NutritionLog.created_at.desc())
        .limit(10)
        .all()
    )
    summary = build_nutrition_summary(
        plan_tier=tenant.subscription_tier,
        latest_record=latest_record,
        logs=logs,
    )
    return NutritionSummaryOut(
        **summary,
        recent_logs=[_nutrition_log_out(item) for item in logs],
    )


@app.post("/nutrition/logs", response_model=NutritionLogOut)
def create_nutrition_log(
    payload: NutritionLogCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content_present = any(
        value is not None and str(value).strip()
        for value in [
            payload.calories,
            payload.water_liters,
            payload.symptoms,
            payload.goals,
            payload.notes,
            payload.meal_type,
        ]
    )
    if not content_present:
        raise HTTPException(
            status_code=400,
            detail="Add at least one nutrition detail such as calories, water, symptoms, goals, or notes.",
        )

    log = NutritionLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        entry_date=payload.entry_date or datetime.utcnow().date(),
        meal_type=(payload.meal_type or "").strip() or None,
        calories=payload.calories,
        water_liters=payload.water_liters,
        symptoms=(payload.symptoms or "").strip() or None,
        goals=(payload.goals or "").strip() or None,
        notes=(payload.notes or "").strip() or None,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return _nutrition_log_out(log)


@app.post("/chatbot/nutrition-plan", response_model=NutritionPlanResponse)
def nutrition_plan_ask(
    payload: NutritionPlanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    goal = payload.goal.strip()
    if not goal:
        raise HTTPException(status_code=400, detail="Goal is required")

    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=400, detail="User tenant is not configured")
    _require_pro_tier(
        tenant,
        "Nutrition AI meal planning is reserved for Pro and Enterprise plans.",
    )

    used = _monthly_chat_usage(db, tenant.id, current_user.id)
    limit, _image_limit = _effective_chat_limits(tenant, current_user)
    if used >= limit:
        raise HTTPException(status_code=429, detail="Monthly chatbot limit reached for your subscription plan")

    latest_record = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == current_user.id, HealthRecord.tenant_id == current_user.tenant_id)
        .order_by(HealthRecord.record_date.desc(), HealthRecord.id.desc())
        .first()
    )
    logs = (
        db.query(NutritionLog)
        .filter(NutritionLog.user_id == current_user.id, NutritionLog.tenant_id == current_user.tenant_id)
        .order_by(NutritionLog.entry_date.desc(), NutritionLog.created_at.desc())
        .limit(10)
        .all()
    )
    summary = NutritionSummaryOut(
        **build_nutrition_summary(
            plan_tier=tenant.subscription_tier,
            latest_record=latest_record,
            logs=logs,
        ),
        recent_logs=[_nutrition_log_out(item) for item in logs],
    )

    prompt = _build_nutrition_plan_prompt(payload, summary)
    context = _build_chat_context(db, current_user)
    used_fallback = False
    try:
        answer, model_used, prompt_tokens, completion_tokens = ask_llm(
            question=prompt,
            context=context,
            history=[],
            assistant="nutrition",
        )
    except RuntimeError as e:
        logger.warning(
            "LLM unavailable for nutrition_plan_ask user_id=%s tenant_id=%s: %s",
            current_user.id,
            tenant.id,
            e,
        )
        raise HTTPException(
            status_code=502,
            detail="Pinecone nutrition chat is unavailable right now. Please try again in a moment.",
        )

    if not used_fallback:
        msg = ChatMessage(
            tenant_id=tenant.id,
            user_id=current_user.id,
            question=f"[Nutrition AI]\n{prompt}",
            answer=answer,
            had_image=False,
            llm_model=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        db.add(msg)
        db.commit()

    used_after = used + (0 if used_fallback else 1)
    return NutritionPlanResponse(
        answer=answer,
        llm_model=model_used,
        plan_tier=tenant.subscription_tier,
        used_this_month=used_after,
        monthly_limit=limit,
        remaining=max(limit - used_after, 0),
    )


@app.post("/chatbot/medication-plan", response_model=MedicationPlanResponse)
def medication_plan_ask(
    payload: MedicationPlanRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    primary_complaint = payload.primary_complaint.strip()
    if not primary_complaint:
        raise HTTPException(status_code=400, detail="Primary complaint is required")

    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=400, detail="User tenant is not configured")

    used = _monthly_chat_usage(db, tenant.id, current_user.id)
    limit, _image_limit = _effective_chat_limits(tenant, current_user)
    if used >= limit:
        raise HTTPException(status_code=429, detail="Monthly chatbot limit reached for your subscription plan")

    prompt = _build_medication_plan_prompt(payload)
    context = _build_chat_context(db, current_user)
    used_fallback = False
    try:
        answer, model_used, prompt_tokens, completion_tokens = ask_llm(
            question=prompt,
            context=context,
            history=[],
            assistant="medication",
        )
    except RuntimeError as e:
        logger.warning(
            "LLM unavailable for medication_plan_ask user_id=%s tenant_id=%s: %s",
            current_user.id,
            tenant.id,
            e,
        )
        raise HTTPException(
            status_code=502,
            detail="Pinecone medication chat is unavailable right now. Please try again in a moment.",
        )

    if not used_fallback:
        msg = ChatMessage(
            tenant_id=tenant.id,
            user_id=current_user.id,
            question=f"[Medication AI]\n{prompt}",
            answer=answer,
            had_image=False,
            llm_model=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        db.add(msg)
        db.commit()

    used_after = used + (0 if used_fallback else 1)
    return MedicationPlanResponse(
        answer=answer,
        llm_model=model_used,
        plan_tier=tenant.subscription_tier,
        used_this_month=used_after,
        monthly_limit=limit,
        remaining=max(limit - used_after, 0),
    )


@app.get("/community/peer-insights", response_model=CommunityInsightsResponse)
def community_peer_insights(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=400, detail="User tenant is not configured")
    _require_pro_tier(
        tenant,
        "Community / Peer Insights is reserved for Pro and Enterprise plans.",
    )

    health_peer_ids = {
        row[0]
        for row in db.query(HealthRecord.user_id)
        .filter(HealthRecord.tenant_id == tenant.id, HealthRecord.user_id != current_user.id)
        .distinct()
        .all()
    }
    chat_peer_ids = {
        row[0]
        for row in db.query(ChatMessage.user_id)
        .filter(ChatMessage.tenant_id == tenant.id, ChatMessage.user_id != current_user.id)
        .distinct()
        .all()
    }
    nutrition_peer_ids = {
        row[0]
        for row in db.query(NutritionLog.user_id)
        .filter(NutritionLog.tenant_id == tenant.id, NutritionLog.user_id != current_user.id)
        .distinct()
        .all()
    }
    peer_ids = sorted(health_peer_ids | chat_peer_ids | nutrition_peer_ids)

    latest_peer_records = []
    peer_messages = []
    peer_logs = []
    if peer_ids:
        ordered_records = (
            db.query(HealthRecord)
            .filter(HealthRecord.tenant_id == tenant.id, HealthRecord.user_id.in_(peer_ids))
            .order_by(HealthRecord.user_id.asc(), HealthRecord.record_date.desc(), HealthRecord.id.desc())
            .all()
        )
        seen_record_users = set()
        for item in ordered_records:
            if item.user_id in seen_record_users:
                continue
            seen_record_users.add(item.user_id)
            latest_peer_records.append(item)

        peer_messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.tenant_id == tenant.id, ChatMessage.user_id.in_(peer_ids))
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(120)
            .all()
        )
        peer_logs = (
            db.query(NutritionLog)
            .filter(NutritionLog.tenant_id == tenant.id, NutritionLog.user_id.in_(peer_ids))
            .order_by(NutritionLog.entry_date.desc(), NutritionLog.created_at.desc())
            .limit(120)
            .all()
        )

    current_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.tenant_id == tenant.id, ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(12)
        .all()
    )
    current_logs = (
        db.query(NutritionLog)
        .filter(NutritionLog.tenant_id == tenant.id, NutritionLog.user_id == current_user.id)
        .order_by(NutritionLog.entry_date.desc(), NutritionLog.created_at.desc())
        .limit(12)
        .all()
    )

    payload = build_peer_insights(
        cohort_size=len(peer_ids),
        latest_peer_records=latest_peer_records,
        peer_messages=peer_messages,
        peer_logs=peer_logs,
        current_messages=current_messages,
        current_logs=current_logs,
    )
    return CommunityInsightsResponse(
        plan_tier=tenant.subscription_tier,
        cohort_size=payload["cohort_size"],
        overview=payload["overview"],
        matched_topics=payload["matched_topics"],
        habit_trends=[PeerInsightItem(**item) for item in payload["habit_trends"]],
        symptom_patterns=[PeerInsightItem(**item) for item in payload["symptom_patterns"]],
        nutrition_patterns=[PeerInsightItem(**item) for item in payload["nutrition_patterns"]],
        privacy_note=payload["privacy_note"],
    )


@app.post("/chatbot/ask-with-image", response_model=ChatAskResponse)
def chatbot_ask_with_image(
    payload: ChatAskImageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    text_q = payload.question.strip()
    if not text_q:
        raise HTTPException(status_code=400, detail="Question is required")

    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=400, detail="User tenant is not configured")

    used = _monthly_chat_usage(db, tenant.id, current_user.id)
    limit, image_limit = _effective_chat_limits(tenant, current_user)
    if used >= limit:
        raise HTTPException(status_code=429, detail="Monthly chatbot limit reached for your subscription plan")

    image_used = _monthly_image_chat_usage(db, tenant.id, current_user.id)
    if image_limit <= 0:
        raise HTTPException(status_code=403, detail="Your subscription plan does not include image chat")
    if image_used >= image_limit:
        raise HTTPException(status_code=429, detail="Monthly image-chat limit reached for your subscription plan")

    allowed_types = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
    mime_type = (payload.image_mime_type or "").strip().lower()
    if mime_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Unsupported image type. Use PNG/JPEG/WEBP")

    max_bytes = int(os.getenv("CHAT_IMAGE_MAX_BYTES", "5242880"))
    encoded = (payload.image_base64 or "").strip()
    if not encoded:
        raise HTTPException(status_code=400, detail="image_base64 is required")
    if encoded.startswith("data:") and "," in encoded:
        encoded = encoded.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Invalid base64 image payload")
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Image file is empty")
    if len(image_bytes) > max_bytes:
        raise HTTPException(status_code=400, detail="Image is too large")

    recent = (
        db.query(ChatMessage)
        .filter(ChatMessage.tenant_id == tenant.id, ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(6)
        .all()
    )
    history = []
    for item in reversed(recent):
        history.append({"role": "user", "content": item.question})
        history.append({"role": "assistant", "content": item.answer})

    context = _build_chat_context(db, current_user)
    try:
        answer, model_used, prompt_tokens, completion_tokens = ask_llm(
            question=text_q,
            context=context,
            history=history,
            image_bytes=image_bytes,
            image_mime_type=mime_type,
        )
    except RuntimeError as e:
        logger.warning(
            "LLM unavailable for chatbot_ask_with_image user_id=%s tenant_id=%s: %s",
            current_user.id,
            tenant.id,
            e,
        )
        raise HTTPException(
            status_code=502,
            detail="Pinecone image chat is unavailable right now. Please try again in a moment.",
        ) from e

    msg = ChatMessage(
        tenant_id=tenant.id,
        user_id=current_user.id,
        question=text_q,
        answer=answer,
        had_image=True,
        llm_model=model_used,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    db.add(msg)
    db.commit()

    used_after = used + 1
    img_used_after = image_used + 1
    return ChatAskResponse(
        answer=answer,
        llm_model=model_used,
        plan_tier=tenant.subscription_tier,
        used_this_month=used_after,
        monthly_limit=limit,
        remaining=max(limit - used_after, 0),
        image_used=True,
        image_used_this_month=img_used_after,
        image_monthly_limit=image_limit,
        image_remaining=max(image_limit - img_used_after, 0),
    )


@app.get("/chatbot/history", response_model=List[ChatMessageOut])
def chatbot_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.tenant_id == current_user.tenant_id, ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(30)
        .all()
    )


@app.get("/chatbot/usage")
def chatbot_usage(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=400, detail="User tenant is not configured")
    used = _monthly_chat_usage(db, tenant.id, current_user.id)
    limit, image_limit = _effective_chat_limits(tenant, current_user)
    image_used = _monthly_image_chat_usage(db, tenant.id, current_user.id)
    return {
        "plan_tier": tenant.subscription_tier,
        "used_this_month": used,
        "monthly_limit": limit,
        "remaining": max(limit - used, 0),
        "image_used_this_month": image_used,
        "image_monthly_limit": image_limit,
        "image_remaining": max(image_limit - image_used, 0),
    }


def _ingest_for_user(
    *,
    db: Session,
    tenant: Tenant,
    actor_user: User,
    payload: HealthRecordCreate,
) -> HealthIngestResponse:
    record_payload = payload.model_dump()
    if actor_user.location_permission_granted and actor_user.latitude is not None and actor_user.longitude is not None:
        auto = fetch_weather_and_air(actor_user.latitude, actor_user.longitude)
        if auto.get("weather_condition") is not None:
            record_payload["weather_condition"] = auto.get("weather_condition")
        if auto.get("temperature_c") is not None:
            record_payload["temperature_c"] = auto.get("temperature_c")
        if auto.get("uv_index") is not None:
            record_payload["uv_index"] = auto.get("uv_index")
        if auto.get("aqi") is not None:
            record_payload["aqi"] = auto.get("aqi")
        if actor_user.location_label and not record_payload.get("city"):
            record_payload["city"] = actor_user.location_label

    today_records = (
        db.query(func.count(HealthRecord.id))
        .filter(
            HealthRecord.tenant_id == tenant.id,
            func.date(HealthRecord.created_at) == func.current_date(),
        )
        .scalar()
        or 0
    )
    if today_records >= int(tenant.daily_record_limit):
        raise HTTPException(status_code=429, detail="Daily record limit reached for your subscription plan")

    record = HealthRecord(user_id=actor_user.id, tenant_id=tenant.id, **record_payload)
    db.add(record)
    try:
        db.commit()
        db.refresh(record)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save health record")

    scores = _risk_scores_for_user(db, actor_user.id)
    if not scores:
        hydration_msg = hydration_tip(record.hydration_liters)
        activity_msg = build_activity_tip(record.steps_count, record.activity_minutes)
        env_tips = build_environment_tips(
            aqi=record.aqi,
            uv_index=record.uv_index,
            temperature_c=record.temperature_c,
            weather_condition=record.weather_condition,
        )
        live_intel = {}
        if actor_user.location_permission_granted and actor_user.latitude is not None and actor_user.longitude is not None:
            live_intel = collect_live_intel(
                actor_user.latitude,
                actor_user.longitude,
                None,
                record.record_date,
            )
        outbreaks = live_intel.get("outbreak_alerts") or build_outbreak_alerts(record.record_date)
        env_tips.extend((live_intel.get("health_tips") or [])[:2])
        _create_notification(
            db=db,
            user=actor_user,
            event_type="health_record.ingested",
            title="Health record saved",
            message=f"Record for {record.record_date.isoformat()} was saved successfully.",
            severity="INFO",
            metadata={"record_id": record.id},
        )
        db.commit()
        return HealthIngestResponse(
            record=record,
            current_risk=None,
            risk_level=None,
            trend="INSUFFICIENT_DATA",
            next_risk_prediction=None,
            alert_triggered=False,
            alert_suppressed_due_to_plan=False,
            hydration_alert=hydration_msg,
            activity_tip=activity_msg,
            environment_tips=env_tips,
            outbreak_alerts=outbreaks,
        )

    current_score = round(scores[-1], 2)
    previous_score = scores[-2] if len(scores) > 1 else None
    trend = risk_trend(scores)
    risk_level = classify_risk(current_score)
    next_prediction = linear_forecast(scores, 1) if len(scores) >= 2 else current_score
    should_alert, _ = should_trigger_alert(current_score, previous_score)
    month_start, month_end = _current_month_bounds()
    monthly_alerts = (
        db.query(func.count(RiskHistory.id))
        .filter(
            RiskHistory.tenant_id == tenant.id,
            RiskHistory.alert_triggered.is_(True),
            RiskHistory.created_at >= month_start,
            RiskHistory.created_at < month_end,
        )
        .scalar()
        or 0
    )
    alert_suppressed = should_alert and monthly_alerts >= int(tenant.monthly_alert_limit)
    alert_triggered = (
        False if alert_suppressed else process_risk_alert(actor_user, current_score, previous_score, trend, db=db)
    )

    db.add(
        RiskHistory(
            user_id=actor_user.id,
            tenant_id=tenant.id,
            risk_score=current_score,
            risk_level=risk_level,
            trend=trend,
            alert_triggered=alert_triggered,
        )
    )
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to persist risk history")

    _create_notification(
        db=db,
        user=actor_user,
        event_type="health_record.ingested",
        title="Health record analyzed",
        message=f"Risk scored at {current_score:.2f} ({risk_level}) for {record.record_date.isoformat()}.",
        severity="INFO",
        metadata={"record_id": record.id, "risk_score": current_score, "risk_level": risk_level},
    )
    if alert_triggered:
        _create_notification(
            db=db,
            user=actor_user,
            event_type="risk.alert_triggered",
            title="High-risk alert triggered",
            message=f"A high-risk alert was triggered with score {current_score:.2f}.",
            severity="HIGH",
            metadata={"record_id": record.id, "trend": trend},
        )
    elif alert_suppressed:
        _create_notification(
            db=db,
            user=actor_user,
            event_type="risk.alert_suppressed",
            title="Alert suppressed by plan limit",
            message="Risk was elevated, but alert dispatch was suppressed by monthly plan limit.",
            severity="MEDIUM",
            metadata={"record_id": record.id, "risk_score": current_score},
        )
    db.commit()

    _dispatch_webhooks(
        db,
        tenant.id,
        "health_record.ingested",
        {
            "record_id": record.id,
            "user_id": actor_user.id,
            "risk_level": risk_level,
            "risk_score": current_score,
        },
    )
    if alert_triggered:
        _dispatch_webhooks(
            db,
            tenant.id,
            "risk.alert_triggered",
            {
                "record_id": record.id,
                "user_id": actor_user.id,
                "risk_level": risk_level,
                "risk_score": current_score,
                "trend": trend,
            },
        )

    hydration_msg = hydration_tip(record.hydration_liters)
    activity_msg = build_activity_tip(record.steps_count, record.activity_minutes)
    env_tips = build_environment_tips(
        aqi=record.aqi,
        uv_index=record.uv_index,
        temperature_c=record.temperature_c,
        weather_condition=record.weather_condition,
    )
    live_intel = {}
    if actor_user.location_permission_granted and actor_user.latitude is not None and actor_user.longitude is not None:
        live_intel = collect_live_intel(
            actor_user.latitude,
            actor_user.longitude,
            None,
            record.record_date,
        )
    outbreaks = live_intel.get("outbreak_alerts") or build_outbreak_alerts(record.record_date)
    env_tips.extend((live_intel.get("health_tips") or [])[:2])

    return HealthIngestResponse(
        record=record,
        current_risk=current_score,
        risk_level=risk_level,
        trend=trend,
        next_risk_prediction=next_prediction,
        alert_triggered=alert_triggered,
        alert_suppressed_due_to_plan=alert_suppressed,
        hydration_alert=hydration_msg,
        activity_tip=activity_msg,
        environment_tips=env_tips,
        outbreak_alerts=outbreaks,
    )


@app.post("/health-record", response_model=HealthIngestResponse)
def ingest_health_record(
    payload: HealthRecordCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=400, detail="User tenant is not configured")
    return _ingest_for_user(db=db, tenant=tenant, actor_user=current_user, payload=payload)


@app.post("/device/health-record", response_model=HealthIngestResponse)
def device_ingest_health_record(
    payload: HealthRecordCreate,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    user_id: int | None = None,
    db: Session = Depends(get_db),
):
    tenant = _get_tenant_from_api_key(db, x_api_key)
    if user_id is None:
        actor_user = db.query(User).filter(User.tenant_id == tenant.id).order_by(User.id.asc()).first()
    else:
        actor_user = db.query(User).filter(User.id == user_id, User.tenant_id == tenant.id).first()
    if not actor_user:
        raise HTTPException(status_code=404, detail="No eligible tenant user found for ingestion")
    return _ingest_for_user(db=db, tenant=tenant, actor_user=actor_user, payload=payload)


@app.get("/users/me/risk-summary")
def risk_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        summary = user_risk_summary(db, current_user.id, current_user.tenant_id)
    except OperationalError:
        raise HTTPException(status_code=503, detail="Database unavailable. Check database configuration.")

    if summary.get("current_risk") is None:
        return {**summary, "explanation": "Not enough medical history to generate a risk explanation"}

    explanation = explain_risk(score=float(summary["current_risk"]), trend=str(summary["trend"]).upper())
    return {**summary, "explanation": explanation}


@app.get("/my-health", response_model=List[HealthRecordOut])
def get_my_health(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return (
            db.query(HealthRecord)
            .filter(
                HealthRecord.user_id == current_user.id,
                HealthRecord.tenant_id == current_user.tenant_id,
            )
            .order_by(HealthRecord.record_date.desc())
            .all()
        )
    except OperationalError:
        raise HTTPException(status_code=503, detail="Database unavailable. Check database configuration.")


@app.get("/my-risk-history", response_model=List[RiskHistoryOut])
def get_my_risk_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(RiskHistory)
        .filter(
            RiskHistory.user_id == current_user.id,
            RiskHistory.tenant_id == current_user.tenant_id,
        )
        .order_by(RiskHistory.created_at.desc())
        .all()
    )


@app.get("/my-trends", response_model=TrendOut)
def get_my_trends(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scores = _risk_scores_for_user(db, current_user.id)
    if len(scores) < 2:
        return TrendOut(trend="INSUFFICIENT_DATA", sample_size=len(scores))
    return TrendOut(trend=risk_trend(scores), sample_size=len(scores))


@app.get("/my-trends/graph")
def get_my_trends_graph(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    points = _risk_series_for_user(db, current_user)
    svg = _build_trend_svg(points)
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/my-trends/graph/view", response_class=HTMLResponse)
def get_my_trends_graph_view(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    points = _risk_series_for_user(db, current_user)
    svg = _build_trend_svg(points)
    return (
        "<html><head><title>PCUBE Trend Graph</title></head>"
        "<body style='margin:0;padding:24px;background:#f8fafc;'>"
        "<div style='max-width:900px;margin:0 auto;'>"
        "<h2 style='font-family:Arial,sans-serif;color:#0f172a;'>Your Risk Trend</h2>"
        f"{svg}"
        "</div></body></html>"
    )


@app.get("/my-forecast", response_model=ForecastOut)
def get_my_forecast(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scores = _risk_scores_for_user(db, current_user.id)
    if not scores:
        return ForecastOut(next_risk_prediction=None, based_on_points=0)
    if len(scores) == 1:
        return ForecastOut(next_risk_prediction=scores[0], based_on_points=1)
    return ForecastOut(next_risk_prediction=linear_forecast(scores, 1), based_on_points=len(scores))


@app.get("/my/coach-cards", response_model=CoachSummaryOut)
def my_coach_cards(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    latest_record = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == current_user.id, HealthRecord.tenant_id == current_user.tenant_id)
        .order_by(HealthRecord.record_date.desc(), HealthRecord.id.desc())
        .first()
    )
    latest_risk = (
        db.query(RiskHistory)
        .filter(RiskHistory.user_id == current_user.id, RiskHistory.tenant_id == current_user.tenant_id)
        .order_by(RiskHistory.created_at.desc(), RiskHistory.id.desc())
        .first()
    )

    cards = []
    if latest_risk:
        cards.append(
            {
                "priority": "HIGH" if latest_risk.risk_level in {"HIGH", "CRITICAL"} else "MEDIUM",
                "title": "Risk Overview",
                "message": f"Current risk score is {latest_risk.risk_score:.2f} ({latest_risk.risk_level}). Trend: {latest_risk.trend}.",
            }
        )
    if latest_record:
        h_tip = hydration_tip(latest_record.hydration_liters)
        if h_tip:
            cards.append({"priority": "MEDIUM", "title": "Hydration", "message": h_tip})
        a_tip = build_activity_tip(latest_record.steps_count, latest_record.activity_minutes)
        if a_tip:
            cards.append({"priority": "LOW", "title": "Activity", "message": a_tip})
        env_tips = build_environment_tips(
            aqi=latest_record.aqi,
            uv_index=latest_record.uv_index,
            temperature_c=latest_record.temperature_c,
            weather_condition=latest_record.weather_condition,
        )
        for t in env_tips[:2]:
            cards.append({"priority": "HIGH", "title": "Environment", "message": t})

    if current_user.location_permission_granted and current_user.location_label:
        cards.append(
            {
                "priority": "LOW",
                "title": "Location Personalization",
                "message": f"Location-aware guidance is enabled for {current_user.location_label}.",
            }
        )
    elif not current_user.location_permission_granted:
        cards.append(
            {
                "priority": "LOW",
                "title": "Enable Location",
                "message": "Enable location permission to get hyper-local safety and weather guidance.",
            }
        )

    return CoachSummaryOut(cards=cards)


@app.get("/users/me/daily-plan", response_model=DailyPlanOut)
def users_daily_plan(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _daily_plan_for_user(db, current_user)


@app.patch("/users/me/daily-plan/{task_key}", response_model=DailyPlanOut)
def update_daily_plan_task(
    task_key: str,
    payload: DailyTaskUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    key = task_key.strip().lower()
    if key not in DAILY_TASK_KEYS:
        raise HTTPException(status_code=404, detail="Unknown daily task")
    today = datetime.utcnow().date()
    row = (
        db.query(DailyPlanCheck)
        .filter(
            DailyPlanCheck.tenant_id == current_user.tenant_id,
            DailyPlanCheck.user_id == current_user.id,
            DailyPlanCheck.plan_date == today,
            DailyPlanCheck.task_key == key,
        )
        .first()
    )
    if not row:
        row = DailyPlanCheck(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            plan_date=today,
            task_key=key,
            completed=bool(payload.completed),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
    else:
        row.completed = bool(payload.completed)
        row.updated_at = datetime.utcnow()
    db.commit()
    return _daily_plan_for_user(db, current_user)


@app.get("/users/me/notifications", response_model=List[NotificationOut])
def users_notifications(
    status_filter: str = "all",
    limit: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(UserNotification).filter(
        UserNotification.tenant_id == current_user.tenant_id,
        UserNotification.user_id == current_user.id,
    )
    normalized = status_filter.strip().upper()
    if normalized and normalized != "ALL":
        if normalized not in NOTIFICATION_STATUSES:
            raise HTTPException(status_code=400, detail="Unsupported notification status filter")
        query = query.filter(UserNotification.status == normalized)
    rows = query.order_by(UserNotification.created_at.desc()).limit(max(1, min(limit, 200))).all()
    return [_notification_out(item) for item in rows]


@app.patch("/users/me/notifications/{notification_id}", response_model=NotificationOut)
def update_notification_status(
    notification_id: int,
    payload: NotificationStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = (
        db.query(UserNotification)
        .filter(
            UserNotification.id == notification_id,
            UserNotification.tenant_id == current_user.tenant_id,
            UserNotification.user_id == current_user.id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Notification not found")
    status_value = payload.status.strip().upper()
    if status_value not in NOTIFICATION_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported notification status")
    item.status = status_value
    if status_value == "RESOLVED":
        item.resolved_at = datetime.utcnow()
        item.snoozed_until = None
    elif status_value == "SNOOZED":
        item.snoozed_until = datetime.utcnow() + timedelta(minutes=int(payload.snooze_minutes or 60))
    db.commit()
    db.refresh(item)
    return _notification_out(item)


@app.get("/users/me/engagement", response_model=EngagementOut)
def users_engagement(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _engagement_for_user(db, current_user)


@app.get("/users/me/dashboard", response_model=DashboardOut)
def users_dashboard(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    summary = user_risk_summary(db, current_user.id, current_user.tenant_id)
    forecast = get_my_forecast(current_user=current_user, db=db).model_dump()
    trends = get_my_trends(current_user=current_user, db=db).model_dump()
    engagement = _engagement_for_user(db, current_user)
    daily_plan = _daily_plan_for_user(db, current_user)
    unread = (
        db.query(func.count(UserNotification.id))
        .filter(
            UserNotification.tenant_id == current_user.tenant_id,
            UserNotification.user_id == current_user.id,
            UserNotification.status == "NEW",
        )
        .scalar()
        or 0
    )
    return DashboardOut(
        risk_summary=summary,
        forecast=forecast,
        trends=trends,
        engagement=engagement,
        daily_plan=daily_plan,
        unread_notifications=int(unread),
    )


@app.post("/users/me/demo/load", response_model=DemoSeedOut)
def load_demo_data(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not ENABLE_DEMO_TOOLS and not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Demo data tools are disabled in this environment")

    inserted_records = 0
    inserted_risk_rows = 0
    today = datetime.utcnow().date()
    for day_back in range(13, -1, -1):
        record_day = today - timedelta(days=day_back)
        exists = (
            db.query(HealthRecord)
            .filter(
                HealthRecord.user_id == current_user.id,
                HealthRecord.tenant_id == current_user.tenant_id,
                HealthRecord.record_date == record_day,
            )
            .first()
        )
        if exists:
            continue

        progress = max(0, 13 - day_back)
        rec = HealthRecord(
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            record_date=record_day,
            systolic_bp=142 - progress * 1.2,
            diastolic_bp=92 - progress * 0.7,
            bmi=29.5 - progress * 0.18,
            blood_glucose=150 - progress * 2.0,
            cholesterol=215 - progress * 1.1,
            smoking_status="never",
            activity_level="moderate",
            steps_count=3200 + progress * 450,
            activity_minutes=15 + progress * 2,
            hydration_liters=1.2 + progress * 0.07,
        )
        db.add(rec)
        db.flush()
        inserted_records += 1

        score = calculate_risk(rec)
        if score is not None:
            db.add(
                RiskHistory(
                    user_id=current_user.id,
                    tenant_id=current_user.tenant_id,
                    risk_score=float(score),
                    risk_level=classify_risk(float(score)),
                    trend="BASELINE" if inserted_risk_rows == 0 else "UPWARD" if float(score) > 0.66 else "DOWNWARD",
                    alert_triggered=False,
                )
            )
            inserted_risk_rows += 1

    if inserted_records > 0:
        _create_notification(
            db=db,
            user=current_user,
            event_type="demo.seeded",
            title="Demo data loaded",
            message=f"{inserted_records} historical records were added.",
            severity="INFO",
            metadata={"inserted_records": inserted_records},
        )
    db.commit()
    return DemoSeedOut(inserted_records=inserted_records, inserted_risk_rows=inserted_risk_rows)


@app.post("/users/me/share-links", response_model=ShareLinkOut)
def create_share_link(
    payload: ShareLinkCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token = secrets.token_urlsafe(24)
    expires_at = datetime.utcnow() + timedelta(hours=payload.expires_hours)
    item = ShareLink(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        token=token,
        lookback_days=int(payload.lookback_days),
        expires_at=expires_at,
        is_active=True,
    )
    db.add(item)
    _create_notification(
        db=db,
        user=current_user,
        event_type="share.created",
        title="Share link created",
        message=f"A caregiver/doctor share link was generated and expires on {expires_at.isoformat()}.",
        severity="MEDIUM",
        metadata={"token": token},
    )
    db.commit()
    base = str(request.base_url).rstrip("/")
    return ShareLinkOut(
        token=token,
        share_url=f"{base}/share/{token}",
        view_url=f"{base}/share/{token}/view",
        pdf_url=f"{base}/share/{token}/pdf",
        expires_at=expires_at,
        lookback_days=int(payload.lookback_days),
    )


def _resolve_share_link(db: Session, token: str) -> ShareLink:
    item = db.query(ShareLink).filter(ShareLink.token == token).first()
    if not item:
        raise HTTPException(status_code=404, detail="Share link not found")
    if not item.is_active:
        raise HTTPException(status_code=410, detail="Share link is inactive")
    if item.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Share link has expired")
    return item


@app.get("/share/{token}")
def open_share_link(token: str, db: Session = Depends(get_db)):
    item = _resolve_share_link(db, token)
    user = db.query(User).filter(User.id == item.user_id, User.tenant_id == item.tenant_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Shared user no longer exists")
    item.last_accessed_at = datetime.utcnow()
    db.commit()
    return _collect_share_bundle(db, user, item.lookback_days)


@app.get("/share/{token}/view", response_class=HTMLResponse)
def open_share_link_view(token: str, db: Session = Depends(get_db)):
    item = _resolve_share_link(db, token)
    user = db.query(User).filter(User.id == item.user_id, User.tenant_id == item.tenant_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Shared user no longer exists")
    bundle = _collect_share_bundle(db, user, item.lookback_days)
    item.last_accessed_at = datetime.utcnow()
    db.commit()
    rows = "".join(
        [
            f"<tr><td>{r.get('record_date')}</td><td>{r.get('systolic_bp')}/{r.get('diastolic_bp')}</td><td>{r.get('blood_glucose')}</td><td>{r.get('steps_count')}</td></tr>"
            for r in bundle.get("records", [])[:20]
        ]
    )
    return (
        "<html><head><title>PCUBE Shared Report</title></head><body style='font-family:Arial;padding:24px;'>"
        f"<h2>PCUBE Shared Health Report</h2><p>Patient: {bundle['patient']['full_name']}</p>"
        f"<p>Generated: {bundle['generated_at']}</p>"
        "<table border='1' cellpadding='8' cellspacing='0'><thead><tr><th>Date</th><th>BP</th><th>Glucose</th><th>Steps</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        "</body></html>"
    )


@app.get("/share/{token}/pdf")
def open_share_link_pdf(token: str, db: Session = Depends(get_db)):
    item = _resolve_share_link(db, token)
    user = db.query(User).filter(User.id == item.user_id, User.tenant_id == item.tenant_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Shared user no longer exists")
    bundle = _collect_share_bundle(db, user, item.lookback_days)
    lines = [
        "PCUBE Shared Health Report",
        f"Patient: {bundle['patient']['full_name']}",
        f"Email: {bundle['patient']['email']}",
        f"Generated: {bundle['generated_at']}",
        f"Lookback Days: {bundle['lookback_days']}",
        "",
    ]
    for row in bundle.get("records", [])[:25]:
        lines.append(
            f"{row.get('record_date')} | BP {row.get('systolic_bp')}/{row.get('diastolic_bp')} | "
            f"Glucose {row.get('blood_glucose')} | Steps {row.get('steps_count')}"
        )
    pdf_bytes = _build_simple_pdf(lines)
    item.last_accessed_at = datetime.utcnow()
    db.commit()
    headers = {"Content-Disposition": f"inline; filename=pcube_share_{token}.pdf"}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@app.get("/integrations/wearables/{provider}/oauth/start", response_model=OAuthStartOut)
def start_wearable_oauth(
    provider: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized = _normalize_wearable_provider(provider)
    cfg = _oauth_provider_config(normalized, request)
    if not cfg.get("client_id") or not cfg.get("client_secret") or not cfg.get("redirect_uri"):
        raise HTTPException(status_code=503, detail=f"OAuth credentials missing for {normalized}")

    state_token = secrets.token_urlsafe(24)
    expires_at = datetime.utcnow() + timedelta(minutes=15)
    db.add(
        OAuthState(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            provider=normalized,
            state=state_token,
            expires_at=expires_at,
            is_used=False,
        )
    )
    db.commit()

    if normalized == "google_fit":
        query = urllib.parse.urlencode(
            {
                "client_id": cfg["client_id"],
                "redirect_uri": cfg["redirect_uri"],
                "response_type": "code",
                "scope": cfg["scopes"],
                "state": state_token,
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
            }
        )
    else:
        query = urllib.parse.urlencode(
            {
                "client_id": cfg["client_id"],
                "redirect_uri": cfg["redirect_uri"],
                "response_type": "code",
                "scope": cfg["scopes"],
                "state": state_token,
            }
        )
    auth_url = f"{cfg['auth_url']}?{query}"
    return OAuthStartOut(provider=normalized, auth_url=auth_url, state=state_token, expires_at=expires_at)


@app.get("/integrations/wearables/{provider}/oauth/callback", response_class=HTMLResponse)
def wearable_oauth_callback(
    provider: str,
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    normalized = _normalize_wearable_provider(provider)
    if error:
        return HTMLResponse(content=f"<h3>OAuth failed: {error}</h3>", status_code=400)
    if not state or not code:
        return HTMLResponse(content="<h3>Missing OAuth state/code.</h3>", status_code=400)

    oauth_row = (
        db.query(OAuthState)
        .filter(OAuthState.provider == normalized, OAuthState.state == state)
        .first()
    )
    if not oauth_row or oauth_row.is_used or oauth_row.expires_at < datetime.utcnow():
        return HTMLResponse(content="<h3>OAuth state is invalid or expired.</h3>", status_code=400)
    user = db.query(User).filter(User.id == oauth_row.user_id, User.tenant_id == oauth_row.tenant_id).first()
    if not user:
        return HTMLResponse(content="<h3>User for OAuth state no longer exists.</h3>", status_code=404)

    cfg = _oauth_provider_config(normalized, None)
    if not cfg.get("client_id") or not cfg.get("client_secret") or not cfg.get("redirect_uri"):
        return HTMLResponse(content="<h3>Server OAuth credentials are missing.</h3>", status_code=503)

    token_payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg["redirect_uri"],
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if normalized == "google_fit":
        token_payload["client_id"] = cfg["client_id"]
        token_payload["client_secret"] = cfg["client_secret"]
    else:
        basic = base64.b64encode(f"{cfg['client_id']}:{cfg['client_secret']}".encode("utf-8")).decode("utf-8")
        headers["Authorization"] = f"Basic {basic}"

    req = urllib.request.Request(
        url=cfg["token_url"],
        data=urllib.parse.urlencode(token_payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        return HTMLResponse(content=f"<h3>Token exchange failed: {detail}</h3>", status_code=502)
    except Exception as exc:
        return HTMLResponse(content=f"<h3>Token exchange failed: {exc}</h3>", status_code=502)

    access_token = token_data.get("access_token")
    if not access_token:
        return HTMLResponse(content="<h3>Provider response did not include access_token.</h3>", status_code=502)

    refresh_token = token_data.get("refresh_token")
    expires_in = int(token_data.get("expires_in") or 0)
    token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in) if expires_in > 0 else None
    scope = token_data.get("scope")

    conn = (
        db.query(WearableConnection)
        .filter(
            WearableConnection.tenant_id == user.tenant_id,
            WearableConnection.user_id == user.id,
            WearableConnection.provider == normalized,
        )
        .first()
    )
    if not conn:
        conn = WearableConnection(
            tenant_id=user.tenant_id,
            user_id=user.id,
            provider=normalized,
            is_active=True,
        )
        db.add(conn)
    conn.access_token = access_token
    conn.refresh_token = refresh_token
    conn.scope = scope
    conn.token_expires_at = token_expires_at
    conn.is_active = True
    conn.last_sync_at = datetime.utcnow()

    oauth_row.is_used = True
    _create_notification(
        db=db,
        user=user,
        event_type="wearable.oauth.connected",
        title="Wearable connected",
        message=f"{normalized} OAuth connection completed successfully.",
        severity="INFO",
        metadata={"provider": normalized},
    )
    db.commit()
    return HTMLResponse(
        content=(
            "<html><body style='font-family:Arial;padding:24px;'>"
            f"<h2>{normalized} connected successfully.</h2>"
            "<p>You can return to the PCUBE app.</p>"
            "<script>setTimeout(function(){ window.location='/app/dashboard'; }, 1200);</script>"
            "</body></html>"
        )
    )


@app.get("/admin/users")
def admin_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(current_user)
    users = (
        db.query(User)
        .filter(User.tenant_id == current_user.tenant_id)
        .order_by(User.created_at.desc())
        .all()
    )
    return {
        "total": len(users),
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "tenant_id": u.tenant_id,
                "created_at": u.created_at,
            }
            for u in users
        ],
    }


@app.get("/admin/high-risk-users", response_model=List[AdminUserRiskOut])
def admin_high_risk_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(current_user)
    entries = (
        db.query(RiskHistory)
        .filter(RiskHistory.tenant_id == current_user.tenant_id)
        .order_by(RiskHistory.created_at.desc())
        .all()
    )
    latest_by_user = {}
    for entry in entries:
        if entry.user_id not in latest_by_user:
            latest_by_user[entry.user_id] = entry

    result = []
    for user_id, entry in latest_by_user.items():
        if entry.risk_level not in {"HIGH", "CRITICAL"}:
            continue
        user = db.query(User).filter(User.id == user_id, User.tenant_id == current_user.tenant_id).first()
        if not user:
            continue
        result.append(
            AdminUserRiskOut(
                user_id=user.id,
                email=user.email,
                full_name=user.full_name,
                latest_risk_score=entry.risk_score,
                latest_risk_level=entry.risk_level,
                recorded_at=entry.created_at,
            )
        )
    return result


@app.get("/admin/system-stats", response_model=AdminSystemStatsOut)
def admin_system_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(current_user)
    total_users = db.query(func.count(User.id)).filter(User.tenant_id == current_user.tenant_id).scalar() or 0
    total_records = db.query(func.count(HealthRecord.id)).filter(HealthRecord.tenant_id == current_user.tenant_id).scalar() or 0
    total_risk_history = db.query(func.count(RiskHistory.id)).filter(RiskHistory.tenant_id == current_user.tenant_id).scalar() or 0
    high_risk_users = len(admin_high_risk_users(current_user=current_user, db=db))
    return AdminSystemStatsOut(
        total_users=int(total_users),
        total_health_records=int(total_records),
        total_risk_history_entries=int(total_risk_history),
        high_risk_users=int(high_risk_users),
    )


@app.get("/admin/tenants", response_model=List[TenantOut])
def admin_list_tenants(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(current_user)
    return db.query(Tenant).order_by(Tenant.created_at.desc()).all()


@app.post("/admin/tenants", response_model=TenantOut)
def admin_create_tenant(
    payload: TenantCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Tenant name is required")
    existing = db.query(Tenant).filter(Tenant.name == name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Tenant already exists")
    defaults = PLAN_DEFAULTS["FREE"]
    tenant = Tenant(
        name=name,
        subscription_tier="FREE",
        daily_record_limit=defaults["daily_record_limit"],
        monthly_alert_limit=defaults["monthly_alert_limit"],
        monthly_chat_limit=defaults["monthly_chat_limit"],
        monthly_image_chat_limit=defaults["monthly_image_chat_limit"],
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@app.patch("/admin/tenants/{tenant_id}/plan", response_model=TenantOut)
def admin_update_tenant_plan(
    tenant_id: int,
    payload: TenantPlanUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    tier = payload.subscription_tier.strip().upper()
    if tier not in PLAN_DEFAULTS:
        raise HTTPException(status_code=400, detail="Unsupported subscription tier")
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.subscription_tier = tier
    tenant.daily_record_limit = PLAN_DEFAULTS[tier]["daily_record_limit"]
    tenant.monthly_alert_limit = PLAN_DEFAULTS[tier]["monthly_alert_limit"]
    tenant.monthly_chat_limit = PLAN_DEFAULTS[tier]["monthly_chat_limit"]
    tenant.monthly_image_chat_limit = PLAN_DEFAULTS[tier]["monthly_image_chat_limit"]
    db.commit()
    db.refresh(tenant)
    return tenant


@app.post("/admin/api-keys", response_model=ApiKeyCreated)
def admin_create_api_key(
    payload: ApiKeyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="API key name is required")
    raw_key = f"pcube_{secrets.token_urlsafe(32)}"
    key_hash = _hash_api_key(raw_key)
    key = ApiKey(
        tenant_id=current_user.tenant_id,
        name=name,
        key_prefix=raw_key[:12],
        key_hash=key_hash,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return ApiKeyCreated(
        id=key.id,
        tenant_id=key.tenant_id,
        name=key.name,
        key_prefix=key.key_prefix,
        api_key=raw_key,
        created_at=key.created_at,
    )


@app.get("/admin/api-keys", response_model=List[ApiKeyOut])
def admin_list_api_keys(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(current_user)
    return (
        db.query(ApiKey)
        .filter(ApiKey.tenant_id == current_user.tenant_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )


@app.patch("/admin/api-keys/{key_id}/deactivate", response_model=ApiKeyOut)
def admin_deactivate_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.tenant_id == current_user.tenant_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    key.is_active = False
    db.commit()
    db.refresh(key)
    return key


@app.post("/admin/webhooks", response_model=WebhookOut)
def admin_create_webhook(
    payload: WebhookCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    url = payload.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Webhook URL is required")
    events = set(payload.events or list(DEFAULT_WEBHOOK_EVENTS))
    if not events.issubset(DEFAULT_WEBHOOK_EVENTS):
        raise HTTPException(status_code=400, detail="Unsupported webhook event")
    hook = WebhookEndpoint(
        tenant_id=current_user.tenant_id,
        url=url,
        events_csv=",".join(sorted(events)),
        signing_secret=secrets.token_hex(32),
    )
    db.add(hook)
    db.commit()
    db.refresh(hook)
    return WebhookOut(
        id=hook.id,
        tenant_id=hook.tenant_id,
        url=hook.url,
        events=_parse_events(hook.events_csv),
        is_active=hook.is_active,
        created_at=hook.created_at,
    )


@app.get("/admin/webhooks", response_model=List[WebhookOut])
def admin_list_webhooks(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(current_user)
    hooks = (
        db.query(WebhookEndpoint)
        .filter(WebhookEndpoint.tenant_id == current_user.tenant_id)
        .order_by(WebhookEndpoint.created_at.desc())
        .all()
    )
    return [
        WebhookOut(
            id=hook.id,
            tenant_id=hook.tenant_id,
            url=hook.url,
            events=_parse_events(hook.events_csv),
            is_active=hook.is_active,
            created_at=hook.created_at,
        )
        for hook in hooks
    ]


@app.patch("/admin/webhooks/{webhook_id}/rotate-secret", response_model=WebhookSecretRotateOut)
def admin_rotate_webhook_secret(
    webhook_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    hook = (
        db.query(WebhookEndpoint)
        .filter(WebhookEndpoint.id == webhook_id, WebhookEndpoint.tenant_id == current_user.tenant_id)
        .first()
    )
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook endpoint not found")
    hook.signing_secret = secrets.token_hex(32)
    db.commit()
    return WebhookSecretRotateOut(id=hook.id, signing_secret=hook.signing_secret)
