from typing import Dict

def who_risk_factors(
    systolic_bp: float,
    diastolic_bp: float,
    bmi: float,
    glucose: float,
    smoking: bool
) -> Dict[str, float]:
    """
    WHO-aligned cardiovascular risk factor scoring.
    Scores are normalized (0–1).
    """

    risk = {}

    # Blood pressure
    if systolic_bp >= 160 or diastolic_bp >= 100:
        risk["blood_pressure"] = 1.0
    elif systolic_bp >= 140 or diastolic_bp >= 90:
        risk["blood_pressure"] = 0.7
    elif systolic_bp >= 130 or diastolic_bp >= 85:
        risk["blood_pressure"] = 0.4
    else:
        risk["blood_pressure"] = 0.1

    # BMI
    if bmi >= 35:
        risk["bmi"] = 1.0
    elif bmi >= 30:
        risk["bmi"] = 0.7
    elif bmi >= 25:
        risk["bmi"] = 0.4
    else:
        risk["bmi"] = 0.1

    # Glucose (mg/dL)
    if glucose >= 200:
        risk["glucose"] = 1.0
    elif glucose >= 126:
        risk["glucose"] = 0.7
    elif glucose >= 100:
        risk["glucose"] = 0.4
    else:
        risk["glucose"] = 0.1

    # Smoking
    risk["smoking"] = 0.8 if smoking else 0.1

    return risk
