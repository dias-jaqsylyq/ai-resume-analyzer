"""Builders for API Gateway HTTP API (payload 2.0) events with a verified JWT."""

import json
from types import SimpleNamespace

SUB = "11111111-2222-3333-4444-555555555555"


def api_event(route_key: str, body=None, sub: str | None = SUB, **extra) -> dict:
    authorizer = {"jwt": {"claims": {"sub": sub}, "scopes": None}} if sub else {}
    event = {
        "version": "2.0",
        "routeKey": route_key,
        "requestContext": {"authorizer": authorizer, "requestId": "api-req-1"},
        "isBase64Encoded": False,
        **extra,
    }
    if body is not None:
        event["body"] = body if isinstance(body, str) else json.dumps(body)
    return event


def lambda_context() -> SimpleNamespace:
    return SimpleNamespace(
        aws_request_id="req-1", function_name="test", get_remaining_time_in_millis=lambda: 3000
    )
