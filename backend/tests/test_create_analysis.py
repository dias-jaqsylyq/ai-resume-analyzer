import base64
import json

import pytest
from api_events import SUB, api_event, lambda_context
from resume_analyzer import ids
from resume_analyzer.handlers import create_analysis


@pytest.fixture
def created(fake_api_store, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UPLOADS_BUCKET", "uploads-bucket")
    return fake_api_store


def call(body, **kwargs) -> tuple[int, dict]:
    result = create_analysis.handler(api_event("POST /analyses", body, **kwargs), lambda_context())
    return result["statusCode"], json.loads(result["body"])


def test_creates_pending_item_and_presigned_post(created) -> None:
    status, body = call({"job_description": "  Python developer  ", "job_title": "Dev"})

    assert status == 201
    analysis_id = body["analysis_id"]
    assert ids.is_ulid(analysis_id)
    assert body["status"] == "PENDING"
    item = created.items[(SUB, analysis_id)]
    assert item["status"] == "PENDING"
    assert item["job_description"] == "Python developer"
    assert item["job_title"] == "Dev"

    upload = body["upload"]
    assert upload["method"] == "POST"
    assert upload["url"] == "https://uploads-bucket.s3.us-east-1.amazonaws.com/"
    fields = upload["fields"]
    assert fields["key"] == f"uploads/{SUB}/{analysis_id}.pdf"
    assert fields["Content-Type"] == "application/pdf"
    assert fields["x-amz-algorithm"] == "AWS4-HMAC-SHA256"
    policy = json.loads(base64.b64decode(fields["policy"]))
    assert ["content-length-range", 1, 5 * 1024 * 1024] in policy["conditions"]
    assert {"Content-Type": "application/pdf"} in policy["conditions"]
    assert {"key": fields["key"]} in policy["conditions"]


def test_upload_key_matches_what_process_analysis_parses(created) -> None:
    from resume_analyzer.handlers import process_analysis

    _, body = call({"job_description": "JD"})
    key = body["upload"]["fields"]["key"]
    record = {"s3": {"bucket": {"name": "b"}, "object": {"key": key, "size": 10}}}

    upload = process_analysis.parse_upload(record)

    assert (upload.user_sub, upload.analysis_id) == (SUB, body["analysis_id"])


def test_job_title_is_optional(created) -> None:
    status, body = call({"job_description": "JD"})
    assert status == 201
    assert "job_title" not in created.items[(SUB, body["analysis_id"])]


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (None, "invalid_body"),
        ("not json", "invalid_body"),
        ([], "invalid_body"),
        ({}, "invalid_job_description"),
        ({"job_description": "   "}, "invalid_job_description"),
        ({"job_description": 5}, "invalid_job_description"),
        ({"job_description": "x" * 10_001}, "invalid_job_description"),
        ({"job_description": "JD", "job_title": 7}, "invalid_job_title"),
        ({"job_description": "JD", "job_title": "t" * 201}, "invalid_job_title"),
    ],
)
def test_rejects_bad_requests_without_writing(created, body, code) -> None:
    status, response = call(body)
    assert (status, response["error"]) == (400, code)
    assert created.items == {}


def test_base64_body_is_decoded(created) -> None:
    raw = base64.b64encode(json.dumps({"job_description": "JD"}).encode()).decode()
    status, _ = call(raw, isBase64Encoded=True)
    assert status == 201


@pytest.mark.parametrize("sub", [None, "a/b", "a#b"])
def test_requires_a_valid_user(created, sub) -> None:
    status, response = call({"job_description": "JD"}, sub=sub)
    assert (status, response["error"]) == (401, "unauthorized")
    assert created.items == {}


def test_store_failure_returns_500_without_details(created, monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(created, "create_analysis", boom)
    status, response = call({"job_description": "JD"})
    assert (status, response["error"]) == (500, "internal_error")
    assert "secret" not in json.dumps(response)
