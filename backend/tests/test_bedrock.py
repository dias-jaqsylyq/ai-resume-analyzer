import pytest
from resume_analyzer import bedrock
from resume_analyzer.report import InvalidReport

CV = "Jane Doe\nPython developer, AWS Lambda, DynamoDB"
JD = "Backend engineer: Python, AWS Lambda, Terraform"
REPORT = {
    "ats_score": 70,
    "score_rationale": "Good Python and AWS, no Terraform.",
    "matched_skills": ["Python", "AWS Lambda"],
    "missing_skills": ["Terraform"],
    "suggestions": [{"priority": "high", "section": "Skills", "advice": "Add Terraform."}],
    "summary": "Good fit.",
}


def response(content: list, stop_reason: str = "tool_use") -> dict:
    return {
        "output": {"message": {"role": "assistant", "content": content}},
        "stopReason": stop_reason,
        "usage": {"inputTokens": 1000, "outputTokens": 150, "totalTokens": 1150},
        "metrics": {"latencyMs": 900},
    }


def tool(report: object) -> dict:
    return {"toolUse": {"toolUseId": "t-1", "name": bedrock.TOOL_NAME, "input": report}}


def request(**kwargs) -> dict:
    return bedrock.build_request(CV, JD, model=bedrock.DEFAULT_MODEL_ID, **kwargs)


@pytest.fixture(autouse=True)
def _no_guardrail_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("BEDROCK_MODE", "BEDROCK_MODEL_ID", "BEDROCK_GUARDRAIL_ID"):
        monkeypatch.delenv(name, raising=False)


def test_live_call_returns_validated_report(bedrock_stub) -> None:
    client, stubber = bedrock_stub
    stubber.add_response("converse", response([tool(REPORT)]), request())

    analysis = bedrock.analyze_live(client, CV, JD)

    assert analysis.report == REPORT
    assert (analysis.attempts, analysis.input_tokens, analysis.output_tokens) == (1, 1000, 150)
    assert analysis.model_id == "amazon.nova-lite-v1:0"


def test_request_forces_the_report_tool_and_wraps_inputs() -> None:
    req = request()

    assert req["toolConfig"]["toolChoice"] == {"tool": {"name": "submit_report"}}
    assert req["inferenceConfig"]["temperature"] == 0
    text = req["messages"][0]["content"][0]["text"]
    assert "<resume>\nJane Doe" in text
    assert "<job_description>\nBackend engineer" in text
    assert "guardrailConfig" not in req


def test_long_inputs_are_truncated() -> None:
    req = bedrock.build_request("x" * 50_000, "y" * 20_000, model="m")
    text = req["messages"][0]["content"][0]["text"]
    assert text.count("x") == bedrock.MAX_CV_CHARS
    assert text.count("y") == bedrock.MAX_JD_CHARS


def test_guardrail_is_attached_when_configured(bedrock_stub) -> None:
    client, stubber = bedrock_stub
    expected = request(guardrail_id="gr-123", guardrail_version="1")
    assert expected["guardrailConfig"] == {"guardrailIdentifier": "gr-123", "guardrailVersion": "1"}
    stubber.add_response("converse", response([tool(REPORT)]), expected)

    bedrock.analyze_live(client, CV, JD, guardrail_id="gr-123", guardrail_version="1")


def test_invalid_output_is_retried_once(bedrock_stub) -> None:
    client, stubber = bedrock_stub
    stubber.add_response("converse", response([tool({**REPORT, "ats_score": 300})]), request())
    stubber.add_response("converse", response([tool(REPORT)]), request())

    analysis = bedrock.analyze_live(client, CV, JD)

    assert analysis.attempts == 2
    assert analysis.input_tokens == 2000  # both calls are counted


def test_invalid_output_twice_raises(bedrock_stub) -> None:
    client, stubber = bedrock_stub
    for _ in range(2):
        stubber.add_response("converse", response([{"text": "Sorry, no."}], "end_turn"), request())

    with pytest.raises(InvalidReport):
        bedrock.analyze_live(client, CV, JD)


def test_json_in_a_text_block_is_accepted() -> None:
    import json

    text = "Here is the report:\n```json\n" + json.dumps(REPORT) + "\n```"
    assert bedrock.parse_response(response([{"text": text}], "end_turn")) == REPORT


def test_guardrail_intervention_is_reported() -> None:
    blocked = response([{"text": "Sorry, the model cannot answer."}], "guardrail_intervened")
    with pytest.raises(bedrock.AnalysisBlocked):
        bedrock.parse_response(blocked)


def test_throttling_propagates_for_an_sqs_retry(bedrock_stub) -> None:
    client, stubber = bedrock_stub
    stubber.add_client_error("converse", "ThrottlingException", http_status_code=429)

    with pytest.raises(client.exceptions.ThrottlingException):
        bedrock.analyze_live(client, CV, JD)


def test_mode_defaults_to_mock_and_never_creates_a_client() -> None:
    def no_client():
        raise AssertionError("Bedrock client created in mock mode")

    assert bedrock.mode() == "mock"
    assert bedrock.model_id() == "mock"
    analysis = bedrock.analyzer(no_client)(CV, JD)
    assert analysis.model_id == "mock"


def test_live_mode_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEDROCK_MODE", "LIVE")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")
    assert bedrock.model_id() == "amazon.nova-micro-v1:0"
    assert bedrock.analyzer(lambda: None) is not bedrock.analyze_mock


def test_unknown_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BEDROCK_MODE", "maybe")
    with pytest.raises(ValueError, match="BEDROCK_MODE"):
        bedrock.mode()


def test_mock_analysis_is_deterministic_keyword_match() -> None:
    first = bedrock.analyze_mock(CV, JD)

    assert first.report == bedrock.analyze_mock(CV, JD).report
    assert {"python", "aws", "lambda"} <= set(first.report["matched_skills"])
    assert first.report["missing_skills"] == ["backend", "engineer", "terraform"]
    assert first.report["ats_score"] == 50


def test_mock_skips_filler_words_and_counts_agree() -> None:
    filler = "Build and run serverless workloads. Hands-on Lambda. Nice to have: keep it secure."
    jd = filler + " " + " ".join(f"tool{i}" for i in range(60))
    report = bedrock.analyze_mock("Lambda serverless", jd).report

    skills = set(report["matched_skills"]) | set(report["missing_skills"])
    assert not skills & {"build", "run", "hands", "nice", "keep"}
    total = len(report["matched_skills"]) + len(report["missing_skills"])
    assert f"of {total} job description" in report["score_rationale"]
    assert report["ats_score"] == round(100 * len(report["matched_skills"]) / total)
