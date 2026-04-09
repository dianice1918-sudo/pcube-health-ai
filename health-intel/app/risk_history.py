from sqlalchemy.orm import Session
from app.models import HealthRecord
from app.services.risk_engine import (
    calculate_risk,
    classify_risk,
    predict_next_risk
)

def user_risk_summary(db: Session, user_id: int, tenant_id: int | None = None):
    query = db.query(HealthRecord).filter(HealthRecord.user_id == user_id)
    if tenant_id is not None:
        query = query.filter(HealthRecord.tenant_id == tenant_id)
    records = query.order_by(HealthRecord.record_date).all()

    if not records or len(records) < 2:
        return {
            "current_risk": None,
            "risk_level": None,
            "trend": "INSUFFICIENT_DATA",
            "next_risk_prediction": None
        }

    # ---- TIME SERIES ----
    # Calculate risk scores and filter out None values from incomplete records
    scores = []
    for r in records:
        risk_score = calculate_risk(r)
        if risk_score is not None:
            scores.append(risk_score)
    
    # Need at least 2 valid scores to compute trend
    if len(scores) < 2:
        return {
            "current_risk": None,
            "risk_level": None,
            "trend": "INSUFFICIENT_DATA",
            "next_risk_prediction": None
        }

    current_risk = round(scores[-1], 2)
    previous_risk = scores[-2]

    trend = (
        "WORSENING" if current_risk > previous_risk
        else "IMPROVING" if current_risk < previous_risk
        else "STABLE"
    )

    risk_level = classify_risk(current_risk)
    next_prediction = predict_next_risk(scores)

    return {
        "current_risk": current_risk,
        "risk_level": risk_level,
        "trend": trend,
        "next_risk_prediction": next_prediction
    }

