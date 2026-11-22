from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.health_service import HealthService


router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/health/live")
def liveness():
    return {"status": "alive"}


@router.get("/health/ready")
def readiness(db: Session = Depends(get_db)):
    payload = HealthService().readiness(db)
    return JSONResponse(
        status_code=200 if payload["status"] == "ready" else 503,
        content=payload,
    )
