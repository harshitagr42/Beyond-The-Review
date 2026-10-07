from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id
        job_id = getattr(record, "job_id", None)
        if job_id:
            payload["job_id"] = job_id
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc_type"] = record.exc_info[0].__name__
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str = "app") -> logging.Logger:
    return logging.getLogger(name)


class RequestIdAdapter(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        extra = kwargs.setdefault("extra", {})
        if "request_id" not in extra and "request_id" in self.extra:
            extra["request_id"] = self.extra["request_id"]
        return msg, kwargs


def log_event(logger: logging.Logger, msg: str, **fields: Optional[Any]) -> None:
    extra: dict[str, Any] = {}
    extra_fields: dict[str, Any] = {}
    for k, v in fields.items():
        if v is None:
            continue
        if k in {"request_id", "job_id"}:
            extra[k] = v
        else:
            extra_fields[k] = v
    if extra_fields:
        extra["extra_fields"] = extra_fields
    logger.info(msg, extra=extra)
