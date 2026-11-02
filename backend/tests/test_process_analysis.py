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


def sqs_event(*bodies: str) -> dict:
    return {
        "Records": [
            {"messageId": f"m-{i}", "body": body, "attributes": {"ApproximateReceiveCount": "1"}}
            for i, body in enumerate(bodies)
        ]
    }


def lambda_context() -> SimpleNamespace:
    return SimpleNamespace(
        aws_request_id="req-1",
        function_name="ai-resume-analyzer-process-analysis",
        get_remaining_time_in_millis=lambda: 60_000,
    )


@pytest.fixture
def textract(textract_stub, monkeypatch: pytest.MonkeyPatch):
    client, stubber = textract_stub
    monkeypatch.setattr(process_analysis, "textract_client", lambda: client)
    return stubber


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


def test_message_is_extracted(textract) -> None:
    expect_job(textract, "uploads/user-1/an-1.pdf", ["Jane Doe", "Python"])

    [result] = process_analysis.process_message(s3_event(), lambda_context())

    assert result.text == "Jane Doe\nPython"


def test_handler_reports_no_failures_on_success(textract) -> None:
    expect_job(textract, "uploads/user-1/an-1.pdf", ["Jane Doe"])

    assert process_analysis.handler(sqs_event(s3_event()), lambda_context()) == {
        "batchItemFailures": []
    }


def test_url_encoded_key_is_decoded(textract) -> None:
    expect_job(textract, "uploads/user 1/an-1.pdf", ["Jane Doe"])

    process_analysis.process_message(s3_event("uploads/user+1/an-1.pdf"), lambda_context())


def test_s3_test_event_is_skipped(textract) -> None:
    body = json.dumps({"Service": "Amazon S3", "Event": "s3:TestEvent", "Bucket": BUCKET})

    assert process_analysis.handler(sqs_event(body), lambda_context()) == {"batchItemFailures": []}


@pytest.mark.parametrize(
    "key",
    ["other/user-1/an-1.pdf", "uploads/an-1.pdf", "uploads/user-1/an-1.docx", "uploads/u/x/a.pdf"],
)
def test_unexpected_key_fails_without_calling_textract(textract, key: str) -> None:
    with pytest.raises(process_analysis.InvalidUpload):
        process_analysis.process_message(s3_event(key), lambda_context())


def test_oversized_upload_fails_without_calling_textract(textract) -> None:
    size = process_analysis.MAX_UPLOAD_BYTES + 1
    with pytest.raises(process_analysis.InvalidUpload):
        process_analysis.process_message(s3_event(size=size), lambda_context())


def test_only_failed_messages_are_reported(textract) -> None:
    expect_job(textract, "uploads/user-1/an-2.pdf", ["Jane Doe"])
    event = sqs_event(s3_event("bad/key.pdf"), s3_event("uploads/user-1/an-2.pdf"), "not json")

    result = process_analysis.handler(event, lambda_context())

    assert result == {"batchItemFailures": [{"itemIdentifier": "m-0"}, {"itemIdentifier": "m-2"}]}
