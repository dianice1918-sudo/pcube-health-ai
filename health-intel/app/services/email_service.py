import smtplib
from email.message import EmailMessage
import os
from app.env import load_app_env

load_app_env()

def send_email(to_email: str, subject: str, body: str) -> bool:
    """Send email with error handling. Returns True on success, False on failure."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    try:
        smtp_port = int(os.getenv("SMTP_PORT", 587))
    except (TypeError, ValueError):
        smtp_port = 587

    # Validate required config
    if not all([smtp_host, smtp_user, smtp_pass, to_email]):
        print(f"Email config incomplete: host={smtp_host}, user={smtp_user}, to={to_email}")
        return False
    
    try:
        msg = EmailMessage()
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Email send failed to {to_email}: {e}")
        return False
