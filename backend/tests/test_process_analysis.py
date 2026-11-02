import json
from types import SimpleNamespace

import pytest
from resume_analyzer.handlers import process_analysis
from resume_analyzer.textract import MAX_RESULTS

BUCKET = "uploads-bucket"


def s3_event(key: str = "uploads/user-1/an-1.pdf", size: int = 2048) -> str:
    return json.dumps(
        {
            "Records": [
                {
                    "eventSource": "aws:s3",
                    "eventName": "ObjectCreated:Put",
                    "s3": {
                        "bucket": {"name": BUCKET},
                        "object": {"key": key, "size": size, "eTag": "etag-1"},
                    },
                }
            ]
        }
    )


def sqs_event(*bodies: str, receive_count: int = 1) -> dict:
    return {
        "Records": [
            {
                "messageId": f"m-{i}",
                "body": body,
                "attributes": {"ApproximateReceiveCount": str(receive_count)},
            }
            for i, body in enumerate(bodies)
        ]
    }


def lambda_context() -> SimpleNamespace:
    return SimpleNamespace(
        aws_request_id="req-1",
        function_name="ai-resume-analyzer-process-analysis",
        get_remaining_time_in_millis=lambda: 60_000,
    )


JD = "Python developer with AWS Lambda and Terraform"


@pytest.fixture
def textract(textract_stub, monkeypatch: pytest.MonkeyPatch):
    client, stubber = textract_stub
    monkeypatch.setattr(process_analysis, "textract_client", lambda: client)
    return stubber


@pytest.fixture
def db(fake_store):
    for analysis_id in ("an-1", "an-2"):
        fake_store.add_analysis("user-1", analysis_id, JD)
    return fake_store


def expect_job(stubber, key: str, text_lines: list[str]) -> None:
    stubber.add_response(
        "start_document_text_detection",
        {"JobId": "job-1"},
        {
            "DocumentLocation": {"S3Object": {"Bucket": BUCKET, "Name": key}},
            "ClientRequestToken": process_analysis.textract.request_token(BUCKET, key, "etag-1"),
        },
    )
    stubber.add_response(
        "get_document_text_detection",
        {
            "JobStatus": "SUCCEEDED",
            "DocumentMetadata": {"Pages": 1},
            "Blocks": [
                {"BlockType": "LINE", "Text": t, "Page": 1, "Id": str(i)}
                for i, t in enumerate(text_lines)
            ],
        },
        {"JobId": "job-1", "MaxResults": MAX_RESULTS},
    )


def test_upload_is_analysed_and_stored(textract, db) -> None:
    expect_job(textract, "uploads/user-1/an-1.pdf", ["Jane Doe", "Python, AWS Lambda"])

    [outcome] = process_analysis.process_message(s3_event(), lambda_context())

    assert outcome == process_analysis.Outcome("an-1", "DONE", "model")
    item = db.items[("user-1", "an-1")]
    assert db.history == [("an-1", "PROCESSING"), ("an-1", "DONE")]
    assert item["model_id"] == "mock"
    assert item["result_source"] == "model"
    assert {"python", "aws", "lambda"} <= set(item["result"]["matched_skills"])
    assert "terraform" in item["result"]["missing_skills"]
    assert len(db.cache) == 1


def test_handler_reports_no_failures_on_success(textract, db) -> None:
    expect_job(textract, "uploads/user-1/an-1.pdf", ["Jane Doe"])

    assert process_analysis.handler(sqs_event(s3_event()), lambda_context()) == {
        "batchItemFailures": []
    }


def test_cache_hit_skips_textract_and_model(textract, db, monkeypatch: pytest.MonkeyPatch) -> None:
    expect_job(textract, "uploads/user-1/an-1.pdf", ["Jane Doe", "Python"])
    process_analysis.process_message(s3_event(), lambda_context())
    # Same file bytes (same fake hash) and same JD under another analysis id.
    db.add_analysis("user-1", "an-3", JD)
    monkeypatch.setattr(process_analysis, "cv_sha256", lambda upload: "same-file")
    db.cache = {
        process_analysis.cache_key("same-file", JD, "mock", "1"): next(iter(db.cache.values()))
    }
    # No Textract responses queued: a Textract call would fail the test.

    [outcome] = process_analysis.process_message(
        s3_event("uploads/user-1/an-3.pdf"), lambda_context()
    )

    assert outcome.source == "cache"
    assert db.items[("user-1", "an-3")]["result"] == db.items[("user-1", "an-1")]["result"]


def test_different_job_description_misses_cache(textract, db) -> None:
    from resume_analyzer.store import cache_key

    assert cache_key("h", "JD one", "m", "1") != cache_key("h", "JD two", "m", "1")
    assert cache_key("h", "JD", "mock", "1") != cache_key("h", "JD", "amazon.nova-lite-v1:0", "1")


def test_already_done_analysis_is_skipped(textract, db) -> None:
    db.items[("user-1", "an-1")]["status"] = "DONE"

    [outcome] = process_analysis.process_message(s3_event(), lambda_context())

    assert outcome.source == "skipped"
    assert db.history == []


def test_url_encoded_key_is_decoded(textract, db) -> None:
    db.add_analysis("user 1", "an-1", JD)
    expect_job(textract, "uploads/user 1/an-1.pdf", ["Jane Doe"])

    process_analysis.process_message(s3_event("uploads/user+1/an-1.pdf"), lambda_context())

    assert db.items[("user 1", "an-1")]["status"] == "DONE"


def test_s3_test_event_is_skipped(textract, db) -> None:
    body = json.dumps({"Service": "Amazon S3", "Event": "s3:TestEvent", "Bucket": BUCKET})

    assert process_analysis.handler(sqs_event(body), lambda_context()) == {"batchItemFailures": []}


@pytest.mark.parametrize(
    "key",
    ["other/user-1/an-1.pdf", "uploads/an-1.pdf", "uploads/user-1/an-1.docx", "uploads/u/x/a.pdf"],
)
def test_unexpected_key_is_dropped_without_calling_textract(textract, db, key: str) -> None:
    with pytest.raises(process_analysis.InvalidUpload):
        process_analysis.parse_upload(json.loads(s3_event(key))["Records"][0])

    assert process_analysis.handler(sqs_event(s3_event(key)), lambda_context()) == {
        "batchItemFailures": []
    }
    assert db.history == []


def test_oversized_upload_is_failed_without_calling_textract(textract, db) -> None:
    size = process_analysis.MAX_UPLOAD_BYTES + 1

    result = process_analysis.handler(sqs_event(s3_event(size=size)), lambda_context())

    assert result == {"batchItemFailures": []}  # permanent: not retried
    assert db.items[("user-1", "an-1")]["status"] == "FAILED"
    assert db.items[("user-1", "an-1")]["error"] == "InvalidUpload"


def test_missing_analysis_item_is_not_retried(textract, fake_store) -> None:
    result = process_analysis.handler(sqs_event(s3_event()), lambda_context())

    assert result == {"batchItemFailures": []}
    assert fake_store.history == []


def test_transient_error_is_retried_then_failed_on_last_receive(
    textract, db, monkeypatch: pytest.MonkeyPatch
) -> None:
    def throttled(cv_text, jd):
        raise RuntimeError("throttled")

    monkeypatch.setattr(process_analysis.bedrock, "analyzer", lambda factory: throttled)
    for count in (1, 2, 3):
        expect_job(textract, "uploads/user-1/an-1.pdf", ["Jane Doe"])
        result = process_analysis.handler(
            sqs_event(s3_event(), receive_count=count), lambda_context()
        )
        assert result == {"batchItemFailures": [{"itemIdentifier": "m-0"}]}
        expected = "FAILED" if count == process_analysis.MAX_RECEIVE_COUNT else "PROCESSING"
        assert db.items[("user-1", "an-1")]["status"] == expected

    assert db.items[("user-1", "an-1")]["error"] == "RuntimeError"


def test_invalid_model_output_is_permanent(textract, db, monkeypatch: pytest.MonkeyPatch) -> None:
    def invalid(cv_text, jd):
        raise process_analysis.InvalidReport("ats_score: expected an integer")

    monkeypatch.setattr(process_analysis.bedrock, "analyzer", lambda factory: invalid)
    expect_job(textract, "uploads/user-1/an-1.pdf", ["Jane Doe"])

    result = process_analysis.handler(sqs_event(s3_event()), lambda_context())

    assert result == {"batchItemFailures": []}
    assert db.items[("user-1", "an-1")]["error"] == "InvalidReport"


def test_only_failed_messages_are_reported(textract, db) -> None:
    expect_job(textract, "uploads/user-1/an-2.pdf", ["Jane Doe"])
    event = sqs_event(s3_event("bad/key.pdf"), s3_event("uploads/user-1/an-2.pdf"), "not json")

    result = process_analysis.handler(event, lambda_context())

    assert result == {"batchItemFailures": [{"itemIdentifier": "m-2"}]}


def test_cv_sha256_streams_the_s3_object(monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib
    import io

    from botocore.response import StreamingBody
    from conftest import stubbed_client

    client, stubber = stubbed_client("s3")
    data = b"%PDF-1.7 fake" * 1000
    stubber.add_response(
        "get_object",
        {"Body": StreamingBody(io.BytesIO(data), len(data))},
        {"Bucket": BUCKET, "Key": "uploads/user-1/an-1.pdf"},
    )
    monkeypatch.setattr(process_analysis, "s3_client", lambda: client)
    upload = process_analysis.parse_upload(json.loads(s3_event())["Records"][0])

    with stubber:
        assert process_analysis.cv_sha256(upload) == hashlib.sha256(data).hexdigest()
