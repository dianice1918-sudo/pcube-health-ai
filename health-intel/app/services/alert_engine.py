from datetime import datetime

ALERT_THRESHOLDS = {
    "MODERATE": 0.66,
    "HIGH": 0.80,
    "CRITICAL": 0.90
}

def should_trigger_alert(current_score: float, previous_score: float | None):
    """
    Determines if an alert should be triggered
    """
    # Threshold breach should trigger even if there is no previous score.
    for level, threshold in ALERT_THRESHOLDS.items():
        if current_score >= threshold:
            return True, level

    # Rapid worsening
    if previous_score is not None and current_score - previous_score >= 0.10:
        return True, "RAPID_INCREASE"

    return False, None
