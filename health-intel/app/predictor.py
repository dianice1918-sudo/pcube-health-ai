from sqlalchemy.orm import Session
from app.models import RiskPrediction
from app.who_rules import who_risk_factors
from app.risk_engine import aggregate_risk_score, risk_level


def predict_and_store(
    db: Session,
    user_id: int,
    systolic_bp: float,
    diastolic_bp: float,
    bmi: float,
    glucose: float,
    smoking: bool
):
    factors = who_risk_factors(
        systolic_bp, diastolic_bp, bmi, glucose, smoking
    )

    score = aggregate_risk_score(factors)
    level = risk_level(score)

    prediction = RiskPrediction(
        user_id=user_id,
        risk_score=score,
        risk_level=level,
        model_version="WHO_RULE_BASED_v1"
    )

    db.add(prediction)
    db.commit()
    db.refresh(prediction)

    return prediction
