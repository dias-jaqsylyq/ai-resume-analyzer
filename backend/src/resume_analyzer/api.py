"""Helpers for API Gateway HTTP API (payload format 2.0) Lambda handlers.

The JWT authorizer (Cognito user pool) has already checked the token before the Lambda runs;
the handler only reads the verified ``sub`` claim from the request context.
Error responses carry a fixed code and message, never request content.
"""

from __future__ import annotations

import base64
import json
from typing import Any


class ApiError(Exception):
    """An error that maps to an HTTP response with a fixed, content-free message."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message


def response(status: int, body: Any) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(body, separators=(",", ":")),
    }


def error_response(exc: ApiError) -> dict[str, Any]:
    return response(exc.status, {"error": exc.code, "message": exc.message})


def user_sub(event: dict[str, Any]) -> str:
    """The Cognito user id (``sub`` claim) verified by the API Gateway JWT authorizer."""
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
    sub = claims.get("sub")
    # sub is a UUID; reject anything that could break the key layout uploads/<sub>/<id>.pdf.
    if not isinstance(sub, str) or not sub or "/" in sub or "#" in sub or len(sub) > 128:
        raise ApiError(401, "unauthorized", "missing or invalid user identity")
    return sub


def json_body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, "invalid_body", "request body must be JSON") from None
    try:
        body = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        raise ApiError(400, "invalid_body", "request body must be JSON") from None
    if not isinstance(body, dict):
        raise ApiError(400, "invalid_body", "request body must be a JSON object")
    return body
