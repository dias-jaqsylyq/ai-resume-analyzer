# 05 — Operations: alarms and the dead-letter queue

## CloudWatch alarms (`infra/alarms.tf`)

Nine alarms, all `Sum`/`Maximum > 0` over 5 minutes, missing data = OK. They have no actions
(SNS is outside the fixed stack), so check them in the console under **CloudWatch → Alarms**, or:

    aws cloudwatch describe-alarms --alarm-name-prefix ai-resume-analyzer- --state-value ALARM \
      --query 'MetricAlarms[].AlarmName'

| Alarm | Metric | Meaning |
| --- | --- | --- |
| `analysis-dlq-not-empty` | `AWS/SQS ApproximateNumberOfMessagesVisible` on the DLQ | an upload failed every retry |
| `failed-analyses` | `AiResumeAnalyzer/FailedAnalyses` (log metric filter) | an analysis ended FAILED (permanent error or last retry) |
| `<function>-errors` ×3 | `AWS/Lambda Errors` | crash, timeout or out of memory |
| `<function>-throttles` ×3 | `AWS/Lambda Throttles` | account concurrency limit reached |
| `api-5xx` | `AWS/ApiGateway 5xx` (HTTP API, `ApiId`) | the API returned a server error |

process-analysis catches its own exceptions (failed messages go back to SQS through
`batchItemFailures`), so failed analyses do not show up in Lambda `Errors`; the
`failed-analyses` metric filter counts the `"analysis failed"` log line with `last_attempt = true`
instead (contract pinned by `backend/tests/test_dlq_check.py`).

Cost: CloudWatch's free tier covers 10 alarms and 10 custom metrics; this uses 9 and 1.

## DLQ end-to-end check (RA-12)

In AWS CloudShell, from a clone of the repo:

    cd backend
    python3 scripts/dlq_check.py send    # one poison (non-JSON) message to the analysis queue
    # wait ~40 min: 3 receives x 12 min visibility timeout
    python3 scripts/dlq_check.py check   # expect "DLQ redrive: OK"; the check message is deleted

While it waits, Lambda logs show three `"message failed"` lines (`error_type: JSONDecodeError`),
and once it reaches the DLQ the `analysis-dlq-not-empty` alarm goes to ALARM (back to OK about
5 minutes after `check` deletes it). The script prints only ids, counts and ages; other DLQ
messages are left in place and their bodies are never printed.

## What to do with a message in the DLQ

1. Find the analysis id in the process-analysis logs (Logs Insights):
   `filter message = "message failed" | fields correlation_id, error_type, receive_count`.
   The analysis item is already FAILED (marked on the last receive), so the user sees the error.
2. If the cause is fixed (e.g. a quota), move the messages back to the analysis queue:
   `aws sqs start-message-move-task --source-arn <DLQ arn>` (the DLQ's redrive allow policy only
   permits the analysis queue). Otherwise purge: `aws sqs purge-queue --queue-url <DLQ url>`.
