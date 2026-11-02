"""Lambda ``create-analysis``: ``POST /analyses`` behind the API Gateway Cognito JWT authorizer.

Request body: ``{"job_description": "...", "job_title": "..."}`` (``job_title`` optional).

1. writes the analyses item (pk ``USER#<sub>``, sk ``ANALYSIS#<ulid>``, status PENDING,
   job description) — process-analysis reads it when the CV arrives;
2. returns a pre-signed S3 POST for ``uploads/<sub>/<analysis_id>.pdf``. A POST policy (not a
   plain pre-signed PUT) lets S3 itself enforce the content type and the size limit.

The browser then sends the PDF straight to S3; the S3 event starts the pipeline.

Logging rule: ids, sizes and status only — never the job description (CLAUDE.md; enforced by
tests/test_no_content_in_logs.py).
"""

from __future__ import annotations

import os
from functools import cache
from typing import Any

import boto3
from botocore.config import Config

from resume_analyzer import ids
from resume_analyzer.api import ApiError, error_response, json_body, response, user_sub
from resume_analyzer.log import correlation_context, get_logger, inject_lambda_context
from resume_analyzer.store import PENDING, Store

logger = get_logger(__name__)

UPLOADS_PREFIX = os.environ.get("UPLOADS_PREFIX", "uploads/")
# Same limit process-analysis checks; here S3 enforces it at upload time.
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
UPLOAD_URL_TTL_SECONDS = int(os.environ.get("UPLOAD_URL_TTL_SECONDS", "300"))
# process-analysis sends at most 10k characters of the JD to the model.
MAX_JOB_DESCRIPTION_CHARS = 10_000
MAX_JOB_TITLE_CHARS = 200
CONTENT_TYPE = "application/pdf"


@cache
def s3_client() -> Any:
    # SigV4 + regional endpoint: required for SSE-KMS objects and avoids redirects.
    region = os.environ.get("AWS_REGION", "us-east-1")
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


@cache
def store() -> Store:
    return Store(
        boto3.client("dynamodb"),
        analyses_table=os.environ["ANALYSES_TABLE"],
        cache_table=os.environ.get("CACHE_TABLE", ""),
    )


def parse_request(body: dict[str, Any]) -> tuple[str, str | None]:
    jd = body.get("job_description")
    if not isinstance(jd, str) or not jd.strip():
        raise ApiError(400, "invalid_job_description", "job_description is required")
    jd = jd.strip()
    if len(jd) > MAX_JOB_DESCRIPTION_CHARS:
        raise ApiError(
            400,
            "invalid_job_description",
            f"job_description is longer than {MAX_JOB_DESCRIPTION_CHARS} characters",
        )
    title = body.get("job_title")
    if title is not None and not isinstance(title, str):
        raise ApiError(400, "invalid_job_title", "job_title must be a string")
    title = (title or "").strip() or None
    if title and len(title) > MAX_JOB_TITLE_CHARS:
        raise ApiError(
            400, "invalid_job_title", f"job_title is longer than {MAX_JOB_TITLE_CHARS} characters"
        )
    return jd, title


def upload_key(sub: str, analysis_id: str) -> str:
    return f"{UPLOADS_PREFIX}{sub}/{analysis_id}.pdf"


def presigned_upload(key: str) -> dict[str, Any]:
    """Pre-signed POST: S3 rejects other content types and files over MAX_UPLOAD_BYTES."""
    return s3_client().generate_presigned_post(
        Bucket=os.environ["UPLOADS_BUCKET"],
        Key=key,
        Fields={"Content-Type": CONTENT_TYPE},
        Conditions=[
            {"Content-Type": CONTENT_TYPE},
            ["content-length-range", 1, MAX_UPLOAD_BYTES],
        ],
        ExpiresIn=UPLOAD_URL_TTL_SECONDS,
    )


def create(event: dict[str, Any]) -> dict[str, Any]:
    sub = user_sub(event)
    jd, title = parse_request(json_body(event))
    analysis_id = ids.new_ulid()
    with correlation_context(analysis_id):
        key = upload_key(sub, analysis_id)
        # Signing is local (no AWS call), so do it first: no item is left behind if it fails.
        upload = presigned_upload(key)
        item = store().create_analysis(sub, analysis_id, jd, title)
        logger.info(
            "analysis created",
            extra={
                "status": PENDING,
                "job_description_chars": len(jd),
                "has_job_title": title is not None,
            },
        )
        return response(
            201,
            {
                "analysis_id": analysis_id,
                "status": PENDING,
                "created_at": item["created_at"],
                "upload": {
                    "method": "POST",
                    "url": upload["url"],
                    "fields": upload["fields"],
                    "max_bytes": MAX_UPLOAD_BYTES,
                    "content_type": CONTENT_TYPE,
                    "expires_in": UPLOAD_URL_TTL_SECONDS,
                },
            },
        )


@inject_lambda_context
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        return create(event)
    except ApiError as exc:
        logger.warning("request rejected", extra={"status_code": exc.status, "error": exc.code})
        return error_response(exc)
    except Exception as exc:
        logger.error("create analysis failed", extra={"error_type": type(exc).__name__})
        return error_response(ApiError(500, "internal_error", "could not create the analysis"))
