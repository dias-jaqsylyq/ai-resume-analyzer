"""RA-12: the DLQ check script and the handler behaviour it relies on.

The script's SQS calls go through botocore's Stubber, so a parameter the real SQS API does not
accept fails the test. The handler tests pin the two contracts the DLQ path and the alarms use:
a poison message is reported back to SQS on every receive (never acknowledged), and a failed
analysis writes the JSON log line the `failed_analyses` metric filter in infra/alarms.tf matches.
"""

import importlib.util
import io
import json
from pathlib import Path

import pytest
from botocore.stub import ANY
from resume_analyzer import log
from resume_analyzer.handlers import process_analysis
from test_process_analysis import lambda_context, s3_event, sqs_event

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dlq_check.py"
spec = importlib.util.spec_from_file_location("dlq_check", SCRIPT)
dlq_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dlq_check)

QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/123456789012/ai-resume-analyzer-analysis"
DLQ_URL = QUEUE_URL + "-dlq"
RECEIVE = {
    "QueueUrl": DLQ_URL,
    "MaxNumberOfMessages": 10,
    "WaitTimeSeconds": 2,
    "VisibilityTimeout": 30,
    "AttributeNames": ["ApproximateReceiveCount", "SentTimestamp"],
}


@pytest.fixture
def sqs():
    from conftest import stubbed_client

    client, stubber = stubbed_client("sqs")
    with stubber:
        yield client, stubber
        stubber.assert_no_pending_responses()


def test_send_puts_a_non_json_marker_on_the_queue(sqs) -> None:
    client, stubber = sqs
    stubber.add_response(
        "send_message",
        {"MessageId": "m-1"},
        {"QueueUrl": QUEUE_URL, "MessageBody": ANY},
    )

    assert dlq_check.send(client, QUEUE_URL) == "m-1"


def test_marker_is_a_poison_message_for_the_handler() -> None:
    body = f"{dlq_check.MARKER_PREFIX}00000000-0000-0000-0000-000000000000"
    for count in (1, 2, 3):  # every receive is reported back, so SQS redrives it to the DLQ
        result = process_analysis.handler(sqs_event(body, receive_count=count), lambda_context())
        assert result == {"batchItemFailures": [{"itemIdentifier": "m-0"}]}


def test_check_deletes_markers_and_releases_other_messages(sqs) -> None:
    client, stubber = sqs
    stubber.add_response(
        "receive_message",
        {
            "Messages": [
                {
                    "MessageId": "m-marker",
                    "ReceiptHandle": "rh-1",
                    "Body": dlq_check.MARKER_PREFIX + "abc",
                    "Attributes": {"ApproximateReceiveCount": "4", "SentTimestamp": "0"},
                },
                {"MessageId": "m-real", "ReceiptHandle": "rh-2", "Body": s3_event()},
            ]
        },
        RECEIVE,
    )
    stubber.add_response("delete_message", {}, {"QueueUrl": DLQ_URL, "ReceiptHandle": "rh-1"})
    stubber.add_response(
        "change_message_visibility",
        {},
        {"QueueUrl": DLQ_URL, "ReceiptHandle": "rh-2", "VisibilityTimeout": 0},
    )
    stubber.add_response("receive_message", {"Messages": []}, RECEIVE)

    result = dlq_check.check(client, DLQ_URL)

    assert [f["message_id"] for f in result["found"]] == ["m-marker"]
    assert result["found"][0]["receive_count"] == 4
    assert result["other"] == 1


def test_check_reports_nothing_found_on_an_empty_dlq(sqs) -> None:
    client, stubber = sqs
    stubber.add_response("receive_message", {}, RECEIVE)

    assert dlq_check.check(client, DLQ_URL) == {"found": [], "other": 0}


def test_check_never_prints_message_bodies(sqs, monkeypatch, capsys) -> None:
    client, stubber = sqs
    secret_body = json.dumps({"Records": [{"s3": {"object": {"key": "uploads/u/Zebulon.pdf"}}}]})
    stubber.add_response("get_queue_url", {"QueueUrl": DLQ_URL}, {"QueueName": dlq_check.DLQ_NAME})
    stubber.add_response(
        "receive_message",
        {"Messages": [{"MessageId": "m-real", "ReceiptHandle": "rh", "Body": secret_body}]},
        RECEIVE,
    )
    stubber.add_response(
        "change_message_visibility",
        {},
        {"QueueUrl": DLQ_URL, "ReceiptHandle": "rh", "VisibilityTimeout": 0},
    )
    stubber.add_response("receive_message", {}, RECEIVE)
    monkeypatch.setattr(dlq_check.boto3, "client", lambda service: client)

    assert dlq_check.main(["dlq_check.py", "check"]) == 1

    out = capsys.readouterr().out
    assert "Zebulon" not in out
    assert "other messages in DLQ (left untouched): 1" in out


def test_failed_analysis_log_line_matches_the_alarm_metric_filter(
    fake_store, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_store.add_analysis("user-1", "an-1", "JD")
    buffer = io.StringIO()
    for handler in log.get_logger().handlers:
        if getattr(handler, "_resume_analyzer", False):
            monkeypatch.setattr(handler, "stream", buffer)
    oversized = process_analysis.MAX_UPLOAD_BYTES + 1

    process_analysis.handler(sqs_event(s3_event(size=oversized)), lambda_context())

    lines = [json.loads(line) for line in buffer.getvalue().splitlines()]
    # infra/alarms.tf: { ($.message = "analysis failed") && ($.last_attempt IS TRUE) }
    assert any(
        entry["message"] == "analysis failed" and entry["last_attempt"] is True for entry in lines
    )
