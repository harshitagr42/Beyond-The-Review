from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.deps import get_jobs
from app.schemas.common import ErrorBody
from app.schemas.jobs import JobStatus
from app.services.job_service import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "/{job_id}/status",
    response_model=JobStatus,
    responses={401: {"model": ErrorBody}, 404: {"model": ErrorBody}, 422: {"model": ErrorBody}},
)
def job_status(job_id: str, jobs: JobService = Depends(get_jobs)) -> JobStatus:
    job_id = jobs.require_job_id(job_id)
    return jobs.status(job_id)


@router.delete(
    "/{job_id}",
    status_code=204,
    response_class=Response,
    responses={
        401: {"model": ErrorBody},
        404: {"model": ErrorBody},
        409: {"model": ErrorBody},
        422: {"model": ErrorBody},
    },
)
def delete_job(job_id: str, jobs: JobService = Depends(get_jobs)) -> Response:
    job_id = jobs.require_job_id(job_id)
    jobs.delete(job_id)
    return Response(status_code=204)
