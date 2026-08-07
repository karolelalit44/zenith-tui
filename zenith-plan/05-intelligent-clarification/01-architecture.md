# Intelligent Clarification — Architecture

## State machine

`NONE → REQUIRED → ASKING → ANSWERED → VALIDATING → READY_TO_EXECUTE`, with `CANCELLED`, `EXPIRED`, and `SUPERSEDED` exits.

## Backend components

- `IntentClassifier`: detects answer/clarify/plan/execute and risk.
- `ClarificationPlanner`: creates ordered questions and answer dependencies.
- `AnswerValidator`: validates option/free-text answers against type and domain rules.
- `ClarificationStore`: persists immutable answers and current question state.
- `WorkflowCoordinator`: resumes execution only when required information is valid.

## Contracts

```text
ClarificationThread
  id, session_id, turn_run_id, status, goal, version, expires_at

ClarificationQuestion
  id, thread_id, prompt, type, options[], required,
  allows_free_text, validation_rules, order, status

ClarificationAnswer
  id, question_id, value, source, valid, supersedes_id, created_at
```

Emit `clarification_requested`, `answer_submitted`, `answer_rejected`, `clarification_ready`, `clarification_cancelled`, and `clarification_expired` events. The client may reconnect and receive the current thread in `SessionSnapshot`.

## UX behavior

Show one focused question at a time when dependent; batch independent questions. Support option selection, free text, answer editing, retry, cancellation, and explicit “continue with assumption” only for optional questions.
