"""End-to-end check of the deployed API (run by the owner in AWS CloudShell).

Signs in with Cognito, creates an analysis, uploads a PDF with the pre-signed POST, polls
until the analysis is DONE or FAILED, then reads the history. Prints only ids, status codes,
statuses, the ATS score and timings, never CV text or report text.

    export API_URL=... CLIENT_ID=... SMOKE_EMAIL=... SMOKE_PASSWORD=...
    python3 scripts/api_smoke.py path/to/cv.pdf

API_URL and CLIENT_ID are the `api_url` and `cognito_client_id` Terraform outputs. The user
must exist and be confirmed (sign up in the app, or `aws cognito-idp admin-create-user` and
`admin-set-user-password --permanent`).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

import boto3


def https_request(url: str, data: bytes | None, method: str) -> urllib.request.Request:
    if not url.startswith("https://"):
        raise ValueError("only https URLs are allowed")
    return urllib.request.Request(url, data=data, method=method)  # noqa: S310 - checked above


def call(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    request = https_request(url, data, method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - https only
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def post_upload(upload: dict, pdf: bytes) -> int:
    """multipart/form-data POST to S3: policy fields first, the file last."""
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in upload["fields"].items():
        header = f'Content-Disposition: form-data; name="{name}"'
        parts.append(f"--{boundary}\r\n{header}\r\n\r\n{value}\r\n".encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="cv.pdf"\r\n'
        f"Content-Type: {upload['content_type']}\r\n\r\n".encode()
        + pdf
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = https_request(upload["url"], b"".join(parts), "POST")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - https only
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def main() -> int:
    api = os.environ["API_URL"].rstrip("/")
    pdf = open(sys.argv[1], "rb").read()  # noqa: SIM115
    auth = boto3.client("cognito-idp").initiate_auth(
        ClientId=os.environ["CLIENT_ID"],
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={
            "USERNAME": os.environ["SMOKE_EMAIL"],
            "PASSWORD": os.environ["SMOKE_PASSWORD"],
        },
    )
    token = auth["AuthenticationResult"]["AccessToken"]
    print("signed in: OK")

    status, created = call(
        "POST",
        f"{api}/analyses",
        token,
        {"job_title": "Smoke test", "job_description": "Python, AWS, Terraform, CI/CD"},
    )
    print(f"POST /analyses -> {status}")
    if status != 201:
        print(f"error: {created.get('error')}")
        return 1
    analysis_id = created["analysis_id"]
    print(f"analysis_id: {analysis_id}")
    print(f"upload to S3 -> {post_upload(created['upload'], pdf)} (expect 204), {len(pdf)} bytes")

    started = time.monotonic()
    detail: dict = {}
    while time.monotonic() - started < 180:
        status, detail = call("GET", f"{api}/analyses/{analysis_id}", token)
        if detail.get("status") in ("DONE", "FAILED"):
            break
        time.sleep(3)
    elapsed = time.monotonic() - started
    print(f"GET /analyses/{{id}} -> {status}, status {detail.get('status')} after {elapsed:.0f}s")
    if detail.get("status") == "DONE":
        report = detail.get("report") or {}
        suggestions = len(report.get("suggestions", []))
        print(f"ats_score: {report.get('ats_score')}, suggestions: {suggestions}")
    else:
        print(f"error: {detail.get('error')}")

    status, history = call("GET", f"{api}/analyses?limit=5", token)
    print(f"GET /analyses -> {status}, {len(history.get('items', []))} items")
    return 0 if detail.get("status") == "DONE" else 1


if __name__ == "__main__":
    sys.exit(main())
