from __future__ import annotations

from typing import Callable, Optional

from app.utils.logging import get_logger, log_event

_sanitizer = None
_tried = False


def _load_sanitizer(engine_path: Optional[str]) -> Optional[Callable[[str], str]]:
    global _sanitizer, _tried
    if _tried:
        return _sanitizer
    _tried = True
    if not engine_path:
        return None
    try:
        import sys
        from pathlib import Path

        root = str(Path(engine_path).resolve())
        if root not in sys.path:
            sys.path.insert(0, root)
        from src.ml.pii_sanitizer import PIISanitizer

        sanitizer = PIISanitizer(enable_ner=False)

        def _run(text: str) -> str:
            return sanitizer.sanitize(text)

        _sanitizer = _run
        return _sanitizer
    except Exception:
        _sanitizer = None
        return None


def guard_text(text: str, engine_path: Optional[str], on_hit: Optional[Callable[[], None]] = None) -> str:
    fn = _load_sanitizer(engine_path)
    if fn is None or not text:
        return text
    try:
        cleaned = fn(text)
    except Exception:
        return text
    if cleaned != text:
        log_event(get_logger(), "output_guard_hit", count=1)
        if on_hit:
            on_hit()
        return cleaned
    return text


def guard_many(texts: list[str], engine_path: Optional[str], on_hit: Optional[Callable[[], None]] = None) -> list[str]:
    return [guard_text(t, engine_path, on_hit) for t in texts]


def reset_guard_cache() -> None:
    global _sanitizer, _tried
    _sanitizer = None
    _tried = False
