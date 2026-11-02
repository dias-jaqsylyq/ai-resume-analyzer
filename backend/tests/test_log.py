import io
import json
import logging
from types import SimpleNamespace

import pytest
from resume_analyzer import log


@pytest.fixture
def stream(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Point the shared JSON handler at an in-memory stream."""
    buffer = io.StringIO()
    root = log.get_logger()
    for handler in root.handlers:
        if getattr(handler, "_resume_analyzer", False):
            monkeypatch.setattr(handler, "stream", buffer)
    return buffer


def lines(buffer: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in buffer.getvalue().splitlines()]


def lambda_context(request_id: str = "req-1") -> SimpleNamespace:
    return SimpleNamespace(aws_request_id=request_id, function_name="process-analysis")


def test_line_is_single_json_object_with_core_fields(stream: io.StringIO) -> None:
    log.get_logger("tests").info("hello %s", "world")

    [entry] = lines(stream)
    assert entry["message"] == "hello world"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "resume_analyzer.tests"
    assert entry["correlation_id"] is None
    assert entry["timestamp"].endswith("+00:00")


def test_extra_fields_are_top_level_keys(stream: io.StringIO) -> None:
    log.get_logger("tests").info("done", extra={"stage": "textract", "pages": 2})

    [entry] = lines(stream)
    assert entry["stage"] == "textract"
    assert entry["pages"] == 2


def test_correlation_context_binds_and_resets(stream: io.StringIO) -> None:
    logger = log.get_logger("tests")
    with log.correlation_context("analysis-123") as cid:
        assert cid == "analysis-123"
        logger.info("inside")
    logger.info("outside")

    inside, outside = lines(stream)
    assert inside["correlation_id"] == "analysis-123"
    assert outside["correlation_id"] is None


def test_correlation_context_generates_id_when_missing() -> None:
    with log.correlation_context(None) as cid:
        assert cid
        assert log.get_correlation_id() == cid
    assert log.get_correlation_id() is None


def test_sensitive_keys_are_redacted_at_any_depth(stream: io.StringIO) -> None:
    log.get_logger("tests").info(
        "parsed",
        extra={
            "cv_text": "John Doe, john@example.com",
            "detail": {"Email": "john@example.com", "pages": 1, "items": [{"text": "x"}]},
        },
    )

    [entry] = lines(stream)
    assert entry["cv_text"] == log.REDACTED
    assert entry["detail"] == {"Email": log.REDACTED, "pages": 1, "items": [{"text": log.REDACTED}]}
    assert "john@example.com" not in stream.getvalue()


def test_exception_is_included(stream: io.StringIO) -> None:
    logger = log.get_logger("tests")
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failed")

    [entry] = lines(stream)
    assert entry["level"] == "ERROR"
    assert "ValueError: boom" in entry["exception"]


def test_non_json_values_are_stringified(stream: io.StringIO) -> None:
    log.get_logger("tests").info("odd", extra={"obj": object()})

    [entry] = lines(stream)
    assert entry["obj"].startswith("<object object")


def test_inject_lambda_context_uses_event_correlation_id(stream: io.StringIO) -> None:
    logger = log.get_logger("tests")

    @log.inject_lambda_context(correlation_id_from=lambda event: event["analysis_id"])
    def handler(event, context):
        logger.info("working")
        return log.get_correlation_id()

    assert handler({"analysis_id": "an-1"}, lambda_context()) == "an-1"
    logger.info("after")

    working, after = lines(stream)
    assert working["correlation_id"] == "an-1"
    assert working["aws_request_id"] == "req-1"
    assert working["function_name"] == "process-analysis"
    assert after["correlation_id"] is None
    assert "aws_request_id" not in after


def test_inject_lambda_context_falls_back_to_request_id() -> None:
    @log.inject_lambda_context(correlation_id_from=lambda event: event["missing"])
    def handler(event, context):
        return log.get_correlation_id()

    assert handler({}, lambda_context("req-9")) == "req-9"


def test_inject_lambda_context_without_arguments() -> None:
    @log.inject_lambda_context
    def handler(event, context):
        return log.get_correlation_id()

    assert handler({}, lambda_context("req-7")) == "req-7"


def test_cold_start_is_true_only_once(stream: io.StringIO, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log, "_cold_start", True)
    logger = log.get_logger("tests")

    @log.inject_lambda_context
    def handler(event, context):
        logger.info("call")

    handler({}, lambda_context())
    handler({}, lambda_context())

    first, second = lines(stream)
    assert first["cold_start"] is True
    assert second["cold_start"] is False


def test_context_is_cleared_when_handler_raises() -> None:
    @log.inject_lambda_context
    def handler(event, context):
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        handler({}, lambda_context())
    assert log.get_correlation_id() is None


def test_handler_is_attached_once_and_root_does_not_propagate() -> None:
    log.get_logger("a")
    log.get_logger("b")
    root = logging.getLogger(log.ROOT_LOGGER_NAME)

    ours = [h for h in root.handlers if getattr(h, "_resume_analyzer", False)]
    assert len(ours) == 1
    assert root.propagate is False


def test_log_level_comes_from_env(stream: io.StringIO, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "warning")
    logger = log.get_logger("tests")
    logger.info("hidden")
    logger.warning("shown")
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    log.get_logger()

    [entry] = lines(stream)
    assert entry["message"] == "shown"
