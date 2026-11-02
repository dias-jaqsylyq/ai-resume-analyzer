"""DynamoDB access for the ``analyses`` and ``cache`` tables (data model: docs/02-architecture.md).

- ``analyses``: pk ``USER#<sub>``, sk ``ANALYSIS#<id>``; status PENDING | PROCESSING | DONE |
  FAILED, ``job_description`` (written by create-analysis), ``result``, ``model_id``, ``error``.
- ``cache``: pk = cache key (SHA-256), ``result``, ``model_id``, ``expires_at`` (TTL, epoch s).

Uses the low-level client so tests can check every request with botocore ``Stubber``.
``error`` only ever holds an error code (exception class name), never a message or content.
"""

from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

PENDING = "PENDING"
PROCESSING = "PROCESSING"
DONE = "DONE"
FAILED = "FAILED"
DEFAULT_CACHE_TTL_SECONDS = 24 * 3600

_serializer = TypeSerializer()
_deserializer = TypeDeserializer()


def _to_ddb(value: dict[str, Any]) -> dict[str, Any]:
    return _serializer.serialize(value)["M"]


def _from_ddb(item: dict[str, Any]) -> dict[str, Any]:
    return _plain(_deserializer.deserialize({"M": item}))


def _plain(value: Any) -> Any:
    """Turn DynamoDB Decimals back into int/float so results are plain JSON types."""
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if type(value).__name__ == "Decimal":
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def cache_key(cv_sha256: str, job_description: str, model_id: str, prompt_version: str) -> str:
    """Same CV file + same JD + same model and prompt → same report."""
    material = "\n".join([cv_sha256, model_id, prompt_version, job_description.strip()])
    return hashlib.sha256(material.encode()).hexdigest()


class Store:
    def __init__(self, client: Any, analyses_table: str, cache_table: str) -> None:
        self.client = client
        self.analyses_table = analyses_table
        self.cache_table = cache_table

    @staticmethod
    def _key(user_sub: str, analysis_id: str) -> dict[str, Any]:
        return {"pk": {"S": f"USER#{user_sub}"}, "sk": {"S": f"ANALYSIS#{analysis_id}"}}

    def get_analysis(self, user_sub: str, analysis_id: str) -> dict[str, Any] | None:
        response = self.client.get_item(
            TableName=self.analyses_table,
            Key=self._key(user_sub, analysis_id),
            ConsistentRead=True,
        )
        item = response.get("Item")
        return _from_ddb(item) if item else None

    def _set_status(
        self, user_sub: str, analysis_id: str, status: str, extra: dict[str, Any] | None = None
    ) -> None:
        values = {"status": status, "updated_at": _now(), **(extra or {})}
        names = {f"#f{i}": k for i, k in enumerate(values)}
        self.client.update_item(
            TableName=self.analyses_table,
            Key=self._key(user_sub, analysis_id),
            UpdateExpression="SET " + ", ".join(f"{n} = :v{i}" for i, n in enumerate(names)),
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeNames=names,
            ExpressionAttributeValues={
                f":v{i}": _serializer.serialize(v) for i, v in enumerate(values.values())
            },
        )

    def mark_processing(self, user_sub: str, analysis_id: str) -> None:
        self._set_status(user_sub, analysis_id, PROCESSING)

    def mark_done(
        self, user_sub: str, analysis_id: str, result: dict[str, Any], model_id: str, source: str
    ) -> None:
        self._set_status(
            user_sub,
            analysis_id,
            DONE,
            {"result": result, "model_id": model_id, "result_source": source},
        )

    def mark_failed(self, user_sub: str, analysis_id: str, error_code: str) -> None:
        self._set_status(user_sub, analysis_id, FAILED, {"error": error_code})

    def get_cached(self, key: str) -> dict[str, Any] | None:
        response = self.client.get_item(TableName=self.cache_table, Key={"pk": {"S": key}})
        item = response.get("Item")
        if not item:
            return None
        cached = _from_ddb(item)
        # TTL deletion is lazy (can lag), so check expiry ourselves.
        if cached.get("expires_at", 0) <= time.time():
            return None
        return cached

    def put_cached(
        self,
        key: str,
        result: dict[str, Any],
        model_id: str,
        ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self.client.put_item(
            TableName=self.cache_table,
            Item=_to_ddb(
                {
                    "pk": key,
                    "result": result,
                    "model_id": model_id,
                    "created_at": _now(),
                    "expires_at": int(time.time()) + ttl_seconds,
                }
            ),
        )
