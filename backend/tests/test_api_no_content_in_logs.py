"""Logging rule for the API handlers: the job description and the report never reach the logs,
at DEBUG level, on success and on failure (see test_no_content_in_logs.py)."""

import json

import pytest
from api_events import SUB, api_event, lambda_context
from resume_analyzer.handlers import create_analysis, read_analyses
from test_no_content_in_logs import JOB_DESCRIPTION, MODEL_LINES, MODEL_REPORT, assert_not_logged

ANALYSIS_ID = "01JAAAAAAAAAAAAAAAAAAAAAA1"
JOB_TITLE = "Zebulon Chief Wrangler Title"
CONTENT = [JOB_DESCRIPTION, JOB_TITLE, *MODEL_LINES]


@pytest.fixture
def api_store(fake_api_store, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("UPLOADS_BUCKET", "uploads-bucket")
    return fake_api_store


def test_create_does_not_log_job_description(api_store, all_log_output) -> None:
    body = {"job_description": JOB_DESCRIPTION, "job_title": JOB_TITLE}
    result = create_analysis.handler(api_event("POST /analyses", body), lambda_context())

    output = all_log_output()
    assert result["statusCode"] == 201
    assert '"job_description_chars"' in output  # the handler did log, just not the content
    assert_not_logged(output, CONTENT)


def test_create_failure_does_not_log_job_description(
    api_store, all_log_output, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError(f"write failed for {args}")  # exception text carries the JD

    monkeypatch.setattr(api_store, "create_analysis", boom)
    body = {"job_description": JOB_DESCRIPTION, "job_title": JOB_TITLE}
    result = create_analysis.handler(api_event("POST /analyses", body), lambda_context())

    output = all_log_output()
    assert result["statusCode"] == 500
    assert "RuntimeError" in output
    assert_not_logged(output + result["body"], CONTENT)


def test_read_does_not_log_report(api_store, all_log_output) -> None:
    api_store.add_analysis(
        SUB, ANALYSIS_ID, JOB_DESCRIPTION, status="DONE", result=MODEL_REPORT, job_title=JOB_TITLE
    )
    detail = read_analyses.handler(
        api_event("GET /analyses/{analysis_id}", pathParameters={"analysis_id": ANALYSIS_ID}),
        lambda_context(),
    )
    history = read_analyses.handler(api_event("GET /analyses"), lambda_context())

    output = all_log_output()
    assert json.loads(detail["body"])["report"] == MODEL_REPORT
    assert history["statusCode"] == 200
    assert '"count": 1' in output
    assert_not_logged(output, CONTENT)


def test_read_failure_does_not_log_content(
    api_store, all_log_output, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError(f"read failed: {MODEL_REPORT}")

    monkeypatch.setattr(api_store, "get_analysis", boom)
    result = read_analyses.handler(
        api_event("GET /analyses/{analysis_id}", pathParameters={"analysis_id": ANALYSIS_ID}),
        lambda_context(),
    )

    assert result["statusCode"] == 500
    assert_not_logged(all_log_output() + result["body"], CONTENT)
