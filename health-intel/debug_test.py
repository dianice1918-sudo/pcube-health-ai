import sys
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

print("Step 1: Import database")
from app.database import SessionLocal, DATABASE_URL, engine
from app.models import Base
print("Success")

def _mask_db_url(url: str) -> str:
    if "://" not in url or "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    creds, host = rest.split("@", 1)
    if ":" not in creds:
        return f"{scheme}://***@{host}"
    user, _ = creds.split(":", 1)
    return f"{scheme}://{user}:***@{host}"

print(f"Resolved DB URL: {_mask_db_url(DATABASE_URL)}")

print("Step 2: Create session")
db = SessionLocal()
print("Success")

print("Step 3: Ensure schema")
Base.metadata.create_all(bind=engine)
print("Schema check complete")

print("Step 4: DB connectivity check")
try:
    db.execute(text("SELECT 1"))
    print("DB check passed")
except SQLAlchemyError as e:
    print(f"DB check failed: {e}")
    db.close()
    raise SystemExit(1)

print("Step 5: Import risk_history")
from app.risk_history import user_risk_summary
print("Success")

print("Step 6: Call user_risk_summary")
result = user_risk_summary(db, 1)
print(f"Result: {result}")

print("Step 7: Import explain_risk")
from app.explain import explain_risk
print("Success")

print("Step 8: Call explain_risk")
if result and result["current_risk"]:
    explanation = explain_risk(float(result["current_risk"]), str(result["trend"]).upper())
    print(f"Explanation: {explanation}")
else:
    print("No current_risk to explain")

db.close()
print("All steps completed successfully")
