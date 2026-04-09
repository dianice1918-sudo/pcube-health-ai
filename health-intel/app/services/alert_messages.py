def build_alert_message(
    user_name: str,
    risk_level: str,
    score: float,
    trend: str,
    next_risk_prediction: float | None = None,
    record_count: int | None = None,
) -> str:
    trend_note = {
        "WORSENING": "Your recent readings suggest the risk is increasing.",
        "IMPROVING": "Your recent readings suggest the risk is easing.",
        "STABLE": "Your recent readings are holding steady.",
        "INSUFFICIENT_DATA": "There is not enough recent history to establish a trend yet.",
    }.get(str(trend).upper(), f"Trend: {trend}.")

    next_line = (
        f"Predicted next risk: {next_risk_prediction:.2f}\n"
        if isinstance(next_risk_prediction, (int, float))
        else "Predicted next risk: unavailable\n"
    )
    history_line = f"Recent records reviewed: {int(record_count)}\n" if record_count is not None else ""
    return (
        f"Hello {user_name},\n\n"
        "Here is your latest PCUBE health report.\n\n"
        f"Current risk level: {risk_level}\n"
        f"Risk score: {score:.2f}\n"
        f"Trend: {trend}\n"
        f"{next_line}"
        f"{history_line}\n"
        f"Summary: {trend_note}\n\n"
        "Recommended next steps:\n"
        "- Review any recent symptoms, medications, or lifestyle changes.\n"
        "- Monitor your readings over the next few days.\n"
        "- Seek medical care promptly if symptoms are severe or worsening.\n\n"
        "This is educational information, not a medical diagnosis."
    )
