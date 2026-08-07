# Intelligent Clarification — Validation and Rollout

## Tests

- Fully specified coding prompt executes directly.
- Ambiguous authentication prompt produces useful options and no mutation.
- Invalid option/free-text answer is rejected with actionable feedback.
- Edited answer supersedes prior answer and revalidates dependent questions.
- Ignore/timeout, cancel, interrupt, reconnect, restart, and session switch preserve state.
- Required clarification cannot be bypassed through hallucinated tool calls or alternate RPCs.
- Concurrent sessions do not receive each other’s questions or answers.

## Metrics and gates

- Clarification rate by intent/category.
- First-question acceptance and answer correction rate.
- Time-to-ready, abandonment, timeout, and cancellation rates.
- Unsafe/incorrect execution incidents and user-reported assumption corrections.

Roll out in shadow classification, then read-only clarification, then mutating workflows with a kill switch and audit logs.
