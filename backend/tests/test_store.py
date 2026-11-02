import time

import pytest
from botocore.stub import ANY
from resume_analyzer import store as store_module
from resume_analyzer.store import Store, cache_key

KEY = {"pk": {"S": "USER#user-1"}, "sk": {"S": "ANALYSIS#an-1"}}
RESULT = {"ats_score": 70, "matched_skills": ["Python"], "summary": "ok"}


@pytest.fixture
def ddb(dynamodb_stub):
    client, stubber = dynamodb_stub
    return Store(client, "analyses", "cache"), stubber


def test_get_analysis_reads_consistently_and_returns_plain_types(ddb) -> None:
    store, stubber = ddb
    stubber.add_response(
        "get_item",
        {"Item": {**KEY, "status": {"S": "PENDING"}, "score": {"N": "5"}}},
        {"TableName": "analyses", "Key": KEY, "ConsistentRead": True},
    )

    item = store.get_analysis("user-1", "an-1")

    assert item["status"] == "PENDING"
    assert item["score"] == 5
    assert type(item["score"]) is int


def test_missing_analysis_returns_none(ddb) -> None:
    store, stubber = ddb
    stubber.add_response(
        "get_item", {}, {"TableName": "analyses", "Key": KEY, "ConsistentRead": True}
    )
    assert store.get_analysis("user-1", "an-1") is None


def test_mark_done_writes_result_only_to_an_existing_item(ddb) -> None:
    store, stubber = ddb
    stubber.add_response(
        "update_item",
        {},
        {
            "TableName": "analyses",
            "Key": KEY,
            "UpdateExpression": "SET #f0 = :v0, #f1 = :v1, #f2 = :v2, #f3 = :v3, #f4 = :v4",
            "ConditionExpression": "attribute_exists(pk)",
            "ExpressionAttributeNames": {
                "#f0": "status",
                "#f1": "updated_at",
                "#f2": "result",
                "#f3": "model_id",
                "#f4": "result_source",
            },
            "ExpressionAttributeValues": {
                ":v0": {"S": "DONE"},
                ":v1": ANY,
                ":v2": {
                    "M": {
                        "ats_score": {"N": "70"},
                        "matched_skills": {"L": [{"S": "Python"}]},
                        "summary": {"S": "ok"},
                    }
                },
                ":v3": {"S": "mock"},
                ":v4": {"S": "model"},
            },
        },
    )

    store.mark_done("user-1", "an-1", RESULT, "mock", "model")


def test_mark_failed_stores_only_the_error_code(ddb) -> None:
    store, stubber = ddb
    stubber.add_response(
        "update_item",
        {},
        {
            "TableName": "analyses",
            "Key": KEY,
            "UpdateExpression": "SET #f0 = :v0, #f1 = :v1, #f2 = :v2",
            "ConditionExpression": "attribute_exists(pk)",
            "ExpressionAttributeNames": {"#f0": "status", "#f1": "updated_at", "#f2": "error"},
            "ExpressionAttributeValues": {
                ":v0": {"S": "FAILED"},
                ":v1": ANY,
                ":v2": {"S": "InvalidReport"},
            },
        },
    )

    store.mark_failed("user-1", "an-1", "InvalidReport")


def test_cache_put_sets_ttl(ddb, monkeypatch: pytest.MonkeyPatch) -> None:
    store, stubber = ddb
    monkeypatch.setattr(store_module.time, "time", lambda: 1_000_000.0)
    stubber.add_response(
        "put_item",
        {},
        {
            "TableName": "cache",
            "Item": {
                "pk": {"S": "k1"},
                "result": ANY,
                "model_id": {"S": "mock"},
                "created_at": ANY,
                "expires_at": {"N": str(1_000_000 + 3600)},
            },
        },
    )

    store.put_cached("k1", RESULT, "mock", ttl_seconds=3600)


@pytest.mark.parametrize(("expires_in", "hit"), [(60, True), (-60, False)])
def test_cache_get_ignores_expired_items(ddb, expires_in: int, hit: bool) -> None:
    store, stubber = ddb
    stubber.add_response(
        "get_item",
        {
            "Item": {
                "pk": {"S": "k1"},
                "result": {"M": {"ats_score": {"N": "70"}}},
                "expires_at": {"N": str(int(time.time()) + expires_in)},
            }
        },
        {"TableName": "cache", "Key": {"pk": {"S": "k1"}}},
    )

    cached = store.get_cached("k1")

    assert (cached is not None) is hit
    if hit:
        assert cached["result"] == {"ats_score": 70}


def test_cache_key_depends_on_every_input() -> None:
    base = cache_key("h", "JD", "m", "1")
    assert base == cache_key("h", " JD \n", "m", "1")  # surrounding whitespace ignored
    assert len({base, cache_key("h2", "JD", "m", "1"), cache_key("h", "JD", "m", "2")}) == 3
