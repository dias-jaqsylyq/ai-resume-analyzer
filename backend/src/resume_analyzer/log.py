"""Structured JSON logging with a correlation ID, shared by every Lambda.

One log line = one JSON object on stdout, which CloudWatch Logs stores as-is and
Logs Insights can query by field (e.g. `filter correlation_id = "..."`).

Usage in a handler::

    from resume_analyzer.log import get_logger, inject_lambda_context

    logger = get_logger(__name__)

    @inject_lambda_context(correlation_id_from=lambda event: event.get("analysis_id"))
    def handler(event, context):
        logger.info("analysis started", extra={"stage": "textract"})

Safety: CV text and PII must never be logged. As a safety net, values under
sensitive keys (see ``REDACTED_KEYS``) are replaced with ``[REDACTED]`` before
the line is written. Do not rely on it: log ids, sizes and statuses, not content.
"""

from __future__ import annotations

import contextlib
import contextvars
import functools
import json
import logging
import os
import sys
import uuid
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from typing import Any

ROOT_LOGGER_NAME = "resume_analyzer"
REDACTED = "[REDACTED]"
# Lower-cased keys whose values are never written to logs, at any nesting depth.
REDACTED_KEYS = frozenset(
    {
        "authorization",
        "body",
        "content",
        "cv",
        "cv_text",
        "document",
        "email",
        "job_description",
        "name",
        "phone",
        "prompt",
        "resume",
        "text",
        "token",
    }
)

# Attributes every LogRecord has; anything else on a record came from `extra=`.
_RESERVED_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "asctime",
    "taskName",
}

_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)
_lambda_fields: contextvars.ContextVar[Mapping[str, Any] | None] = contextvars.ContextVar(
    "lambda_fields", default=None
)
_cold_start = True


def get_correlation_id() -> str | None:
    """Return the correlation ID bound to the current invocation, if any."""
    return _correlation_id.get()


def set_correlation_id(value: str | None) -> contextvars.Token[str | None]:
    """Bind a correlation ID; pass the returned token to ``reset_correlation_id``."""
    return _correlation_id.set(value)


def reset_correlation_id(token: contextvars.Token[str | None]) -> None:
    _correlation_id.reset(token)


@contextlib.contextmanager
def correlation_context(value: str | None) -> Iterator[str]:
    """Bind ``value`` (or a new UUID when empty) as the correlation ID inside the block."""
    cid = value or str(uuid.uuid4())
    token = _correlation_id.set(cid)
    try:
        yield cid
    finally:
        _correlation_id.reset(token)


def redact(value: Any) -> Any:
    """Return a copy of ``value`` with sensitive keys replaced, recursively."""
    if isinstance(value, Mapping):
        return {
            k: REDACTED if str(k).lower() in REDACTED_KEYS else redact(v) for k, v in value.items()
        }
    if isinstance(value, list | tuple | set | frozenset):
        return [redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    """Format a record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": _correlation_id.get(),
        }
        entry.update(_lambda_fields.get() or {})
        extras = {k: v for k, v in vars(record).items() if k not in _RESERVED_ATTRS}
        entry.update(redact(extras))
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            entry["stack"] = self.formatStack(record.stack_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


def _configure_root() -> logging.Logger:
    root = logging.getLogger(ROOT_LOGGER_NAME)
    if not any(getattr(h, "_resume_analyzer", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        handler._resume_analyzer = True  # type: ignore[attr-defined]
        root.addHandler(handler)
        # The Lambda runtime puts its own plain-text handler on the Python root logger;
        # not propagating keeps each line written once, as JSON.
        root.propagate = False
    root.setLevel(os.environ.get("LOG_LEVEL", "INFO").upper())
    return root


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a JSON logger under the ``resume_analyzer`` namespace.

    The level comes from the ``LOG_LEVEL`` environment variable (default INFO).
    """
    root = _configure_root()
    if not name or name == ROOT_LOGGER_NAME:
        return root
    if not name.startswith(ROOT_LOGGER_NAME + "."):
        name = f"{ROOT_LOGGER_NAME}.{name}"
    return logging.getLogger(name)


def inject_lambda_context(
    handler: Callable[..., Any] | None = None,
    *,
    correlation_id_from: Callable[[Any], str | None] | None = None,
) -> Any:
    """Decorate a Lambda handler so every log line carries invocation fields.

    Adds ``function_name``, ``aws_request_id`` and ``cold_start`` to each line and binds a
    correlation ID: ``correlation_id_from(event)`` when it returns a value, otherwise the
    Lambda request ID. Both are cleared when the handler returns or raises.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(event: Any, context: Any, *args: Any, **kwargs: Any) -> Any:
            global _cold_start
            request_id = getattr(context, "aws_request_id", None)
            fields = {
                "function_name": getattr(context, "function_name", None),
                "aws_request_id": request_id,
                "cold_start": _cold_start,
            }
            _cold_start = False
            cid = None
            if correlation_id_from is not None:
                try:
                    cid = correlation_id_from(event)
                except Exception:  # a malformed event must not break the handler
                    cid = None
            fields_token = _lambda_fields.set(fields)
            try:
                with correlation_context(cid or request_id):
                    return func(event, context, *args, **kwargs)
            finally:
                _lambda_fields.reset(fields_token)

        return wrapper

    return decorator(handler) if handler is not None else decorator
