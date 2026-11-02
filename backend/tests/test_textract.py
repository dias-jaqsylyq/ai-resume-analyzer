import pytest
from resume_analyzer import textract

BUCKET, KEY, TOKEN = "uploads-bucket", "uploads/user-1/an-1.pdf", "a" * 64


def line(text: str, page: int = 1, n: int = 0) -> dict:
    return {"BlockType": "LINE", "Text": text, "Page": page, "Id": f"l{page}-{n}"}


def start(stubber, job_id: str = "job-1") -> None:
    stubber.add_response(
        "start_document_text_detection",
        {"JobId": job_id},
        {
            "DocumentLocation": {"S3Object": {"Bucket": BUCKET, "Name": KEY}},
            "ClientRequestToken": TOKEN,
        },
    )


def get(stubber, response: dict, after: str | None = None, job_id: str = "job-1") -> None:
    params = {"JobId": job_id, "MaxResults": textract.MAX_RESULTS}
    if after:
        params["NextToken"] = after
    stubber.add_response("get_document_text_detection", response, params)


def run(client, remaining_ms=lambda: 60_000, sleeps=None):
    return textract.extract_text(
        client,
        BUCKET,
        KEY,
        token=TOKEN,
        remaining_ms=remaining_ms,
        sleep=(sleeps.append if sleeps is not None else lambda _: None),
    )


def test_blocks_to_text_keeps_lines_per_page_and_cleans_whitespace() -> None:
    blocks = [
        {"BlockType": "PAGE", "Page": 1},
        line("  Jane   Doe ", 1),
        {"BlockType": "WORD", "Text": "Jane", "Page": 1},
        line("Python\tdeveloper", 1),
        line("   ", 1),
        line("Experience", 2),
    ]

    text, lines = textract.blocks_to_text(blocks)

    assert text == "Jane Doe\nPython developer\n\nExperience"
    assert lines == 3


def test_blocks_to_text_empty_document() -> None:
    assert textract.blocks_to_text([]) == ("", 0)


def test_request_token_is_stable_and_valid() -> None:
    token = textract.request_token(BUCKET, KEY, "etag-1")

    assert token == textract.request_token(BUCKET, KEY, "etag-1")
    assert token != textract.request_token(BUCKET, KEY, "etag-2")
    assert len(token) == 64
    assert token.isalnum()


def test_extract_polls_until_done_and_follows_pagination(textract_stub) -> None:
    client, stubber = textract_stub
    start(stubber)
    get(stubber, {"JobStatus": "IN_PROGRESS"})
    get(stubber, {"JobStatus": "IN_PROGRESS"})
    get(
        stubber,
        {
            "JobStatus": "SUCCEEDED",
            "DocumentMetadata": {"Pages": 2},
            "Blocks": [line("Jane Doe", 1)],
            "NextToken": "t1",
        },
    )
    get(stubber, {"JobStatus": "SUCCEEDED", "Blocks": [line("Skills", 2)]}, after="t1")
    sleeps: list[float] = []

    result = run(client, sleeps=sleeps)

    assert result.text == "Jane Doe\n\nSkills"
    assert (result.pages, result.lines, result.chars) == (2, 2, len("Jane Doe\n\nSkills"))
    assert (result.job_id, result.status) == ("job-1", "SUCCEEDED")
    assert sleeps == [1.0, 1.5]


def test_extract_accepts_partial_success(textract_stub) -> None:
    client, stubber = textract_stub
    start(stubber)
    get(
        stubber,
        {
            "JobStatus": "PARTIAL_SUCCESS",
            "DocumentMetadata": {"Pages": 1},
            "Blocks": [line("Jane Doe")],
            "Warnings": [{"ErrorCode": "x", "Pages": [2]}],
        },
    )

    assert run(client).status == "PARTIAL_SUCCESS"


def test_extract_raises_when_job_fails(textract_stub) -> None:
    client, stubber = textract_stub
    start(stubber)
    get(stubber, {"JobStatus": "FAILED", "StatusMessage": "UNSUPPORTED_DOCUMENT"})

    with pytest.raises(textract.TextractJobFailed, match="UNSUPPORTED_DOCUMENT"):
        run(client)


def test_extract_gives_up_before_lambda_deadline(textract_stub) -> None:
    client, stubber = textract_stub
    start(stubber)
    get(stubber, {"JobStatus": "IN_PROGRESS"})

    with pytest.raises(textract.ExtractionTimeout):
        run(client, remaining_ms=lambda: 10_500)
