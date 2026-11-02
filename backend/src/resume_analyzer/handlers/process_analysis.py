"""Lambda ``process-analysis``: SQS consumer that turns an uploaded CV into an analysis.

Trigger: SQS queue fed by S3 ``ObjectCreated`` events for ``uploads/<user_sub>/<analysis_id>.pdf``
(batch size 1, ``ReportBatchItemFailures``). A failed record is reported back to SQS, retried,
and moved to the DLQ after the queue's ``maxReceiveCount``.

Stages: (b) Textract text extraction — this module. Model analysis and the DynamoDB write
are added in RA-8.

Logging rule: log ids, sizes, counts, durations and status only — never document text or
model output (see CLAUDE.md; enforced by tests/test_no_content_in_logs.py).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from functools import cache
from typing import Any
from urllib.parse import unquote_plus

import boto3

from resume_analyzer import textract
from resume_analyzer.log import correlation_context, get_logger, inject_lambda_context

logger = get_logger(__name__)

# Larger files are rejected before Textract is called (a CV is well under this).
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
UPLOADS_PREFIX = os.environ.get("UPLOADS_PREFIX", "uploads/")


class InvalidUpload(ValueError):
    """The S3 object cannot be processed (unexpected key or too large)."""


@dataclass(frozen=True)
class Upload:
    bucket: str
    key: str
    size: int
    etag: str | None
    user_sub: str
    analysis_id: str


@cache
def textract_client() -> Any:
    return boto3.client("textract")


def parse_upload(s3_record: dict[str, Any]) -> Upload:
    """Read bucket/key/size from one S3 event record and check the key layout."""
    bucket = s3_record["s3"]["bucket"]["name"]
    obj = s3_record["s3"]["object"]
    key = unquote_plus(obj["key"])  # S3 event keys are URL-encoded
    size = int(obj.get("size", 0))

    parts = key.removeprefix(UPLOADS_PREFIX).split("/") if key.startswith(UPLOADS_PREFIX) else []
    if len(parts) != 2 or not parts[0] or not parts[1].lower().endswith(".pdf"):
        raise InvalidUpload("unexpected upload key layout")
    analysis_id = parts[1][: -len(".pdf")]
    if not analysis_id:
        raise InvalidUpload("unexpected upload key layout")
    if size > MAX_UPLOAD_BYTES:
        raise InvalidUpload(f"upload is {size} bytes, limit is {MAX_UPLOAD_BYTES}")
    return Upload(bucket, key, size, obj.get("eTag"), parts[0], analysis_id)


def process_upload(upload: Upload, context: Any) -> textract.Extraction:
    """Extract the CV text of one upload. The caller must not log the returned text."""
    started = time.monotonic()
    extraction = textract.extract_text(
        textract_client(),
        upload.bucket,
        upload.key,
        token=textract.request_token(upload.bucket, upload.key, upload.etag),
        remaining_ms=context.get_remaining_time_in_millis,
    )
    logger.info(
        "text extracted",
        extra={
            "stage": "textract",
            "status": extraction.status,
            "size_bytes": upload.size,
            "pages": extraction.pages,
            "lines": extraction.lines,
            "chars": extraction.chars,
            "duration_ms": round((time.monotonic() - started) * 1000),
        },
    )
    return extraction


def process_message(body: str, context: Any) -> list[textract.Extraction]:
    """Handle one SQS message body (an S3 event notification)."""
    event = json.loads(body)
    if event.get("Event") == "s3:TestEvent":
        logger.info("skipping s3 test event")
        return []
    results = []
    for s3_record in event.get("Records", []):
        upload = parse_upload(s3_record)
        with correlation_context(upload.analysis_id):
            results.append(process_upload(upload, context))
    return results


@inject_lambda_context
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """SQS batch handler; returns the ids of failed messages so only those are retried."""
    failures = []
    for record in event.get("Records", []):
        message_id = record.get("messageId")
        try:
            process_message(record["body"], context)
        except Exception as exc:
            logger.error(
                "message failed",
                extra={
                    "message_id": message_id,
                    "error_type": type(exc).__name__,
                    "receive_count": record.get("attributes", {}).get("ApproximateReceiveCount"),
                },
                exc_info=True,
            )
            failures.append({"itemIdentifier": message_id})
    return {"batchItemFailures": failures}
