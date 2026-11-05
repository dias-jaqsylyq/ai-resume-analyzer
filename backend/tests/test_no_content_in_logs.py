"""Guard for the logging rule: handlers never log document text or model output.

Key-based redaction in ``resume_analyzer.log`` cannot catch text inside a free-text message
(``logger.info(f"got {text}")``), so these tests run the handler on a CV and a model answer
with recognisable content and fail if any of it appears anywhere in the captured output,
at DEBUG level, on success and on failure.
"""

import json
from types import SimpleNamespace

import pytest
from resume_analyzer import bedrock, log
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
JOB_DESCRIPTION = "Wanted: Glorptastic Hyperlane Wrangler with Rust"
# Synthetic model answer. Every string is distinctive, so finding it in logs means a leak.
MODEL_REPORT = {
    "ats_score": 73,
    "score_rationale": "Quixotic rationale: strong Rust, thin on hyperlane wrangling",
    "matched_skills": ["Rust-Zebulon-Skill"],
    "missing_skills": ["Glorptastic Hyperlane Wrangling"],
    "suggestions": [
        {"priority": "high", "section": "Marchetti Section", "advice": "Add the wrangler badge"}
    ],
    "summary": "Overall Zebulon summary paragraph for the leak test",
}
MODEL_LINES = [
    MODEL_REPORT["score_rationale"],
    *MODEL_REPORT["matched_skills"],
    *MODEL_REPORT["missing_skills"],
    "Marchetti Section",
    "Add the wrangler badge",
    MODEL_REPORT["summary"],
]
CONTENT = CV_LINES + MODEL_LINES + [JOB_DESCRIPTION]


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


def converse_response(report_input: object) -> dict:
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "t-1",
                            "name": bedrock.TOOL_NAME,
                            "input": report_input,
                        }
                    }
                ],
            }
        },
        "stopReason": "tool_use",
        "usage": {"inputTokens": 900, "outputTokens": 200, "totalTokens": 1100},
        "metrics": {"latencyMs": 1200},
    }


@pytest.fixture
def db(fake_store):
    fake_store.add_analysis("user-1", "an-1", JOB_DESCRIPTION)
    return fake_store


@pytest.fixture
def live_bedrock(bedrock_stub, monkeypatch: pytest.MonkeyPatch):
    """BEDROCK_MODE=live with Converse answered by Stubber (request checked against the API)."""
    client, stubber = bedrock_stub
    monkeypatch.setenv("BEDROCK_MODE", "live")
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    monkeypatch.setattr(process_analysis, "bedrock_client", lambda: client)
    return stubber


def expect_converse(stubber, report_input: object) -> None:
    request = bedrock.build_request(
        "\n".join(CV_LINES), JOB_DESCRIPTION, model=bedrock.DEFAULT_MODEL_ID
    )
    stubber.add_response("converse", converse_response(report_input), request)


@pytest.fixture
def textract(textract_stub, db, monkeypatch: pytest.MonkeyPatch):
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
    """Mock mode (the default): the CV never reaches the logs."""
    result = process_analysis.handler(sqs_event(), lambda_context())

    output = all_log_output()
    assert result == {"batchItemFailures": []}
    assert '"chars"' in output  # the handler did log, just not the content
    assert_not_logged(output, CONTENT)


def test_handler_does_not_log_model_output(textract, live_bedrock, db, all_log_output) -> None:
    expect_converse(live_bedrock, MODEL_REPORT)

    result = process_analysis.handler(sqs_event(), lambda_context())

    output = all_log_output()
    assert result == {"batchItemFailures": []}
    assert db.items[("user-1", "an-1")]["result"]["summary"] == MODEL_REPORT["summary"]
    assert '"output_tokens": 200' in output  # the handler did log, just not the content
    assert_not_logged(output, CONTENT)


def test_invalid_model_output_is_not_logged(textract, live_bedrock, db, all_log_output) -> None:
    """Invalid answers are logged by field and rule only, never by value."""
    bad = {**MODEL_REPORT, "ats_score": "Zebulon-ninety", "suggestions": "Marchetti Section"}
    expect_converse(live_bedrock, bad)
    expect_converse(live_bedrock, bad)

    result = process_analysis.handler(sqs_event(), lambda_context())

    output = all_log_output()
    assert result == {"batchItemFailures": []}  # permanent failure, recorded on the item
    assert db.items[("user-1", "an-1")]["error"] == "InvalidReport"
    assert "invalid model output" in output
    assert_not_logged(output, [*CONTENT, "Zebulon-ninety"])


def test_handler_does_not_log_content_on_failure(
    textract, live_bedrock, db, all_log_output, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure after extraction and analysis (here: the DynamoDB write) dumps nothing."""
    expect_converse(live_bedrock, MODEL_REPORT)

    def write_failed(*args, **kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr(db, "mark_done", write_failed)

    result = process_analysis.handler(sqs_event(), lambda_context())

    assert result == {"batchItemFailures": [{"itemIdentifier": "m-1"}]}
    assert_not_logged(all_log_output(), CONTENT)


def guarded_bedrock(live_bedrock, monkeypatch: pytest.MonkeyPatch, action: str, texts: list[str]):
    """Live mode with a guardrail: Converse with guardrailConfig, then ApplyGuardrail."""
    monkeypatch.setenv("BEDROCK_GUARDRAIL_ID", "gr-1")
    monkeypatch.setenv("BEDROCK_GUARDRAIL_VERSION", "1")
    request = bedrock.build_request(
        "\n".join(CV_LINES),
        JOB_DESCRIPTION,
        model=bedrock.DEFAULT_MODEL_ID,
        guardrail_id="gr-1",
        guardrail_version="1",
    )
    live_bedrock.add_response("converse", converse_response(MODEL_REPORT), request)
    fields = [value for _, value in bedrock._text_fields(MODEL_REPORT)]
    live_bedrock.add_response(
        "apply_guardrail",
        {
            "usage": {
                "topicPolicyUnits": 0,
                "contentPolicyUnits": 1,
                "wordPolicyUnits": 0,
                "sensitiveInformationPolicyUnits": 1,
                "sensitiveInformationPolicyFreeUnits": 0,
                "contextualGroundingPolicyUnits": 0,
            },
            "action": action,
            "outputs": [{"text": t} for t in texts],
            "assessments": [],
        },
        {
            "guardrailIdentifier": "gr-1",
            "guardrailVersion": "1",
            "source": "OUTPUT",
            "content": [{"text": {"text": bedrock._FIELD_SEPARATOR.join(fields)}}],
        },
    )
    return fields


def test_masked_report_is_not_logged(
    textract, live_bedrock, db, all_log_output, monkeypatch: pytest.MonkeyPatch
) -> None:
    fields = [value for _, value in bedrock._text_fields(MODEL_REPORT)]
    masked = [f.replace("Zebulon", "{NAME}") for f in fields]
    guarded_bedrock(
        live_bedrock, monkeypatch, "GUARDRAIL_INTERVENED", [bedrock._FIELD_SEPARATOR.join(masked)]
    )

    result = process_analysis.handler(sqs_event(), lambda_context())

    output = all_log_output()
    assert result == {"batchItemFailures": []}
    assert db.items[("user-1", "an-1")]["result"]["summary"].startswith("Overall {NAME}")
    assert '"guardrail": "masked"' in output
    assert_not_logged(output, [*CONTENT, *masked])


def test_blocked_report_is_not_logged(
    textract, live_bedrock, db, all_log_output, monkeypatch: pytest.MonkeyPatch
) -> None:
    guarded_bedrock(live_bedrock, monkeypatch, "GUARDRAIL_INTERVENED", ["Blocked Zebulon notice"])

    result = process_analysis.handler(sqs_event(), lambda_context())

    output = all_log_output()
    assert result == {"batchItemFailures": []}  # permanent failure, recorded on the item
    assert db.items[("user-1", "an-1")]["error"] == "AnalysisBlocked"
    assert_not_logged(output, [*CONTENT, "Blocked Zebulon notice"])


def test_guard_catches_a_leak(all_log_output) -> None:
    """The check itself works: text in a free-text message or a print() is detected."""
    log.get_logger("leaky").debug("extracted: %s", CV_LINES[0])
    print(CV_LINES[1])

    with pytest.raises(AssertionError, match="document text found in logs"):
        assert_not_logged(all_log_output(), CV_LINES[:1])
    with pytest.raises(AssertionError, match="document text found in logs"):
        assert_not_logged(all_log_output(), CV_LINES[1:2])
