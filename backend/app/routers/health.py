from __future__ import annotations

from fastapi import APIRouter, Request

from app import __version__
from app.schemas.health import EngineHealth, HealthResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={200: {"description": "Service health"}},
)
def health(request: Request) -> HealthResponse:
    worker = request.app.state.worker
    st = worker.engine_status() if worker else {"mode": "mock", "status": "ready", "device": None}
    return HealthResponse(
        status="ok",
        engine=EngineHealth(mode=st.get("mode") or "mock", status=st.get("status") or "loading", device=st.get("device")),
        version=__version__,
    )
