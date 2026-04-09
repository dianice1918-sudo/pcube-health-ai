import json
import os
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import HealthRecord, RiskHistory, Tenant, User, UserNotification
from app.services.alert_engine import should_trigger_alert
from app.services.alert_dispatcher import process_risk_alert
from app.services.live_intel import alert_level_rank, collect_live_intel
from app.services.risk_engine import calculate_risk, classify_risk
from app.trend_analysis import risk_trend

_scheduler_instance = None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _current_month_bounds() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, 1, tzinfo=timezone.utc).replace(tzinfo=None)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
    return start, end


def run_daily_risk_check():
    print("Running daily PCUBE risk scan...")
    db: Session = SessionLocal()
    try:
        users = db.query(User).all()
        for user in users:
            records = (
                db.query(HealthRecord)
                .filter(
                    HealthRecord.user_id == user.id,
                    HealthRecord.tenant_id == user.tenant_id,
                )
                .order_by(HealthRecord.record_date)
                .all()
            )
            if not records:
                continue

            scores = []
            for rec in records:
                score = calculate_risk(rec)
                if score is not None:
                    scores.append(float(score))
            if not scores:
                continue

            current_score = round(scores[-1], 2)
            previous_score = scores[-2] if len(scores) > 1 else None
            trend = risk_trend(scores)
            risk_level = classify_risk(current_score)
            should_alert, _ = should_trigger_alert(current_score, previous_score)
            month_start, month_end = _current_month_bounds()
            tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
            monthly_limit = tenant.monthly_alert_limit if tenant else 20
            monthly_alerts = (
                db.query(func.count(RiskHistory.id))
                .filter(
                    RiskHistory.tenant_id == user.tenant_id,
                    RiskHistory.alert_triggered.is_(True),
                    RiskHistory.created_at >= month_start,
                    RiskHistory.created_at < month_end,
                )
                .scalar()
                or 0
            )
            alert_suppressed = should_alert and monthly_alerts >= int(monthly_limit)
            alert_triggered = (
                False
                if alert_suppressed
                else process_risk_alert(user, current_score, previous_score, trend, db=db)
            )

            db.add(
                RiskHistory(
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    risk_score=current_score,
                    risk_level=risk_level,
                    trend=trend,
                    alert_triggered=alert_triggered,
                )
            )
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"Daily risk check failed: {e}")
    finally:
        db.close()


def run_live_intel_check():
    print("Running hourly live-intel scan...")
    db: Session = SessionLocal()
    cooldown_minutes = max(15, _env_int("LIVE_INTEL_ALERT_COOLDOWN_MINUTES", 180))
    cutoff = datetime.utcnow() - timedelta(minutes=cooldown_minutes)
    try:
        users = (
            db.query(User)
            .filter(
                User.location_permission_granted.is_(True),
                User.latitude.isnot(None),
                User.longitude.isnot(None),
            )
            .all()
        )
        for user in users:
            intel = collect_live_intel(
                float(user.latitude),
                float(user.longitude),
                user.location_label,
                datetime.utcnow().date(),
            )
            level = str(intel.get("alert_level") or "NORMAL").upper()
            level_rank = alert_level_rank(level)
            if level_rank <= 0:
                continue

            event_type = "intel.urgent" if level_rank >= 2 else "intel.warning"
            already_recent = (
                db.query(UserNotification.id)
                .filter(
                    UserNotification.tenant_id == user.tenant_id,
                    UserNotification.user_id == user.id,
                    UserNotification.event_type == event_type,
                    UserNotification.created_at >= cutoff,
                )
                .first()
            )
            if already_recent:
                continue

            summary = str(intel.get("summary") or "Environment signal needs your attention.").strip()
            tips = intel.get("health_tips") if isinstance(intel.get("health_tips"), list) else []
            tip_line = f" Tip: {tips[0]}" if tips else ""
            title = "Urgent Health Intel Alert" if level_rank >= 2 else "Health Intel Warning"
            severity = "HIGH" if level_rank >= 2 else "MEDIUM"

            metadata = {
                "alert_level": level,
                "aqi": intel.get("aqi"),
                "uv_index": intel.get("uv_index"),
                "temperature_c": intel.get("temperature_c"),
                "outbreak_alerts": intel.get("outbreak_alerts", []),
                "generated_at": str(intel.get("generated_at")),
                "sources": intel.get("sources", {}),
            }

            db.add(
                UserNotification(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    event_type=event_type,
                    title=title,
                    message=f"{summary}{tip_line}",
                    severity=severity,
                    status="NEW",
                    metadata_json=json.dumps(metadata),
                    created_at=datetime.utcnow(),
                )
            )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Live intel check failed: {e}")
    finally:
        db.close()


def start_scheduler():
    global _scheduler_instance
    if _scheduler_instance is not None and _scheduler_instance.running:
        print("Scheduler already running")
        return _scheduler_instance

    risk_interval_hours = max(1, _env_int("RISK_CHECK_INTERVAL_HOURS", 24))
    live_intel_interval_minutes = max(10, _env_int("LIVE_INTEL_INTERVAL_MINUTES", 60))
    enable_live_intel_job = _env_bool("ENABLE_LIVE_INTEL_JOB", True)

    _scheduler_instance = BackgroundScheduler()
    _scheduler_instance.add_job(run_daily_risk_check, "interval", hours=risk_interval_hours, id="daily_risk_scan")
    if enable_live_intel_job:
        _scheduler_instance.add_job(
            run_live_intel_check,
            "interval",
            minutes=live_intel_interval_minutes,
            id="live_intel_scan",
        )
    _scheduler_instance.start()
    print(
        f"Scheduler started (risk every {risk_interval_hours}h"
        + (f", live-intel every {live_intel_interval_minutes}m)" if enable_live_intel_job else ", live-intel disabled)")
    )
    return _scheduler_instance


def stop_scheduler():
    global _scheduler_instance
    if _scheduler_instance is not None and _scheduler_instance.running:
        _scheduler_instance.shutdown()
        _scheduler_instance = None
        print("Scheduler stopped")
