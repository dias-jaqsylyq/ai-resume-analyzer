"""Guard for the logging rule: handlers never log document text or model output.

Key-based redaction in ``resume_analyzer.log`` cannot catch text inside a free-text message
(``logger.info(f"got {text}")``), so these tests run the handler on a CV with recognisable
content and fail if any of it appears anywhere in the captured output, at DEBUG level,
on success and on failure.
"""

import json
from types import SimpleNamespace

import pytest
from resume_analyzer import log
from resume_analyzer.handlers import process_analysis
from resume_analyzer.textract import MAX_RESULTS

BUCKET, KEY = "uploads-bucket", "uploads/user-1/an-1.pdf"
# Synthetic CV. Each line is distinctive enough that finding it in logs means a leak.
CV_LINES = [
    "Zebulon Quixote-Marchetti",
    "zebulon.quixote@example.org | +1 555 0199 4242",
    "Senior Platform Engineer at Fictional Widgets LLC",
    "Kubernetes, Terraform, Rust, PostgreSQL",
]


def sqs_event() -> dict:
    s3 = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": BUCKET},
                    "object": {"key": KEY, "size": 2048, "eTag": "etag-1"},
                }
            }
        ]
    }
    return {"Records": [{"messageId": "m-1", "body": json.dumps(s3)}]}


def lambda_context() -> SimpleNamespace:
    return SimpleNamespace(
        aws_request_id="req-1", function_name="test", get_remaining_time_in_millis=lambda: 60_000
    )


def assert_not_logged(output: str, lines: list[str]) -> None:
    leaked = [line for line in lines if line in output]
    assert not leaked, f"document text found in logs: {leaked}"


@pytest.fixture
def textract(textract_stub, monkeypatch: pytest.MonkeyPatch):
    client, stubber = textract_stub
    monkeypatch.setattr(process_analysis, "textract_client", lambda: client)
    stubber.add_response(
        "start_document_text_detection",
        {"JobId": "job-1"},
        {
            "DocumentLocation": {"S3Object": {"Bucket": BUCKET, "Name": KEY}},
            "ClientRequestToken": process_analysis.textract.request_token(BUCKET, KEY, "etag-1"),
        },
    )
    stubber.add_response(
        "get_document_text_detection",
        {
            "JobStatus": "SUCCEEDED",
            "DocumentMetadata": {"Pages": 1},
            "Blocks": [
                {"BlockType": "LINE", "Text": t, "Page": 1, "Id": str(i)}
                for i, t in enumerate(CV_LINES)
            ],
        },
        {"JobId": "job-1", "MaxResults": MAX_RESULTS},
    )
    return stubber


def test_handler_does_not_log_extracted_text(textract, all_log_output) -> None:
    result = process_analysis.handler(sqs_event(), lambda_context())

    output = all_log_output()
    assert result == {"batchItemFailures": []}
    assert '"chars"' in output  # the handler did log, just not the content
    assert_not_logged(output, CV_LINES)


def test_handler_does_not_log_extracted_text_on_failure(
    textract, all_log_output, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure after extraction (e.g. in the next stage) must not dump the text either."""
    original = process_analysis.process_upload

    def fail_after_extraction(upload, context):
        original(upload, context)
        raise RuntimeError("next stage failed")

    monkeypatch.setattr(process_analysis, "process_upload", fail_after_extraction)

    result = process_analysis.handler(sqs_event(), lambda_context())

    assert result == {"batchItemFailures": [{"itemIdentifier": "m-1"}]}
    assert_not_logged(all_log_output(), CV_LINES)


def test_guard_catches_a_leak(all_log_output) -> None:
    """The check itself works: text in a free-text message or a print() is detected."""
    log.get_logger("leaky").debug("extracted: %s", CV_LINES[0])
    print(CV_LINES[1])

    with pytest.raises(AssertionError, match="document text found in logs"):
        assert_not_logged(all_log_output(), CV_LINES[:1])
    with pytest.raises(AssertionError, match="document text found in logs"):
        assert_not_logged(all_log_output(), CV_LINES[1:2])
