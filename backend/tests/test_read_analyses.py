import json

import pytest
from api_events import SUB, api_event, lambda_context
from resume_analyzer.handlers import read_analyses

A1, A2, A3 = (f"01JAAAAAAAAAAAAAAAAAAAAAA{n}" for n in (1, 2, 3))
REPORT = {"ats_score": 81, "summary": "good", "matched_skills": ["Python"]}


@pytest.fixture
def db(fake_api_store):
    fake_api_store.add_analysis(SUB, A1, "JD one", status="DONE", result=REPORT, model_id="m")
    fake_api_store.add_analysis(SUB, A2, "JD two", status="FAILED", error="InvalidReport")
    fake_api_store.add_analysis(SUB, A3, "JD three")
    fake_api_store.add_analysis("other-user", "01JAAAAAAAAAAAAAAAAAAAAAA9", "theirs")
    return fake_api_store


def call(route_key: str, **extra) -> tuple[int, dict]:
    result = read_analyses.handler(api_event(route_key, **extra), lambda_context())
    return result["statusCode"], json.loads(result["body"])


def test_history_lists_own_analyses_newest_first(db) -> None:
    status, body = call("GET /analyses")

    assert status == 200
    assert [i["analysis_id"] for i in body["items"]] == [A3, A2, A1]
    done = body["items"][2]
    assert done["status"] == "DONE"
    assert done["ats_score"] == 81
    assert "report" not in done and "job_description" not in done
    assert body["items"][1]["error"] == "InvalidReport"
    assert body["next_cursor"] is None


def test_history_pages_with_cursor(db) -> None:
    _, first = call("GET /analyses", queryStringParameters={"limit": "2"})
    assert [i["analysis_id"] for i in first["items"]] == [A3, A2]
    assert first["next_cursor"] == A2

    _, second = call(
        "GET /analyses", queryStringParameters={"limit": "2", "cursor": first["next_cursor"]}
    )
    assert [i["analysis_id"] for i in second["items"]] == [A1]
    assert second["next_cursor"] is None


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"limit": "0"}, "invalid_limit"),
        ({"limit": "51"}, "invalid_limit"),
        ({"limit": "x"}, "invalid_limit"),
        ({"cursor": "USER#other"}, "invalid_cursor"),
    ],
)
def test_history_rejects_bad_params(db, params, code) -> None:
    status, body = call("GET /analyses", queryStringParameters=params)
    assert (status, body["error"]) == (400, code)


def test_get_done_analysis_returns_report(db) -> None:
    status, body = call("GET /analyses/{analysis_id}", pathParameters={"analysis_id": A1})

    assert status == 200
    assert body["status"] == "DONE"
    assert body["report"] == REPORT
    assert body["job_description"] == "JD one"
    assert body["model_id"] == "m"


def test_get_pending_analysis_has_no_report(db) -> None:
    status, body = call("GET /analyses/{analysis_id}", pathParameters={"analysis_id": A3})
    assert (status, body["status"], body["report"]) == (200, "PENDING", None)


@pytest.mark.parametrize("analysis_id", [f"01JAAAAAAAAAAAAAAAAAAAAAA{n}" for n in (8, 9)])
def test_other_users_or_unknown_analysis_is_404(db, analysis_id) -> None:
    status, body = call("GET /analyses/{analysis_id}", pathParameters={"analysis_id": analysis_id})
    assert (status, body["error"]) == (404, "not_found")


def test_malformed_id_is_404_without_db_call(db, monkeypatch) -> None:
    monkeypatch.setattr(db, "get_analysis", lambda *a: pytest.fail("db called"))
    status, _ = call("GET /analyses/{analysis_id}", pathParameters={"analysis_id": "../x"})
    assert status == 404


def test_requires_user(db) -> None:
    status, body = call("GET /analyses", sub=None)
    assert (status, body["error"]) == (401, "unauthorized")


def test_unknown_route_is_404(db) -> None:
    status, _ = call("DELETE /analyses")
    assert status == 404
