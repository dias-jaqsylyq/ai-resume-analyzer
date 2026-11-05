"""Benchmarks for docs/metrics.md: latency and cost per analysis.

Three subcommands, all printing only counts, timings and dollar amounts (never CV or report
text):

    # 1. In-process latency of process-analysis in mock mode (no AWS, runs anywhere / in CI).
    #    Textract and DynamoDB are replaced by in-memory fakes, so this is the handler's own
    #    compute time, not end-to-end latency.
    cd backend && PYTHONPATH=src python3 scripts/benchmark.py local --runs 500

    # 2. Cost model per CV and per 100 CVs from the code's limits and AWS list prices
    #    (an estimate, not a bill; prices from the AWS Price List API, us-east-1).
    cd backend && PYTHONPATH=src python3 scripts/benchmark.py cost

    # 3. End-to-end latency on the deployed stack (the owner, in AWS CloudShell).
    #    Upload -> DONE for N fresh analyses (each with a unique job description, so the cache
    #    misses), then one repeat of the first one (cache hit). Same env as scripts/api_smoke.py.
    export API_URL=... CLIENT_ID=... SMOKE_EMAIL=... SMOKE_PASSWORD=...
    cd backend && python3 scripts/benchmark.py e2e cv.pdf --runs 10

The e2e run creates N+1 analyses in the user's history and costs N Textract pages per CV page
(inside the Textract free tier for new accounts; $0.0015 per page otherwise). In mock mode
there is no Bedrock charge.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# --- shared ----------------------------------------------------------------------------------


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (no interpolation): the smallest value with >= pct% at or below."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


def summary(name: str, values: list[float], unit: str) -> str:
    return (
        f"{name}: n={len(values)} p50={percentile(values, 50):.2f}{unit} "
        f"p95={percentile(values, 95):.2f}{unit} max={max(values):.2f}{unit}"
    )


# --- 1. local (in-process, mock mode) --------------------------------------------------------

SYNTHETIC_CV_LINES = [
    "Backend Engineer",
    "Five years building Python services on AWS: Lambda, SQS, DynamoDB, S3.",
    "Built CI/CD pipelines with GitHub Actions and infrastructure with Terraform.",
    "Skills: Python, pytest, Docker, PostgreSQL, REST APIs, CloudWatch.",
] * 10  # ~40 lines, about one page of text
SYNTHETIC_JD = (
    "We are looking for a backend engineer with Python, AWS Lambda, DynamoDB, Terraform, "
    "Kubernetes, GraphQL and observability experience. CI/CD with GitHub Actions is a plus."
)


class MemoryStore:
    """Just enough of resume_analyzer.store.Store for the handler."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self.cache: dict[str, dict[str, Any]] = {}

    def get_analysis(self, user_sub: str, analysis_id: str) -> dict[str, Any] | None:
        item = self.items.get((user_sub, analysis_id))
        return dict(item) if item else None

    def mark_processing(self, user_sub: str, analysis_id: str) -> None:
        self.items[(user_sub, analysis_id)]["status"] = "PROCESSING"

    def mark_done(self, user_sub, analysis_id, result, model_id, source) -> None:
        self.items[(user_sub, analysis_id)].update(status="DONE", result=result, source=source)

    def mark_failed(self, user_sub: str, analysis_id: str, error_code: str) -> None:
        self.items[(user_sub, analysis_id)].update(status="FAILED", error=error_code)

    def get_cached(self, key: str) -> dict[str, Any] | None:
        return self.cache.get(key)

    def put_cached(self, key: str, result: dict, model_id: str, ttl_seconds: int = 0) -> None:
        self.cache[key] = {"result": result, "model_id": model_id}


class FakeTextract:
    """Answers the two async Textract calls with a finished one-page job."""

    def __init__(self, lines: list[str]) -> None:
        self.blocks = [
            {"BlockType": "LINE", "Text": text, "Page": 1, "Id": str(i)}
            for i, text in enumerate(lines)
        ]

    def start_document_text_detection(self, **kwargs: Any) -> dict[str, Any]:
        return {"JobId": "job-" + kwargs["ClientRequestToken"][:8]}

    def get_document_text_detection(self, **kwargs: Any) -> dict[str, Any]:
        return {"JobStatus": "SUCCEEDED", "DocumentMetadata": {"Pages": 1}, "Blocks": self.blocks}


def s3_message(user_sub: str, analysis_id: str) -> dict[str, Any]:
    body = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "s3": {
                    "bucket": {"name": "bench-bucket"},
                    "object": {
                        "key": f"uploads/{user_sub}/{analysis_id}.pdf",
                        "size": 48_000,
                        "eTag": "bench",
                    },
                },
            }
        ]
    }
    return {
        "Records": [
            {
                "messageId": analysis_id,
                "body": json.dumps(body),
                "attributes": {"ApproximateReceiveCount": "1"},
            }
        ]
    }


def run_local(runs: int) -> dict[str, list[float]]:
    """Time the process-analysis handler on cache misses and cache hits, in milliseconds."""
    import logging

    from resume_analyzer import log
    from resume_analyzer.handlers import process_analysis

    root = log.get_logger()
    level, mode = root.level, os.environ.get("BEDROCK_MODE")
    root.setLevel(logging.WARNING)  # keep the timing loop quiet
    os.environ["BEDROCK_MODE"] = "mock"
    try:
        return _time_handler(process_analysis, runs)
    finally:
        root.setLevel(level)
        if mode is None:
            os.environ.pop("BEDROCK_MODE", None)
        else:
            os.environ["BEDROCK_MODE"] = mode


def _time_handler(process_analysis: Any, runs: int) -> dict[str, list[float]]:

    db = MemoryStore()
    textract = FakeTextract(SYNTHETIC_CV_LINES)
    process_analysis.store = lambda: db
    process_analysis.textract_client = lambda: textract
    # Each analysis id stands for a different file, except the "hit" runs, which reuse run 0's.
    process_analysis.cv_sha256 = lambda upload: hashlib.sha256(
        upload.analysis_id.removeprefix("hit-").encode()
    ).hexdigest()
    context = SimpleNamespace(
        aws_request_id="bench",
        function_name="bench",
        get_remaining_time_in_millis=lambda: 120_000,
    )

    timings: dict[str, list[float]] = {"miss": [], "hit": []}
    for i in range(runs):
        for kind, analysis_id in (("miss", f"a{i:05d}"), ("hit", f"hit-a{i:05d}")):
            db.items[("bench-user", analysis_id)] = {
                "status": "PENDING",
                "job_description": SYNTHETIC_JD,
            }
            started = time.perf_counter()
            result = process_analysis.handler(s3_message("bench-user", analysis_id), context)
            timings[kind].append((time.perf_counter() - started) * 1000)
            item = db.items[("bench-user", analysis_id)]
            if result["batchItemFailures"] or item["status"] != "DONE":
                raise RuntimeError(f"run {i} ({kind}) did not finish DONE")
            expected = "cache" if kind == "hit" else "model"
            if item["source"] != expected:
                raise RuntimeError(f"run {i} ({kind}) came from {item['source']}")
    return timings


# --- 2. cost model ---------------------------------------------------------------------------

# AWS list prices, us-east-1, on-demand, read from the AWS Price List API
# (https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<service>/current/us-east-1/index.json)
# on 2026-11-05. Free tiers are ignored, so this is the cost after the free tier runs out.
PRICES = {
    "textract_page": 0.0015,  # DetectDocumentText, async, first 1M pages/month
    "nova_lite_input_1k": 0.00006,
    "nova_lite_output_1k": 0.00024,
    "nova_micro_input_1k": 0.000035,
    "nova_micro_output_1k": 0.00014,
    "lambda_arm_gb_s": 0.0000133334,
    "lambda_request": 0.0000002,
    "sqs_request": 0.0000004,
    "dynamodb_write": 0.000000625,  # per write request unit, on-demand
    "dynamodb_read": 0.000000125,  # per read request unit, on-demand
    "http_api_request": 0.000001,
    "s3_put": 0.000005,
    "s3_get": 0.0000004,
    "kms_request": 0.000003,
}

# Requests per analysis, counted from the code (backend/src/resume_analyzer):
# create-analysis: 1 API call + 1 Lambda + 1 DynamoDB put; S3 POST upload;
# process-analysis: SQS receive + delete, 1 Lambda, S3 GET (hash), DynamoDB get + 2 updates +
# cache get + cache put; Textract async start + 1 get; the browser then polls GET /analyses/{id}
# every 3 s (about 5 polls), each 1 API call + 1 Lambda + 1 DynamoDB get.
POLLS = 5
API_CALLS = 1 + POLLS
LAMBDA_CALLS = 1 + 1 + POLLS
# Small items (< 1 KB written, < 4 KB read) cost 1 unit each; the report item is about 2-3 KB.
DDB_WRITE_UNITS = 1 + 3 * 3 + 3  # create, PROCESSING, DONE (~3 KB = 3 WRU), cache put (~3 WRU)
DDB_READ_UNITS = 1 + 1 + POLLS  # analysis get, cache get, polls (strongly consistent: 1 RRU each)
# SSE-KMS with Bucket Keys and SQS data-key reuse make KMS calls rare; 3 is a generous bound.
KMS_REQUESTS = 3
CHARS_PER_TOKEN = 4  # rough rule of thumb for English text


def live_input_tokens(cv_chars: int, jd_chars: int) -> int:
    """Estimated Converse input tokens: system prompt + tool schema + JD + CV, at ~4 chars/token."""
    from resume_analyzer import bedrock

    request = bedrock.build_request("x" * cv_chars, "y" * jd_chars, model="m")
    fixed = len(json.dumps(request["system"])) + len(json.dumps(request["toolConfig"]))
    user = len(request["messages"][0]["content"][0]["text"])
    return math.ceil((fixed + user) / CHARS_PER_TOKEN)


def cost_per_cv(
    *,
    pages: int,
    mode: str,
    model: str = "nova_lite",
    input_tokens: int = 0,
    output_tokens: int = 0,
    lambda_ms: float,
    memory_mb: int = 256,
) -> dict[str, float]:
    """Dollar cost of one analysis, by service."""
    p = PRICES
    api_lambda_ms = 100.0  # create/read-analyses: a few ms of work, rounded up generously
    gb_s = memory_mb / 1024 * (lambda_ms + (LAMBDA_CALLS - 1) * api_lambda_ms) / 1000
    parts = {
        "textract": pages * p["textract_page"],
        "bedrock": 0.0,
        "lambda": gb_s * p["lambda_arm_gb_s"] + LAMBDA_CALLS * p["lambda_request"],
        "api_gateway": API_CALLS * p["http_api_request"],
        "dynamodb": DDB_WRITE_UNITS * p["dynamodb_write"] + DDB_READ_UNITS * p["dynamodb_read"],
        "sqs": 2 * p["sqs_request"],
        "s3": p["s3_put"] + p["s3_get"],
        "kms": KMS_REQUESTS * p["kms_request"],
    }
    if mode == "live":
        parts["bedrock"] = (
            input_tokens / 1000 * p[f"{model}_input_1k"]
            + output_tokens / 1000 * p[f"{model}_output_1k"]
        )
    return parts


def run_cost(lambda_ms_mock: float, lambda_ms_live: float, cv_chars: int, jd_chars: int) -> None:
    from resume_analyzer import bedrock

    input_tokens = live_input_tokens(cv_chars, jd_chars)
    typical_output = 800  # a 5-suggestion report is ~3 KB of JSON
    scenarios = [
        ("mock, 1-page CV", cost_per_cv(pages=1, mode="mock", lambda_ms=lambda_ms_mock)),
        ("mock, 2-page CV", cost_per_cv(pages=2, mode="mock", lambda_ms=lambda_ms_mock)),
        (
            "live Nova Lite, 2-page CV, typical output",
            cost_per_cv(
                pages=2,
                mode="live",
                input_tokens=input_tokens,
                output_tokens=typical_output,
                lambda_ms=lambda_ms_live,
            ),
        ),
        (
            "live Nova Lite, 2-page CV, worst case (retry, max output)",
            cost_per_cv(
                pages=2,
                mode="live",
                input_tokens=2 * input_tokens,
                output_tokens=2 * bedrock.MAX_TOKENS,
                lambda_ms=2 * lambda_ms_live,
            ),
        ),
        # A hit skips Textract and Bedrock; the Lambda run is short (hash + 2 DynamoDB calls).
        ("cache hit (any mode)", cost_per_cv(pages=0, mode="mock", lambda_ms=500)),
    ]
    print(f"assumed input tokens (live): {input_tokens} ({cv_chars} CV chars, {jd_chars} JD chars)")
    for name, parts in scenarios:
        total = sum(parts.values())
        biggest = max(parts, key=parts.get)
        print(
            f"{name}: per CV ${total:.6f}, per 100 CVs ${100 * total:.4f} "
            f"(largest part: {biggest} ${parts[biggest]:.6f})"
        )


# --- 3. end to end on the deployed stack -----------------------------------------------------


def run_e2e(pdf_path: str, runs: int, poll_seconds: float) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import boto3
    from api_smoke import call, post_upload

    api = os.environ["API_URL"].rstrip("/")
    pdf = Path(pdf_path).read_bytes()
    auth = boto3.client("cognito-idp").initiate_auth(
        ClientId=os.environ["CLIENT_ID"],
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={
            "USERNAME": os.environ["SMOKE_EMAIL"],
            "PASSWORD": os.environ["SMOKE_PASSWORD"],
        },
    )
    token = auth["AuthenticationResult"]["AccessToken"]
    nonce = hex(int(time.time()))[2:]
    base_jd = "Backend engineer: Python, AWS Lambda, SQS, DynamoDB, Terraform, CI/CD."

    def one(jd: str) -> tuple[str, float | None]:
        status, created = call(
            "POST", f"{api}/analyses", token, {"job_title": "Benchmark", "job_description": jd}
        )
        if status != 201:
            return f"create {status}", None
        upload_status = post_upload(created["upload"], pdf)
        uploaded = time.monotonic()
        if upload_status != 204:
            return f"upload {upload_status}", None
        detail: dict = {}
        while time.monotonic() - uploaded < 180:
            _, detail = call("GET", f"{api}/analyses/{created['analysis_id']}", token)
            if detail.get("status") in ("DONE", "FAILED"):
                break
            time.sleep(poll_seconds)
        elapsed = time.monotonic() - uploaded
        print(f"  {created['analysis_id']}: {detail.get('status')} after {elapsed:.1f}s")
        return detail.get("status", "?"), elapsed if detail.get("status") == "DONE" else None

    misses: list[float] = []
    failures = 0
    print(f"{runs} fresh analyses ({len(pdf)} bytes PDF), polling every {poll_seconds}s:")
    for i in range(runs):
        _, elapsed = one(f"{base_jd} (benchmark {nonce}-{i})")
        if elapsed is None:
            failures += 1
        else:
            misses.append(elapsed)
        time.sleep(1.2)  # POST /analyses is throttled to 1 req/s
    print("repeat of the first analysis (same PDF + same JD -> cache hit):")
    _, hit = one(f"{base_jd} (benchmark {nonce}-0)")

    print(f"success: {len(misses)}/{runs}")
    if misses:
        print(summary("upload -> DONE, cache miss", misses, "s"))
    if hit is not None:
        print(f"upload -> DONE, cache hit: {hit:.1f}s")
    print(f"note: times include up to {poll_seconds}s of polling granularity")
    return 0 if failures == 0 else 1


# --- CLI -------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    local = sub.add_parser("local", help="in-process handler latency, mock mode, no AWS")
    local.add_argument("--runs", type=int, default=500)
    cost = sub.add_parser("cost", help="cost model per CV / per 100 CVs")
    cost.add_argument("--lambda-ms-mock", type=float, default=8000, help="process-analysis ms")
    cost.add_argument("--lambda-ms-live", type=float, default=15000, help="process-analysis ms")
    cost.add_argument("--cv-chars", type=int, default=6000, help="extracted CV text (2 pages)")
    cost.add_argument("--jd-chars", type=int, default=3000)
    e2e = sub.add_parser("e2e", help="upload -> DONE latency on the deployed stack")
    e2e.add_argument("pdf")
    e2e.add_argument("--runs", type=int, default=10)
    e2e.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args(argv)

    if args.command == "local":
        timings = run_local(args.runs)
        print(summary("process-analysis in-process, cache miss (mock)", timings["miss"], "ms"))
        print(summary("process-analysis in-process, cache hit", timings["hit"], "ms"))
        return 0
    if args.command == "cost":
        run_cost(args.lambda_ms_mock, args.lambda_ms_live, args.cv_chars, args.jd_chars)
        return 0
    return run_e2e(args.pdf, args.runs, args.poll_seconds)


if __name__ == "__main__":
    sys.exit(main())
