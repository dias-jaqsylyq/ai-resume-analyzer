"""Live Bedrock check for RA-8: one real Converse call with a synthetic CV.

Run where AWS credentials for the project account are available (e.g. AWS CloudShell in
us-east-1), from the ``backend/`` directory:

    PYTHONPATH=src python3 scripts/bedrock_smoke.py
    PYTHONPATH=src BEDROCK_MODEL_ID=amazon.nova-micro-v1:0 python3 scripts/bedrock_smoke.py

It prints only status, sizes, token counts and latency (no report text), and exits 0 if the
model returned a report that passes schema validation. Costs well under one cent per run.
"""

from __future__ import annotations

import os
import sys
import time

import boto3
from botocore.exceptions import ClientError
from resume_analyzer import bedrock

SYNTHETIC_CV = """Alex Example
Backend Engineer
Experience: 5 years building Python services on AWS (Lambda, SQS, DynamoDB, S3).
Built CI/CD pipelines with GitHub Actions; wrote infrastructure in CloudFormation.
Skills: Python, pytest, AWS Lambda, DynamoDB, REST APIs, Docker, PostgreSQL."""

SYNTHETIC_JD = """Senior Backend Engineer (Python, AWS).
Must have: Python, AWS Lambda, DynamoDB, Terraform, CI/CD with GitHub Actions.
Nice to have: Amazon Bedrock, Kubernetes, observability with CloudWatch."""


def main() -> int:
    model = os.environ.get("BEDROCK_MODEL_ID", bedrock.DEFAULT_MODEL_ID)
    region = os.environ.get("AWS_REGION", "us-east-1")
    client = boto3.client("bedrock-runtime", region_name=region)
    print(f"model={model} region={region}")
    started = time.monotonic()
    try:
        analysis = bedrock.analyze_live(client, SYNTHETIC_CV, SYNTHETIC_JD, model=model)
    except ClientError as exc:
        error = exc.response.get("Error", {})
        print(f"FAIL api_error={error.get('Code')} message={error.get('Message')}")
        return 1
    except Exception as exc:  # InvalidReport / AnalysisBlocked: message holds no model output
        print(f"FAIL {type(exc).__name__}: {exc}")
        return 1
    report = analysis.report
    print(
        "OK schema_valid=true"
        f" attempts={analysis.attempts}"
        f" input_tokens={analysis.input_tokens}"
        f" output_tokens={analysis.output_tokens}"
        f" latency_ms={round((time.monotonic() - started) * 1000)}"
        f" ats_score={report['ats_score']}"
        f" matched={len(report['matched_skills'])}"
        f" missing={len(report['missing_skills'])}"
        f" suggestions={len(report['suggestions'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
