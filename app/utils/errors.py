from __future__ import annotations

from typing import Any, Optional

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details if details is not None else {}

    def body(self) -> dict[str, Any]:
        return {"error": self.message, "code": self.code, "details": self.details}


def error_body(message: str, code: str, details: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {"error": message, "code": code, "details": details if details is not None else {}}


def json_error(status_code: int, message: str, code: str, details: Optional[dict[str, Any]] = None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error_body(message, code, details))


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return json_error(exc.status_code, exc.message, exc.code, exc.details)


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if isinstance(exc, AppError):
        return json_error(exc.status_code, exc.message, exc.code, exc.details)
    status = exc.status_code
    if status == 404:
        return json_error(404, "The requested resource was not found.", "NOT_FOUND")
    if status == 405:
        return json_error(405, "Method not allowed.", "METHOD_NOT_ALLOWED")
    if status == 401:
        return json_error(401, "Unauthorized.", "UNAUTHORIZED")
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return json_error(status, detail, "HTTP_ERROR")


async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    safe_errors = []
    for err in exc.errors():
        safe_errors.append(
            {
                "loc": [str(x) for x in err.get("loc", [])],
                "msg": err.get("msg"),
                "type": err.get("type"),
            }
        )
    return json_error(
        422,
        "Request validation failed.",
        "VALIDATION_ERROR",
        {"errors": safe_errors},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    from app.utils.logging import get_logger

    request_id = getattr(request.state, "request_id", None)
    get_logger().exception("unhandled_error", extra={"request_id": request_id, "exc_type": type(exc).__name__})
    return json_error(500, "An unexpected error occurred.", "INTERNAL_ERROR")
