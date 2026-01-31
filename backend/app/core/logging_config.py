"""Structured logging configuration for IsoCrates.

Provides JSON-formatted logs in production and human-readable text in development.
A contextvars-based request_id is automatically included in every log record
when set by the request context middleware.
"""

import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Optional


# Shared contextvar — set by request_context middleware, read by formatter.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line.

    Merges any ``extra`` fields from the record into the top-level object
    so callers can do ``logger.info("msg", extra={"doc_id": "abc"})`` and
    get ``{"doc_id": "abc"}`` alongside the standard fields.
    """

    # Keys that belong to the LogRecord itself and should not leak into output.
    _RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys())

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        rid = request_id_var.get("")
        if rid:
            payload["request_id"] = rid

        # Merge caller-supplied extra fields.
        for key, value in record.__dict__.items():
            if key not in self._RESERVED and key not in payload:
                payload[key] = value

        return json.dumps(payload, default=str)


def setup_logging(log_level: Optional[str] = None, log_format: Optional[str] = None) -> None:
    """Configure application-wide logging.

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL. Defaults to INFO.
        log_format: ``"json"`` for structured output, ``"text"`` for human-readable.
                    Defaults to ``"json"``.
    """
    level = (log_level or "INFO").upper()
    fmt = (log_format or "json").lower()

    handler = logging.StreamHandler(sys.stdout)

    if fmt == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Reduce noise from third-party libraries.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info("Logging configured", extra={"level": level, "format": fmt})
