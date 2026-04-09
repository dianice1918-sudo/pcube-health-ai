def send_whatsapp(to: str, message: str) -> bool:
    """
    Send WhatsApp message with error handling and config validation.
    Returns True on success, False on failure.
    """
    import os
    
    # Validate required config
    twilio_sid = os.getenv("TWILIO_SID")
    twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_from = "whatsapp:+14155238886"
    
    if not all([twilio_sid, twilio_auth_token, to]):
        print(f"WhatsApp config incomplete: sid={twilio_sid}, to={to}")
        return False
    
    # Validate destination format
    if not to:
        print("WhatsApp destination (to) is missing")
        return False
    
    try:
        from twilio.rest import Client
        
        client = Client(twilio_sid, twilio_auth_token)
        client.messages.create(
            body=message,
            from_=twilio_from,
            to=f"whatsapp:{to}"
        )
        return True
    except Exception as e:
        print(f"WhatsApp send failed to {to}: {e}")
        return False
