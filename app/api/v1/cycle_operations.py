"""Authenticated cycle operations; trusted initialization stays in the runtime."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user, get_onboarded_active_user
from app.core.time import as_utc, utc_now
from app.database import get_db
from app.models.campaign_cycle import CycleScoutRequest
from app.models.user import User
from app.services.cycle_plan_service import CyclePlanService
from app.services.cycle_reconnaissance_service import CycleReconnaissanceService
from app.services.cycle_reinforcement_store import CycleReinforcementStore
from app.services.cycle_startup_service import CycleStartupService
from app.services.cycle_interception_service import CycleInterceptionService


class OperationsRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def checked(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                raise HTTPException(409, 'Invalid operation input') from error
        return checked


router = APIRouter(tags=['cycle-operations'], route_class=OperationsRoute)
scouts = CycleReconnaissanceService()
reinforcements = CycleReinforcementStore()
startup = CycleStartupService()
Positive = Annotated[int, Field(strict=True, gt=0)]
Revision = Annotated[int, Field(strict=True, ge=1)]
CommandId = Annotated[str, Field(strict=True, min_length=1, max_length=120, pattern=r'\S')]
PathId = Annotated[int, Path(gt=0)]
Database = Annotated[Session, Depends(get_db)]
Actor = Annotated[User, Depends(get_current_active_user)]
Commander = Annotated[User, Depends(get_onboarded_active_user)]


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')


class TerritoryInput(Command):
    territory_id: Positive
    expected_revision: Revision


class ScoutInput(TerritoryInput):
    scout_user_id: Positive


class HelpInput(TerritoryInput):
    request_id: CommandId


class DispatchInput(TerritoryInput):
    dispatch_id: CommandId
    origin_territory_id: Positive | None = None
    request_id: CommandId | None = None
    recipient_clan_id: Positive
    player_user_ids: list[Positive] = Field(min_length=1, max_length=500)


class PreviewInput(Command):
    selected: list[Positive] = Field(min_length=3, max_length=3)


class ClaimInput(PreviewInput):
    expected_revision: Revision


def _run(db, action):
    try:
        return action()
    except PermissionError as error:
        db.rollback()
        raise HTTPException(403, str(error)) from error
    except ValueError as error:
        db.rollback()
        raise HTTPException(409, str(error)) from error
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, 'Concurrent operation; refresh before retry') from error


def _reinforcement_view(db, cycle_id, clan_id, user_id):
    return reinforcements.read(db, cycle_id=cycle_id, viewer_clan_id=clan_id,
                               actor_user_id=user_id)


@router.get('/{cycle_id}/interception')
def interception_detail(cycle_id: PathId, dispatch_id: Annotated[str, Query(min_length=1, max_length=120)],
                        db: Database, _user: Actor):
    return _run(db, lambda: CycleInterceptionService().read(db, cycle_id=cycle_id,
        dispatch_id=dispatch_id, now=utc_now()))


@router.post('/{cycle_id}/clans/{clan_id}/scout')
def request_scout(cycle_id: PathId, clan_id: PathId, payload: ScoutInput,
                  db: Database, user: Commander):
    def action():
        row = scouts.request(db, cycle_id=cycle_id, clan_id=clan_id,
                             actor_user_id=user.id, now=utc_now(), **payload.model_dump())
        result = dict(id=row.id, cycle_id=row.cycle_id, clan_id=row.clan_id,
                      territory_id=row.territory_id, scout_user_id=row.scout_user_id, scout_uuid=row.scout_uuid,
                      requested_at=as_utc(row.requested_at))
        db.commit()
        return result
    return _run(db, action)


@router.get('/{cycle_id}/clans/{clan_id}/scout/{request_id}/report')
def scout_report(cycle_id: PathId, clan_id: PathId, request_id: PathId,
                 db: Database, user: Actor):
    def action():
        CyclePlanService._permission(db, clan_id, user.id)
        row = db.get(CycleScoutRequest, request_id)
        if row is None or row.cycle_id != cycle_id or row.clan_id != clan_id:
            raise ValueError('Unknown scouting request for this cycle and clan')
        report = scouts.report(db, request_id=request_id, actor_user_id=user.id, now=utc_now())
        result = {'report': None if report is None else {'enemy_squads': report['enemy_squads']}}
        # A first report persists its anonymous cutoff snapshot.
        db.commit()
        return result
    return _run(db, action)


@router.get('/{cycle_id}/clans/{clan_id}/reinforcements')
def read_reinforcements(cycle_id: PathId, clan_id: PathId, db: Database, user: Actor):
    return _run(db, lambda: _reinforcement_view(db, cycle_id, clan_id, user.id))


@router.get('/{cycle_id}/clans/{clan_id}/preparation')
def preparation_context(cycle_id: PathId, clan_id: PathId, db: Database, user: Actor):
    from app.services.cycle_preparation_service import CyclePreparationService
    def action():
        result = CyclePreparationService().read(db, cycle_id=cycle_id, clan_id=clan_id, actor_id=user.id, now=utc_now())
        db.commit()
        return result
    return _run(db, action)


@router.get('/{cycle_id}/clans/{clan_id}/reinforcements/context')
def reinforcement_context(cycle_id: PathId, clan_id: PathId, db: Database, user: Actor):
    return _run(db, lambda: reinforcements.context(db, cycle_id=cycle_id, viewer_clan_id=clan_id,
                                                  actor_user_id=user.id, now=utc_now()))


@router.post('/{cycle_id}/clans/{clan_id}/reinforcements/requests')
def request_help(cycle_id: PathId, clan_id: PathId, payload: HelpInput,
                 db: Database, user: Commander):
    def action():
        reinforcements.request_help(db, cycle_id=cycle_id, clan_id=clan_id,
                                    actor_user_id=user.id, now=utc_now(), **payload.model_dump())
        result = _reinforcement_view(db, cycle_id, clan_id, user.id)
        db.commit()
        return result
    return _run(db, action)


@router.post('/{cycle_id}/clans/{clan_id}/reinforcements/dispatches')
def dispatch(cycle_id: PathId, clan_id: PathId, payload: DispatchInput,
             db: Database, user: Commander):
    def action():
        reinforcements.dispatch(db, cycle_id=cycle_id, sender_clan_id=clan_id,
                                actor_user_id=user.id, now=utc_now(), **payload.model_dump())
        result = _reinforcement_view(db, cycle_id, clan_id, user.id)
        db.commit()
        return result
    return _run(db, action)


@router.post('/{cycle_id}/clans/{clan_id}/startup/preview')
def preview_startup(cycle_id: PathId, clan_id: PathId, payload: PreviewInput,
                    db: Database, user: Commander):
    return _run(db, lambda: startup.preview(db, cycle_id=cycle_id, clan_id=clan_id,
                actor_id=user.id, selected=payload.selected, now=utc_now()))


@router.post('/{cycle_id}/clans/{clan_id}/startup/claim')
def claim_startup(cycle_id: PathId, clan_id: PathId, payload: ClaimInput,
                  db: Database, user: Commander):
    def action():
        row = startup.claim(db, cycle_id=cycle_id, clan_id=clan_id, actor_id=user.id,
                            now=utc_now(), **payload.model_dump())
        result = dict(clan_id=row.clan_id, revision=row.revision, status=row.status,
                      selected_lands=list(row.selected_lands), claimed_at=as_utc(row.claimed_at))
        db.commit()
        return result
    return _run(db, action)


class DefenceTemplateAssignment(Command):
    user_id: Positive
    territory_id: Positive


class DefenceTemplateInput(Command):
    expected_revision: Annotated[int, Field(strict=True, ge=0)]
    assignments: list[DefenceTemplateAssignment] = Field(max_length=500)


@router.get('/{cycle_id}/clans/{clan_id}/defence-template')
def read_defence_template(cycle_id: PathId, clan_id: PathId, db: Database, user: Actor):
    return _run(db, lambda: CyclePlanService().read_defence_template(db, cycle_id=cycle_id,
        clan_id=clan_id, actor_user_id=user.id, now=utc_now()))


@router.put('/{cycle_id}/clans/{clan_id}/defence-template')
def save_defence_template(cycle_id: PathId, clan_id: PathId, payload: DefenceTemplateInput,
                          db: Database, user: Commander):
    def action():
        result = CyclePlanService().save_defence_template(db, cycle_id=cycle_id, clan_id=clan_id,
            actor_user_id=user.id, now=utc_now(), **payload.model_dump())
        db.commit()
        return result
    return _run(db, action)
