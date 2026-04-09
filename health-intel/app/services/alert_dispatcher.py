from app.services.alert_engine import should_trigger_alert
from app.services.alert_messages import build_alert_message
from app.services.email_service import send_email
from app.services.push_service import send_push_notification
from app.models import PushDevice
from app.risk_history import user_risk_summary
from app.models import HealthRecord

def process_risk_alert(
    user,
    current_score,
    previous_score,
    trend,
    db=None,
):
    trigger, reason = should_trigger_alert(current_score, previous_score)

    if not trigger:
        return False

    # Derive user_name from available fields: prefer full_name, else email, else id
    user_name = user.full_name or user.email or f"User {user.id}"
    summary = user_risk_summary(db, user.id, tenant_id=user.tenant_id) if db is not None else None
    record_count = None
    if db is not None:
        record_count = (
            db.query(HealthRecord)
            .filter(HealthRecord.user_id == user.id, HealthRecord.tenant_id == user.tenant_id)
            .count()
        )
    message = build_alert_message(
        user_name=user_name,
        risk_level=reason,
        score=current_score,
        trend=trend if summary is None else summary["trend"],
        next_risk_prediction=None if summary is None else summary.get("next_risk_prediction"),
        record_count=record_count,
    )

    if user.email:
        send_email(user.email, "Health Risk Alert", message)

    if db is not None:
        devices = (
            db.query(PushDevice)
            .filter(
                PushDevice.tenant_id == user.tenant_id,
                PushDevice.user_id == user.id,
                PushDevice.is_active.is_(True),
            )
            .all()
        )
        for device in devices:
            send_push_notification(
                push_token=device.push_token,
                title="PCUBE Health Alert",
                body=f"Risk is {reason}. Score: {current_score:.2f}. Open the app for guidance.",
                data={
                    "risk_score": current_score,
                    "risk_level": reason,
                    "trend": trend,
                },
            )

    return True
