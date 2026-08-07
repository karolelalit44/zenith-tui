# Tool Orchestration — Validation and Rollout

## Test matrix

- Unit: catalog validation, routing outputs, schema resolution, policy decisions, provider translation, idempotency, and scheduler limits.
- Integration: greeting/no-tools, knowledge/no-tools, repository analysis/read tools, multi-file change/write tools, test execution, approval rejection, cancellation, timeout, and capability expansion.
- Provider contract: native OpenAI-style, Anthropic-style, Gemini-style, and no-tool compatibility behavior.
- Security: prompt-injected tool names, poisoned MCP descriptions, path escape, argument smuggling, unknown calls, and permission bypass.
- Recovery: websocket reconnect before approval, during execution, after result persistence, and during child-agent work.

## Metrics

- Tool-schema input tokens per turn and reduction from baseline.
- Router latency, confidence, and misclassification rate.
- Zero-tool precision for conversational prompts.
- Capability recall for coding prompts.
- Invalid call, denied call, retry, timeout, cancellation, and success rates.
- p50/p95 tool and total turn latency; cost per successful turn.

## Rollout

1. Shadow-route requests while the existing tool selection remains authoritative.
2. Compare selected capabilities, expected tool use, latency, and schema cost.
3. Enable selective schemas for read-only requests behind a configuration flag.
4. Enable mutating tools after policy, idempotency, and reconnect tests pass.
5. Enable sub-agents last with strict aggregate budgets.

## Release gates

- No regression in tool task completion on the evaluation suite.
- Material schema-token reduction on mixed workloads.
- Zero unauthorized mutations in adversarial tests.
- Reconnect cannot duplicate a mutating invocation.
- Every invocation is visible in the restored session timeline.
