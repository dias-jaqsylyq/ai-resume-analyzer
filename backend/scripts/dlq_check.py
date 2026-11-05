"""End-to-end check of the SQS dead-letter queue (RA-12; run by the owner in AWS CloudShell).

    python3 scripts/dlq_check.py send     # puts one poison message on the analysis queue
    # ... wait ~40 minutes (3 receives x 12 min visibility timeout) ...
    python3 scripts/dlq_check.py check    # finds it in the DLQ, deletes it, prints the result

The poison message is not JSON, so process-analysis fails on every receive and reports it
back to SQS (`batchItemFailures`). After `maxReceiveCount` (3) receives, the queue's redrive
policy moves it to the DLQ. No S3 object, DynamoDB item, Textract or Bedrock call is involved.
The DLQ alarm (`ai-resume-analyzer-analysis-dlq-not-empty`) goes to ALARM while it waits there.

Prints only message ids, counts, receive counts and ages. Bodies of other DLQ messages (real
failed uploads) are never printed and are left in the queue untouched.
Queue names default to the Terraform ones; override with QUEUE_NAME / DLQ_NAME.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from typing import Any

import boto3

MARKER_PREFIX = "dlq-check:"
QUEUE_NAME = os.environ.get("QUEUE_NAME", "ai-resume-analyzer-analysis")
DLQ_NAME = os.environ.get("DLQ_NAME", "ai-resume-analyzer-analysis-dlq")


def is_marker(body: str) -> bool:
    return body.startswith(MARKER_PREFIX)


def send(sqs: Any, queue_url: str) -> str:
    """Send one poison message; returns the SQS message id."""
    marker = f"{MARKER_PREFIX}{uuid.uuid4()}"  # deliberately not JSON
    return sqs.send_message(QueueUrl=queue_url, MessageBody=marker)["MessageId"]


def check(sqs: Any, dlq_url: str, polls: int = 5) -> dict[str, Any]:
    """Find check messages in the DLQ and delete them; other messages are released at once.

    Returns {"found": [{"message_id", "receive_count", "age_s"}], "other": <count>}.
    """
    found: list[dict[str, Any]] = []
    others: set[str] = set()
    now_ms = time.time() * 1000
    for _ in range(polls):
        response = sqs.receive_message(
            QueueUrl=dlq_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=2,
            VisibilityTimeout=30,
            AttributeNames=["ApproximateReceiveCount", "SentTimestamp"],
        )
        messages = response.get("Messages", [])
        if not messages:
            break
        for message in messages:
            if is_marker(message.get("Body", "")):
                attributes = message.get("Attributes", {})
                found.append(
                    {
                        "message_id": message["MessageId"],
                        "receive_count": int(attributes.get("ApproximateReceiveCount", 0)),
                        "age_s": round(
                            (now_ms - int(attributes.get("SentTimestamp", now_ms))) / 1000
                        ),
                    }
                )
                sqs.delete_message(QueueUrl=dlq_url, ReceiptHandle=message["ReceiptHandle"])
            else:
                others.add(message["MessageId"])
                sqs.change_message_visibility(
                    QueueUrl=dlq_url, ReceiptHandle=message["ReceiptHandle"], VisibilityTimeout=0
                )
    return {"found": found, "other": len(others)}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("send", "check"):
        print(__doc__)
        return 2
    sqs = boto3.client("sqs")
    if argv[1] == "send":
        queue_url = sqs.get_queue_url(QueueName=QUEUE_NAME)["QueueUrl"]
        print(f"sent poison message {send(sqs, queue_url)} to {QUEUE_NAME}")
        print("run `check` in ~40 minutes (3 receives x 12 min visibility timeout)")
        return 0

    dlq_url = sqs.get_queue_url(QueueName=DLQ_NAME)["QueueUrl"]
    result = check(sqs, dlq_url)
    for item in result["found"]:
        print(
            f"in DLQ: {item['message_id']} after {item['age_s']}s "
            f"(DLQ receive count {item['receive_count']}), deleted"
        )
    print(f"other messages in DLQ (left untouched): {result['other']}")
    if not result["found"]:
        print("check message not in the DLQ yet; try again in a few minutes")
        return 1
    print("DLQ redrive: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
