# Command Output / Response

## Overview

How the output of a running/finished command is captured, truncated, and presented to the user. Companion to `command_runner`.

### How opencode does it

- Output is captured from the shell process stream and written into the **tool part's `state.metadata.output`** as it arrives.
- The user sees the running command's output live in the tool block.
- Final output is subject to the `Truncate` service: if output exceeds the limit, it is truncated, the full output written to a truncation directory, and the model told the path.
- Result presented as part of the single assistant message (tool call block: title, live output, completed state).

### How codex does it

- Output streamed as `ExecCommandOutputDelta` events.
- Chunk-capped at `EXEC_OUTPUT_MAX_BYTES`.
- The TUI renders command output inline as it streams.
- `ExecCapturePolicy` controls whether stdout is retained on success (`no_stdout_on_success`), with a retained-bytes cap.

### What zenith has today

- `server/providers/responder.py` â€” event factory `tool_result`, `progress`, `message_event`, etc., with `MAX_EVENT_OUTPUT = 5000` preview cap.
- Tool results carry a `truncated` flag and a preview.
- Command output from `background` jobs is retrieved by a separate `job_output` call, with `BG_OUTPUT_TAIL = 800` (only the tail is returned).
- `format_tool_result` in `server/toolkit/executor.py` formats tool output.
- Heavy outputs (> 8000 tokens) isolated to disk with a marker telling the model to re-read.

### What is correct

- Truncation with a preview + path reference concept (matches opencode's truncation-dir).

### What is wrong / over-engineered / incorrect / missing

**Over-engineered / incorrect:**
- `MAX_EVENT_OUTPUT = 5000` preview as the wire contract â€” the TUI only ever gets a 5K preview, losing context. opencode/codex stream the full (truncated) output into the message.
- `BG_OUTPUT_TAIL = 800` â€” the poll model returns only the tail, so large command output is effectively lost unless the model does more work.
- Heavy-output isolation to disk adds indirection not present in the reference (they use a single truncate service).

**Missing:**
- Live streaming of command output into the tool part.
- A single unified Truncate service (rather than previews + isolation + tail).

## What we will do

- Present command output as part of the tool call result, streamed live.
- Apply one Truncate service: cap output, write oversized output to a file, reference the path.
- Emit the full (truncated) output in the tool result event, not a small preview.
- Remove the poll-based tail retrieval.

## What we will REMOVE
- `MAX_EVENT_OUTPUT` preview-only wire contract (emit full truncated output).
- `BG_OUTPUT_TAIL` poll model (stream live instead).
- Heavy-output isolation (replace with unified Truncate service).

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| (none specific here) | â€” | â€” |

## Verification / signoff
- [ ] Command output streamed live into the tool result
- [ ] One Truncate service (cap + path reference)
- [ ] Full truncated output in events, not a tiny preview
- [ ] No poll-based tail retrieval for normal commands
- [ ] ruff + pytest + runtime smoke pass

## Status: Pending
