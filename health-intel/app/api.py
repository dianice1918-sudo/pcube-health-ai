from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.risk_history import user_risk_summary
from app.explain import explain_risk
from app.services.risk_history_series import get_risk_history
from app.services.alerts import generate_alert, send_alerts

app = FastAPI(
    title="PCUBE API",
    description="AI-powered preventive healthcare platform — Predict. Prevent. Protect.",
    version="1.0.0"
)



@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "Health-Intel API",
        "version": "1.0.0"
    }


@app.get("/users/{user_id}/risk-summary")
def risk_summary(user_id: int, db: Session = Depends(get_db)):
    try:
        summary = user_risk_summary(db, user_id)

        if summary is None:
            return {
                "user_id": user_id,
                "current_risk": None,
                "trend": None,
                "explanation": "No risk data found for this user"
            }

        if summary["current_risk"] is None:
            return {
                **summary,
                "explanation": "Not enough medical history to generate a risk explanation"
            }

        explanation = explain_risk(
            score=float(summary["current_risk"]),
            trend=str(summary["trend"]).upper()
        )

        alert = generate_alert(summary["current_risk"], summary.get("risk_level"))

        return {
            **summary,
            "alert": alert,
            "explanation": explanation
        }

    except Exception:
        import traceback
        error_detail = traceback.format_exc()
        print(f"Error in risk_summary: {error_detail}")
        raise HTTPException(status_code=500, detail="Internal server error")

@app.get("/users/{user_id}/risk-history")
def risk_history(user_id: int, db: Session = Depends(get_db)):
    history = get_risk_history(db, user_id)

    if not history:
        return {
            "user_id": user_id,
            "history": []
        }

    return {
        "user_id": user_id,
        "history": history
    }
    
@app.get("/test-alert")
def test_alert():
    result = send_alerts(
        user_email="victornkemuka@gmail.com",
        risk_score=0.90,
        risk_level="HIGH"
    )
    return {"result": result}
