from statistics import mean
from typing import Dict

def aggregate_risk_score(factors: Dict[str, float]) -> float:
    """
    Aggregate WHO risk factors into a single score.
    """
    return round(mean(factors.values()), 3)


def risk_level(score: float) -> str:
    if score >= 0.75:
        return "HIGH"
    elif score >= 0.45:
        return "MODERATE"
    return "LOW"
