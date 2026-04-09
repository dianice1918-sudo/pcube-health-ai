from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.dependencies import get_current_user, get_db
from app.models import HealthRecord, User

router = APIRouter()

@router.get("/my-health")
def get_my_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    records = db.query(HealthRecord).filter(
        HealthRecord.user_id == current_user.id
    ).all()

    return records