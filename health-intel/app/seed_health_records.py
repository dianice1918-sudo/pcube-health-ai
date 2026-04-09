from datetime import date
from app.database import SessionLocal
from app.models import HealthRecord, User

db = SessionLocal()

# Create user if doesn't exist
user = db.query(User).filter(User.id == 1).first()
if not user:
    # Use a pre-hashed password to avoid bcrypt compatibility issues during seeding
    # In production, use proper password hashing via the registration endpoint
    pre_hashed_pw = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5YmMxSUFUH60m"  # hash of "password123"
    user = User(
        id=1,
        email="demo@example.com",
        full_name="Demo User",
        password_hash=pre_hashed_pw
    )
    db.add(user)
    db.commit()

records = [
    HealthRecord(
        user_id=1,
        record_date=date(2024, 1, 1),
        systolic_bp=120,
        diastolic_bp=80,
        bmi=24,
        blood_glucose=95,
        cholesterol=200,
        smoking_status="never",
        activity_level="moderate"
    ),
    HealthRecord(
        user_id=1,
        record_date=date(2024, 2, 1),
        systolic_bp=135,
        diastolic_bp=85,
        bmi=26,
        blood_glucose=110,
        cholesterol=220,
        smoking_status="never",
        activity_level="moderate"
    ),
    HealthRecord(
        user_id=1,
        record_date=date(2024, 3, 1),
        systolic_bp=150,
        diastolic_bp=95,
        bmi=28,
        blood_glucose=130,
        cholesterol=240,
        smoking_status="former",
        activity_level="low"
    ),
]

db.add_all(records)
db.commit()
db.close()

print("✅ Sample health records inserted")

