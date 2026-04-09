from twilio.rest import Client
import os

TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE = os.getenv("TWILIO_PHONE")

def send_sms(to: str, message: str) -> bool:
    """Send SMS with error handling. Returns True on success, False on failure."""
    # Validate required config
    if not all([TWILIO_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE, to]):
        print(f"Twilio config incomplete: sid={TWILIO_SID}, phone={TWILIO_PHONE}, to={to}")
        return False
    
    try:
        client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=TWILIO_PHONE,
            to=to
        )
        return True
    except Exception as e:
        print(f"SMS send failed to {to}: {e}")
        return False
