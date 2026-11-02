"""Lambda ``process-analysis``: SQS consumer that turns an uploaded CV into an analysis report.

Trigger: SQS queue fed by S3 ``ObjectCreated`` events for ``uploads/<user_sub>/<analysis_id>.pdf``
(batch size 1, ``ReportBatchItemFailures``).

Stages for one upload:
  a. load the analysis item (job description) and mark it PROCESSING; skip if already DONE;
     cache lookup by SHA-256(CV bytes + JD + model + prompt version)
  b. Textract text extraction (``resume_analyzer.textract``)
  c. analysis with Bedrock Nova or the offline mock (``resume_analyzer.bedrock``, BEDROCK_MODE)
  d. validated report → cache entry with TTL → analysis item DONE

Failures:
  - permanent (bad upload, missing analysis item, invalid model output after the retry,
    guardrail block): the item is marked FAILED and the message is acknowledged, because a
    retry would fail the same way and cost money again;
  - anything else (throttling, timeouts, AWS errors): the message is reported back to SQS and
    retried; on the last allowed receive the item is also marked FAILED, and SQS moves the
    message to the DLQ.

Logging rule: log ids, sizes, counts, durations and status only — never document text or
model output (see CLAUDE.md; enforced by tests/test_no_content_in_logs.py).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from functools import cache
from typing import Any
from urllib.parse import unquote_plus

import boto3
from botocore.config import Config

from resume_analyzer import bedrock, textract
from resume_analyzer.log import correlation_context, get_logger, inject_lambda_context
from resume_analyzer.report import InvalidReport
from resume_analyzer.store import DONE, Store, cache_key

logger = get_logger(__name__)

# Larger files are rejected before Textract is called (a CV is well under this).
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
UPLOADS_PREFIX = os.environ.get("UPLOADS_PREFIX", "uploads/")
# Must match the queue's redrive maxReceiveCount: the last receive marks the item FAILED.
MAX_RECEIVE_COUNT = int(os.environ.get("MAX_RECEIVE_COUNT", "3"))
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", str(24 * 3600)))


class InvalidUpload(ValueError):
    """The S3 object cannot be processed (unexpected key or too large)."""


class AnalysisNotFound(LookupError):
    """No analysis item for the upload (create-analysis must write it first)."""


# Retrying these cannot succeed, so they are not sent back to the queue.
PERMANENT_ERRORS = (InvalidUpload, AnalysisNotFound, InvalidReport, bedrock.AnalysisBlocked)


@dataclass(frozen=True)
class Upload:
    bucket: str
    key: str
    size: int
    etag: str | None
    user_sub: str
    analysis_id: str


@dataclass(frozen=True)
class Outcome:
    analysis_id: str
    status: str
    source: str  # "model", "cache" or "skipped"


@cache
def textract_client() -> Any:
    return boto3.client("textract")


@cache
def s3_client() -> Any:
    return boto3.client("s3")


@cache
def bedrock_client() -> Any:
    # Standard retry mode backs off on throttling; what still fails goes back to SQS.
    return boto3.client(
        "bedrock-runtime",
        config=Config(retries={"mode": "standard", "max_attempts": 3}, read_timeout=60),
    )


@cache
def store() -> Store:
    return Store(
        boto3.client("dynamodb"),
        analyses_table=os.environ["ANALYSES_TABLE"],
        cache_table=os.environ["CACHE_TABLE"],
    )


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
    return Upload(bucket, key, size, obj.get("eTag"), parts[0], analysis_id)


def cv_sha256(upload: Upload) -> str:
    """SHA-256 of the uploaded file, streamed from S3 (the ETag is not a content hash with KMS)."""
    body = s3_client().get_object(Bucket=upload.bucket, Key=upload.key)["Body"]
    digest = hashlib.sha256()
    for chunk in iter(lambda: body.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def extract(upload: Upload, context: Any) -> textract.Extraction:
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


def process_upload(upload: Upload, context: Any) -> Outcome:
    """Run all stages for one upload and write the report to DynamoDB."""
    db = store()
    item = db.get_analysis(upload.user_sub, upload.analysis_id)
    if item is None:
        raise AnalysisNotFound("no analysis item for this upload")
    if item.get("status") == DONE:  # duplicate delivery of an already finished upload
        logger.info("analysis already done, skipping", extra={"stage": "load"})
        return Outcome(upload.analysis_id, DONE, "skipped")
    if upload.size > MAX_UPLOAD_BYTES:
        raise InvalidUpload(f"upload is {upload.size} bytes, limit is {MAX_UPLOAD_BYTES}")
    job_description = item.get("job_description") or ""
    db.mark_processing(upload.user_sub, upload.analysis_id)

    model = bedrock.model_id()
    key = cache_key(cv_sha256(upload), job_description, model, bedrock.PROMPT_VERSION)
    cached = db.get_cached(key)
    if cached is not None:
        db.mark_done(upload.user_sub, upload.analysis_id, cached["result"], model, "cache")
        logger.info("analysis done", extra={"stage": "cache", "status": DONE, "cache": "hit"})
        return Outcome(upload.analysis_id, DONE, "cache")

    extraction = extract(upload, context)
    analysis = bedrock.analyzer(bedrock_client)(extraction.text, job_description)
    db.put_cached(key, analysis.report, analysis.model_id, CACHE_TTL_SECONDS)
    db.mark_done(upload.user_sub, upload.analysis_id, analysis.report, analysis.model_id, "model")
    logger.info(
        "analysis done",
        extra={
            "stage": "bedrock",
            "status": DONE,
            "cache": "miss",
            "model_id": analysis.model_id,
            "attempts": analysis.attempts,
            "input_tokens": analysis.input_tokens,
            "output_tokens": analysis.output_tokens,
            "duration_ms": analysis.duration_ms,
        },
    )
    return Outcome(upload.analysis_id, DONE, "model")


def _record_failure(upload: Upload, exc: Exception, receive_count: int) -> bool:
    """Log the failure and mark the item FAILED when no retry will follow.

    Returns True if the message must go back to SQS (transient error: retried, and after the
    last receive moved to the DLQ by the queue's redrive policy).
    """
    permanent = isinstance(exc, PERMANENT_ERRORS)
    last_attempt = permanent or receive_count >= MAX_RECEIVE_COUNT
    logger.error(
        "analysis failed",
        extra={
            "error_type": type(exc).__name__,
            "permanent": permanent,
            "last_attempt": last_attempt,
            "receive_count": receive_count,
        },
    )
    if last_attempt and not isinstance(exc, AnalysisNotFound):
        try:
            store().mark_failed(upload.user_sub, upload.analysis_id, type(exc).__name__)
        except Exception as mark_exc:  # keep the original failure as the outcome
            logger.error(
                "could not mark analysis failed", extra={"error_type": type(mark_exc).__name__}
            )
    return not permanent


def process_message(body: str, context: Any, receive_count: int = 1) -> list[Outcome]:
    """Handle one SQS message body (an S3 event notification).

    Raises when the message should be retried; permanent failures are recorded and swallowed.
    """
    event = json.loads(body)
    if event.get("Event") == "s3:TestEvent":
        logger.info("skipping s3 test event")
        return []
    results = []
    for s3_record in event.get("Records", []):
        try:
            upload = parse_upload(s3_record)
        except InvalidUpload:
            # Not ours to track: no analysis id to mark. Logged and dropped.
            logger.error(
                "ignoring upload with unexpected key", extra={"error_type": "InvalidUpload"}
            )
            continue
        with correlation_context(upload.analysis_id):
            try:
                results.append(process_upload(upload, context))
            except Exception as exc:
                if _record_failure(upload, exc, receive_count):
                    raise
    return results


@inject_lambda_context
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """SQS batch handler; returns the ids of failed messages so only those are retried."""
    failures = []
    for record in event.get("Records", []):
        message_id = record.get("messageId")
        receive_count = int(record.get("attributes", {}).get("ApproximateReceiveCount", "1"))
        try:
            process_message(record["body"], context, receive_count)
        except Exception as exc:
            logger.error(
                "message failed",
                extra={
                    "message_id": message_id,
                    "error_type": type(exc).__name__,
                    "receive_count": receive_count,
                },
                exc_info=True,
            )
            failures.append({"itemIdentifier": message_id})
    return {"batchItemFailures": failures}
