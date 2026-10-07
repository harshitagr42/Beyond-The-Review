from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.deps import get_themes
from app.schemas.common import ErrorBody
from app.schemas.themes import ThemesResponse, VerbatimsResponse
from app.services.theme_service import ThemeService

router = APIRouter(prefix="/themes", tags=["themes"])

JOB_ERRORS = {
    401: {"model": ErrorBody},
    404: {"model": ErrorBody},
    409: {"model": ErrorBody},
    422: {"model": ErrorBody},
}


@router.get("", response_model=ThemesResponse, responses=JOB_ERRORS)
def list_themes(
    job_id: str = Query(...),
    sort: str = Query("priority"),
    general_class: Optional[str] = Query(None),
    themes: ThemeService = Depends(get_themes),
) -> ThemesResponse:
    return themes.list_themes(job_id, sort=sort, general_class=general_class)


@router.get("/{theme_id}/verbatims", response_model=VerbatimsResponse, responses=JOB_ERRORS)
def theme_verbatims(
    theme_id: str,
    job_id: str = Query(...),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sentiment: Optional[str] = Query(None),
    sort: str = Query("most_negative"),
    themes: ThemeService = Depends(get_themes),
) -> VerbatimsResponse:
    return themes.verbatims(theme_id, job_id, page=page, limit=limit, sentiment=sentiment, sort=sort)
