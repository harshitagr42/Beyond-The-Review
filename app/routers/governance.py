from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.deps import get_governance
from app.schemas.common import ErrorBody
from app.schemas.governance import GovernanceMetrics
from app.services.governance_service import GovernanceService

router = APIRouter(prefix="/governance", tags=["governance"])


@router.get(
    "/metrics",
    response_model=GovernanceMetrics,
    responses={
        401: {"model": ErrorBody},
        404: {"model": ErrorBody},
        409: {"model": ErrorBody},
        422: {"model": ErrorBody},
    },
)
def governance_metrics(
    job_id: str = Query(...),
    gov: GovernanceService = Depends(get_governance),
) -> GovernanceMetrics:
    return gov.metrics(job_id)
