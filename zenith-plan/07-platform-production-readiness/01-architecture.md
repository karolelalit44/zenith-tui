# Platform Production Readiness — Architecture

## Reliability

- Idempotent command keys and monotonic event sequences.
- Durable status transitions and resumable checkpoints.
- Bounded retries with provider-aware backoff and retry classification.
- Cancellation propagated through websocket, turn, scheduler, and subprocess.
- Background jobs for indexing, summarization, and large-result processing.

## Security

- Canonical workspace-root/path validation for every file and command tool.
- Explicit permission policies with session/workspace scope and expiry.
- Secret redaction in prompts, logs, events, artifacts, and exports.
- Untrusted MCP/web content isolation and provenance.
- Safe subprocess environment, timeout, output limits, and process cleanup.

## Observability

Emit structured logs/metrics/traces keyed by session, turn, tool, provider, model, and context snapshot. Track latency, tokens, cost, errors, retries, queue depth, compaction, retrieval, and dropped events. Provide local diagnostic export with redaction.

## Scale seams

Keep repository and job interfaces transport-neutral so SQLite/filesystem can later be replaced by Postgres/object storage/queues. Do not introduce hosted infrastructure in the local-first milestone without measured need.
