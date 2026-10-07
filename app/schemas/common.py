from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ErrorBody(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "Invalid file format. Only .csv and .xlsx supported.",
                "code": "INVALID_FILE_FORMAT",
                "details": {},
            }
        }
    )

    error: str
    code: str
    details: dict[str, Any] = Field(default_factory=dict)


class VerbatimSample(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "v12",
                "text": "Charged twice for my monthly sub. Support email [EMAIL_REDACTED] hasn't replied.",
                "sentiment": "Negative",
            }
        }
    )

    id: str
    text: str
    sentiment: str


class FileInfo(BaseModel):
    name: str
    size_bytes: int
