import io
import logging
from collections.abc import Callable, Iterator

import boto3
import pytest
from botocore.stub import Stubber
from resume_analyzer import log


@pytest.fixture
def textract_stub() -> Iterator[tuple[object, Stubber]]:
    """A real Textract client whose calls are answered by botocore's Stubber.

    Stubber validates request parameters against the AWS service model, so a test fails
    if code passes a parameter that the real API does not accept.
    """
    client = boto3.client(
        "textract",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",  # noqa: S106 - fake credentials, never sent
    )
    with Stubber(client) as stubber:
        yield client, stubber
        stubber.assert_no_pending_responses()


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
