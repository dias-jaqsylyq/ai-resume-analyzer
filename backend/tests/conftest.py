import io
import logging
from collections.abc import Callable, Iterator

import boto3
import pytest
from botocore.stub import Stubber
from resume_analyzer import log


def stubbed_client(service: str) -> tuple[object, Stubber]:
    """A real boto3 client whose calls are answered by botocore's Stubber.

    Stubber validates request parameters against the AWS service model, so a test fails
    if code passes a parameter that the real API does not accept.
    """
    client = boto3.client(
        service,
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",  # noqa: S106 - fake credentials, never sent
    )
    return client, Stubber(client)


@pytest.fixture
def textract_stub() -> Iterator[tuple[object, Stubber]]:
    client, stubber = stubbed_client("textract")
    with stubber:
        yield client, stubber
        stubber.assert_no_pending_responses()


@pytest.fixture
def bedrock_stub() -> Iterator[tuple[object, Stubber]]:
    client, stubber = stubbed_client("bedrock-runtime")
    with stubber:
        yield client, stubber
        stubber.assert_no_pending_responses()


@pytest.fixture
def dynamodb_stub() -> Iterator[tuple[object, Stubber]]:
    client, stubber = stubbed_client("dynamodb")
    with stubber:
        yield client, stubber
        stubber.assert_no_pending_responses()


class FakeStore:
    """In-memory stand-in for ``resume_analyzer.store.Store`` (its requests are tested in
    test_store.py with Stubber)."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}
        self.cache: dict[str, dict] = {}
        self.history: list[tuple[str, str]] = []  # (analysis_id, status)

    def add_analysis(self, user_sub: str, analysis_id: str, job_description: str, **extra) -> None:
        self.items[(user_sub, analysis_id)] = {
            "status": "PENDING",
            "job_description": job_description,
            **extra,
        }

    def get_analysis(self, user_sub: str, analysis_id: str) -> dict | None:
        item = self.items.get((user_sub, analysis_id))
        return dict(item) if item else None

    def _set(self, user_sub: str, analysis_id: str, status: str, **fields) -> None:
        item = self.items[(user_sub, analysis_id)]  # KeyError ~ ConditionalCheckFailed
        item.update(status=status, **fields)
        self.history.append((analysis_id, status))

    def mark_processing(self, user_sub: str, analysis_id: str) -> None:
        self._set(user_sub, analysis_id, "PROCESSING")

    def mark_done(self, user_sub, analysis_id, result, model_id, source) -> None:
        self._set(
            user_sub, analysis_id, "DONE", result=result, model_id=model_id, result_source=source
        )

    def mark_failed(self, user_sub: str, analysis_id: str, error_code: str) -> None:
        self._set(user_sub, analysis_id, "FAILED", error=error_code)

    def create_analysis(self, user_sub, analysis_id, job_description, job_title) -> dict:
        assert (user_sub, analysis_id) not in self.items  # ~ attribute_not_exists(pk)
        item = {
            "analysis_id": analysis_id,
            "status": "PENDING",
            "job_description": job_description,
            "created_at": "2026-11-02T00:00:00+00:00",
        }
        if job_title:
            item["job_title"] = job_title
        self.items[(user_sub, analysis_id)] = item
        return dict(item)

    def list_analyses(self, user_sub, limit, after_analysis_id=None):
        ids = sorted((a for (u, a) in self.items if u == user_sub), reverse=True)
        if after_analysis_id:
            ids = [a for a in ids if a < after_analysis_id]
        page = ids[:limit]
        items = [{"sk": f"ANALYSIS#{a}", **self.items[(user_sub, a)]} for a in page]
        return items, (page[-1] if len(ids) > limit else None)

    def get_cached(self, key: str) -> dict | None:
        return self.cache.get(key)

    def put_cached(self, key: str, result: dict, model_id: str, ttl_seconds: int = 0) -> None:
        self.cache[key] = {"result": result, "model_id": model_id}


@pytest.fixture
def all_log_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> Iterator[Callable[[], str]]:
    """Capture everything a handler could emit, at DEBUG: our JSON logs, other loggers, print().

    Returns a function that gives the combined text captured so far.
    """
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    root = log.get_logger()
    buffer = io.StringIO()
    for handler in root.handlers:
        if getattr(handler, "_resume_analyzer", False):
            monkeypatch.setattr(handler, "stream", buffer)
    caplog.set_level(logging.DEBUG)
    printed: list[str] = []

    def output() -> str:
        printed.extend(capsys.readouterr())  # readouterr() drains, so keep what was read
        return "\n".join([buffer.getvalue(), caplog.text, *printed])

    yield output
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    log.get_logger()


@pytest.fixture
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeStore:
    """process-analysis wired to an in-memory store, with a fixed CV hash and mock analysis."""
    from resume_analyzer.handlers import process_analysis

    store = FakeStore()
    monkeypatch.setattr(process_analysis, "store", lambda: store)
    monkeypatch.setattr(process_analysis, "cv_sha256", lambda upload: f"sha-{upload.key}")
    monkeypatch.delenv("BEDROCK_MODE", raising=False)
    return store


@pytest.fixture
def fake_api_store(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeStore]:
    """create-analysis and read-analyses wired to one in-memory store; S3 signing uses fake
    credentials (pre-signing is local, nothing is sent)."""
    from resume_analyzer.handlers import create_analysis, read_analyses

    store = FakeStore()
    monkeypatch.setattr(create_analysis, "store", lambda: store)
    monkeypatch.setattr(read_analyses, "store", lambda: store)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    create_analysis.s3_client.cache_clear()
    yield store
    create_analysis.s3_client.cache_clear()
