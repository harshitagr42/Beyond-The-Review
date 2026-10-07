from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from fastapi.responses import FileResponse

from app.config import Settings
from app.deps import get_jobs, get_settings
from app.schemas.common import ErrorBody
from app.schemas.jobs import UploadAccepted
from app.services.ingestion_service import fast_validate_upload, stream_upload_to_disk
from app.services.job_service import JobService
from app.utils.errors import AppError

router = APIRouter(prefix="/reviews", tags=["reviews"])

ERROR_RESPONSES = {
    400: {"model": ErrorBody},
    401: {"model": ErrorBody},
    413: {"model": ErrorBody},
    422: {"model": ErrorBody},
    429: {"model": ErrorBody},
    503: {"model": ErrorBody},
}

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "data" / "sample_reviews.csv"


@router.post(
    "/upload",
    status_code=202,
    response_model=UploadAccepted,
    responses=ERROR_RESPONSES,
)
async def upload_reviews(
    response: Response,
    file: UploadFile = File(..., description="CSV or XLSX review file"),
    sheet: Optional[str] = Form(None, description="Optional XLSX sheet name"),
    settings: Settings = Depends(get_settings),
    jobs: JobService = Depends(get_jobs),
) -> UploadAccepted:
    filename = file.filename or "upload.csv"
    dest = settings.uploads_dir / f"{uuid4()}{Path(filename).suffix.lower()}"
    size, sha = await stream_upload_to_disk(file, dest, settings.max_file_size)
    try:
        fast_validate_upload(dest, filename, settings, sheet)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    body = jobs.create_from_upload(
        filename=Path(filename).name,
        size_bytes=size,
        sha256=sha,
        raw_path=dest,
        sheet=sheet,
    )
    response.headers["Location"] = body.status_url
    return body


@router.get(
    "/sample",
    responses={200: {"content": {"text/csv": {}}}, 404: {"model": ErrorBody}},
)
def download_sample() -> FileResponse:
    if not SAMPLE_PATH.is_file():
        raise AppError(404, "NOT_FOUND", "Sample file is not available.")
    return FileResponse(
        SAMPLE_PATH,
        media_type="text/csv",
        filename="sample_reviews.csv",
        headers={"Content-Disposition": 'attachment; filename="sample_reviews.csv"'},
    )
