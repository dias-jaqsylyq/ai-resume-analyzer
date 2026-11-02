"""Text extraction from a CV in S3 with Amazon Textract DetectDocumentText (async API).

The async API (``StartDocumentTextDetection`` + ``GetDocumentTextDetection``) is used because
the sync ``DetectDocumentText`` accepts only single-page PDFs. The job is polled from the
Lambda itself: CVs are a few pages, so a job finishes in seconds and no SNS topic is needed.

Retries are idempotent: the job is started with a ``ClientRequestToken`` derived from the
object, so a retried SQS message picks up the same Textract job instead of paying for a new one.
"""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from resume_analyzer.log import get_logger

logger = get_logger(__name__)

# Blocks per GetDocumentTextDetection page (API maximum).
MAX_RESULTS = 1000
_WHITESPACE = re.compile(r"\s+")


class TextractJobFailed(RuntimeError):
    """The Textract job finished with status FAILED."""


class ExtractionTimeout(TimeoutError):
    """The job did not finish before the Lambda deadline; the SQS retry resumes it."""


@dataclass(frozen=True)
class Extraction:
    """Clean text of a document. ``text`` is CV content: never log it."""

    text: str
    pages: int
    lines: int
    job_id: str
    status: str

    @property
    def chars(self) -> int:
        return len(self.text)


def request_token(bucket: str, key: str, etag: str | None) -> str:
    """Idempotency token for StartDocumentTextDetection (1-64 chars of [a-zA-Z0-9-_])."""
    return hashlib.sha256(f"{bucket}/{key}/{etag or ''}".encode()).hexdigest()


def blocks_to_text(blocks: Iterable[Mapping[str, Any]]) -> tuple[str, int]:
    """Turn Textract blocks into clean text: one line per LINE block, pages split by a blank line.

    Whitespace inside a line is collapsed and empty lines are dropped. Returns (text, line count).
    """
    pages: dict[int, list[str]] = {}
    for block in blocks:
        if block.get("BlockType") != "LINE":
            continue
        line = _WHITESPACE.sub(" ", block.get("Text", "")).strip()
        if line:
            pages.setdefault(int(block.get("Page", 1)), []).append(line)
    lines = sum(len(page) for page in pages.values())
    return "\n\n".join("\n".join(pages[n]) for n in sorted(pages)), lines


def extract_text(
    client: Any,
    bucket: str,
    key: str,
    *,
    token: str,
    remaining_ms: Callable[[], int],
    safety_ms: int = 10_000,
    sleep: Callable[[float], None] = time.sleep,
    first_delay: float = 1.0,
    max_delay: float = 5.0,
) -> Extraction:
    """Run a Textract text-detection job on ``s3://bucket/key`` and return its clean text.

    Polls until the job finishes or less than ``safety_ms`` of Lambda time is left, in which
    case ``ExtractionTimeout`` is raised so the message is retried (and the job resumed).
    """
    job_id = client.start_document_text_detection(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
        ClientRequestToken=token,
    )["JobId"]
    logger.info("textract job started", extra={"job_id": job_id})

    delay = first_delay
    while True:
        response = client.get_document_text_detection(JobId=job_id, MaxResults=MAX_RESULTS)
        status = response["JobStatus"]
        if status != "IN_PROGRESS":
            break
        if remaining_ms() - delay * 1000 < safety_ms:
            raise ExtractionTimeout(f"Textract job {job_id} still in progress")
        sleep(delay)
        delay = min(delay * 1.5, max_delay)

    if status == "FAILED":
        raise TextractJobFailed(f"Textract job {job_id} failed: {response.get('StatusMessage')}")
    if status == "PARTIAL_SUCCESS":
        logger.warning(
            "textract job partially succeeded",
            extra={"job_id": job_id, "warnings": len(response.get("Warnings", []))},
        )

    blocks = list(response.get("Blocks", []))
    pages = response.get("DocumentMetadata", {}).get("Pages", 0)
    next_token = response.get("NextToken")
    while next_token:
        response = client.get_document_text_detection(
            JobId=job_id, MaxResults=MAX_RESULTS, NextToken=next_token
        )
        blocks.extend(response.get("Blocks", []))
        next_token = response.get("NextToken")

    text, lines = blocks_to_text(blocks)
    return Extraction(text=text, pages=pages, lines=lines, job_id=job_id, status=status)
