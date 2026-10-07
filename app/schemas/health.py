from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class EngineHealth(BaseModel):
    mode: str
    status: str
    device: Optional[str] = None


class HealthResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "engine": {"mode": "mock", "status": "ready", "device": "cpu"},
                "version": "1.0.0",
            }
        }
    )

    status: str
    engine: EngineHealth
    version: str
