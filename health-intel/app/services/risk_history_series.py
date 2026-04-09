from sqlalchemy.orm import Session
from app.models import HealthRecord
from app.services.risk_engine import calculate_risk

def get_risk_history(db: Session, user_id: int):
    records = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == user_id)
        .order_by(HealthRecord.created_at)
        .all()
    )

    history = []
    for r in records:
        history.append({
            "date": r.created_at.isoformat() if r.created_at else None,
            "risk_score": calculate_risk(r)
        })

    return history
