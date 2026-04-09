from app.services.email_service import send_email


def generate_alert(risk_score: float, risk_level: str):
    if risk_score >= 0.85:
        return {"level": "CRITICAL", "message": "Immediate medical attention is recommended."}
    if risk_score >= 0.70:
        return {"level": "HIGH", "message": "Your health risk is increasing. Monitor closely."}
    return None


def _build_email_report(risk_score: float, risk_level: str) -> str:
    alert = generate_alert(risk_score, risk_level)
    if not alert:
        return ""

    return (
        "PCUBE Health Report\n\n"
        f"Risk level: {alert['level']}\n"
        f"Risk score: {risk_score:.2f}\n\n"
        f"{alert['message']}\n\n"
        "What to do next:\n"
        "- Review recent symptoms, medications, hydration, and activity.\n"
        "- Check your latest readings again soon.\n"
        "- Seek urgent medical care if symptoms are severe or worsening.\n\n"
        "This report is educational and not a diagnosis."
    )


def send_alerts(user_phone, user_email, risk_score, risk_level):
    alert = generate_alert(risk_score, risk_level)
    if not alert:
        return "No alert triggered"

    message = _build_email_report(risk_score, risk_level)
    if user_email:
        send_email(user_email, "PCUBE Health Report", message)

    return "Email report sent"

