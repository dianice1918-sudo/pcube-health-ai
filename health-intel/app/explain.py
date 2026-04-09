def explain_risk(score: float, trend: str) -> str:
    if score >= 0.75:
        level = "high"
    elif score >= 0.45:
        level = "moderate"
    else:
        level = "low"

    trend_msg = {
        "WORSENING": "Your health indicators show a worsening trend over time.",
        "IMPROVING": "Your health indicators show improvement over time.",
        "STABLE": "Your health indicators remain stable.",
        "INSUFFICIENT_DATA": "There is not enough historical data to determine a trend."
    }.get(trend, "")

    return (
        f"Your overall health risk is currently assessed as {level}. "
        f"{trend_msg} "
        "This assessment is based on recorded health metrics and is not a medical diagnosis. "
        "Consult a healthcare professional for clinical advice."
    )
