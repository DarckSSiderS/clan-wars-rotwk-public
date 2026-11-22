from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.season_archive_service import SeasonArchiveService


router = APIRouter(prefix="/archives", tags=["season-archives"])
service = SeasonArchiveService()


@router.get("")
def list_archives(db: Session = Depends(get_db)):
    return {"seasons": service.list_seasons(db)}


@router.get("/{season_id}")
def get_archive(season_id: int, db: Session = Depends(get_db)):
    payload = service.detail(db, season_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Season archive not found")
    return payload


@router.get("/{season_id}/map.svg")
def get_archive_map(season_id: int, db: Session = Depends(get_db)):
    archive = service.get(db, season_id)
    if archive is None:
        raise HTTPException(status_code=404, detail="Season archive not found")
    return Response(
        archive.map_svg,
        media_type="image/svg+xml",
        headers={
            "Content-Security-Policy": "sandbox; default-src 'none'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )
