# Intelligent Clarification — Risks, Debt, and Decisions

## Risks

- Too many questions create friction; too few cause incorrect destructive work.
- Model-generated options may omit a valid path or encode unsafe assumptions.
- Users may answer while a prior turn is still streaming or switch sessions mid-question.
- Free-text answers can contain prompt injection or contradictory requirements.
- “Progress” is misleading when question dependencies are unknown.

## Decisions

- Deterministic safety/configuration checks run before model questions.
- Required answers block mutating execution; optional answers may be skipped with a recorded assumption.
- Answers are immutable; edits create superseding records.
- All questions and assumptions are visible in the restored session.
- Use bounded question count and a clarification budget; escalate to a human-readable summary when the loop cannot converge.

## Debt

- Process-global callback state is not safe across sessions.
- `question` tool output is not a durable workflow record.
- No protocol/UI type currently represents pending questions.
