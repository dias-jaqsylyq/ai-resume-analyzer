"""Lambda ``read-analyses``: history and report, behind the API Gateway Cognito JWT authorizer.

Routes (HTTP API payload format 2.0):
- ``GET /analyses?limit=20&cursor=<id>`` — the caller's analyses, newest first (summaries);
- ``GET /analyses/{analysis_id}`` — one analysis with its report when DONE.

Every read is scoped to the partition ``USER#<sub>`` of the verified caller, so one user can
never read another user's analysis (an unknown id and someone else's id both return 404).

Logging rule: ids, counts and status only — never the job description or the report.
"""

from __future__ import annotations

import os
from functools import cache
from typing import Any

import boto3

from resume_analyzer import ids
from resume_analyzer.api import ApiError, error_response, response, user_sub
from resume_analyzer.log import get_logger, inject_lambda_context
from resume_analyzer.store import DONE, FAILED, Store

logger = get_logger(__name__)

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50


@cache
def store() -> Store:
    return Store(
        boto3.client("dynamodb"),
        analyses_table=os.environ["ANALYSES_TABLE"],
        cache_table=os.environ.get("CACHE_TABLE", ""),
    )


def _summary(item: dict[str, Any]) -> dict[str, Any]:
    analysis_id = item.get("analysis_id") or item.get("sk", "").removeprefix("ANALYSIS#")
    summary = {
        "analysis_id": analysis_id,
        "status": item.get("status"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "job_title": item.get("job_title"),
    }
    score = (item.get("result") or {}).get("ats_score")
    if score is not None:
        summary["ats_score"] = score
    if item.get("status") == FAILED:
        summary["error"] = item.get("error")
    return summary


def _detail(item: dict[str, Any], analysis_id: str) -> dict[str, Any]:
    detail = {**_summary(item), "analysis_id": analysis_id}
    detail.pop("ats_score", None)
    detail["job_description"] = item.get("job_description")
    detail["report"] = item.get("result") if item.get("status") == DONE else None
    if item.get("status") == DONE:
        detail["model_id"] = item.get("model_id")
    return detail


def _page_size(params: dict[str, str]) -> int:
    raw = params.get("limit")
    if raw is None:
        return DEFAULT_PAGE_SIZE
    if not raw.isdigit() or not 1 <= int(raw) <= MAX_PAGE_SIZE:
        raise ApiError(400, "invalid_limit", f"limit must be between 1 and {MAX_PAGE_SIZE}")
    return int(raw)


def list_history(sub: str, params: dict[str, str]) -> dict[str, Any]:
    limit = _page_size(params)
    cursor = params.get("cursor")
    if cursor is not None and not ids.is_ulid(cursor):
        raise ApiError(400, "invalid_cursor", "cursor is not valid")
    items, next_cursor = store().list_analyses(sub, limit, cursor)
    logger.info("history listed", extra={"count": len(items), "has_more": bool(next_cursor)})
    return response(200, {"items": [_summary(i) for i in items], "next_cursor": next_cursor})


def get_one(sub: str, analysis_id: str | None) -> dict[str, Any]:
    if not ids.is_ulid(analysis_id):
        raise ApiError(404, "not_found", "analysis not found")
    item = store().get_analysis(sub, analysis_id)
    if item is None:
        raise ApiError(404, "not_found", "analysis not found")
    logger.info("analysis read", extra={"analysis_id": analysis_id, "status": item.get("status")})
    return response(200, _detail(item, analysis_id))


def route(event: dict[str, Any]) -> dict[str, Any]:
    sub = user_sub(event)
    route_key = event.get("routeKey")
    if route_key == "GET /analyses":
        return list_history(sub, event.get("queryStringParameters") or {})
    if route_key == "GET /analyses/{analysis_id}":
        return get_one(sub, (event.get("pathParameters") or {}).get("analysis_id"))
    raise ApiError(404, "not_found", "route not found")


def _path_id(event: Any) -> str | None:
    value = (event.get("pathParameters") or {}).get("analysis_id")
    return value if ids.is_ulid(value) else None


@inject_lambda_context(correlation_id_from=_path_id)
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        return route(event)
    except ApiError as exc:
        logger.warning("request rejected", extra={"status_code": exc.status, "error": exc.code})
        return error_response(exc)
    except Exception as exc:
        logger.error("read analyses failed", extra={"error_type": type(exc).__name__})
        return error_response(ApiError(500, "internal_error", "could not read analyses"))
