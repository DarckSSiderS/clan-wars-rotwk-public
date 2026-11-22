from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin_user
from app.database import get_db
from app.models.user import User
from app.schemas.balance_simulation import StrategicSandboxRequest
from app.services.balance_simulation_catalog import BalanceSimulationCatalogLoader
from app.services.balance_simulation_service import BalanceSimulationService
from app.services.strategic_simulation_service import StrategicSimulationService


router = APIRouter(prefix="/admin/balance-simulator", tags=["admin balance simulator"])


@router.get("")
def run_balance_simulation(
    days: int = Query(30),
    rule_version: int | None = Query(None, ge=1),
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    if days not in {7, 14, 30}:
        raise HTTPException(status_code=422, detail="Горизонт должен быть 7, 14 или 30 дней")
    try:
        catalog = BalanceSimulationCatalogLoader().load(db, rule_version=rule_version)
        return BalanceSimulationService().run(catalog, days=days)
    except LookupError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/sandbox")
def run_strategic_sandbox(
    payload: StrategicSandboxRequest,
    rule_version: int | None = Query(None, ge=1),
    _current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    try:
        catalog = BalanceSimulationCatalogLoader().load(db, rule_version=rule_version)
        return StrategicSimulationService().run(catalog, payload)
    except LookupError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
