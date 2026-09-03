# Prompt Sending

## Overview

The path from a user typing a prompt to the LLM receiving a request. Includes resolving any attachments (files, agents, MCP resources) into parts, assembling system prompt + history, and streaming.

### How opencode does it

- `Session.prompt()` calls `createUserMessage(input)`, which:
  - Looks up the agent and model.
  - For each part of the user message, calls `resolveUserPart`:
    - MCP resource part â†’ reads the resource, attaches text or file parts (size/mime checked).
    - `data:` URL with text/plain â†’ feeds to the Read tool.
    - `file:` URL â†’ runs the actual Read tool with a range, attaches output parts.
    - agent part â†’ wraps with synthetic text telling the agent to call the `task` tool.
  - Normalizes images.
  - Publishes the user message + parts.
- `runLoop(sessionID)` builds messages via `MessageV2`, filters compacted messages, then per step calls `handle.process()` with system, history, tools, and `toolChoice`.
- Exactly one `llm.stream(request)` per provider turn.
- On loop exit, returns the last assistant message.

### How codex does it

- The user prompt is converted into `ResponseItem[]` (multipart messages) and merged with tool specs and base instructions into a `Prompt`.
- `build_prompt` in `turn.rs` constructs `Prompt { input, tools: tool_router.model_visible_specs(), parallel_tool_calls: true, base_instructions, output_schema }`.
- `client.run(prompt)` streams the response.
- Multipart message content (text, images, tool calls) all flow as `ResponseItem`s.

### What zenith has today

- `server/agents/prompt_executor.py` â€” the `PromptExecutor.run` / `_execute` method.
- The `_execute` method now routes every turn through `PromptPath` and the module-01 `SimpleLoop` seam; the legacy captain/crewmate/default fork has been removed.
- The user prompt is resolved into attachment parts at prompt-build time by `PromptPath.resolve_user_parts`, covering file/folder/inline/agent/MCP resources.
- Streaming goes through `server/agents/llm_stream.py` (`stream_completion`), which builds a `StreamState` and emits THINKING/MESSAGE/TOOL_CALL/TOOL_RESULT events.

### What is correct

- The `llm_stream` abstraction (streaming completion with event emission) is reasonable.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered:**
- Separate event stream (`llm_stream`) parallel to the message model. opencode/codex stream into the single message/part model.

**Missing:**
- No attachment resolution at prompt time (MCP resources, file URLs, data URLs, agent parts). opencode's `resolveUserPart` and codex's `ResponseItem` multipart both handle this.

### Static/simulation code to remove
- `_E2E_INSTRUMENT` and `_instrument()`.

## What we will do

Build a single clean prompt path:
1. One entry point that builds the user message from parts.
2. Resolve each part type: text, file, agent, MCP resource â€” at prompt-build time.
3. Assemble system prompt + history + tools in one place.
4. Stream one LLM turn per request.
5. No delegation branching.

## What we will REMOVE
- The 3-way delegation branch (captain/crewmate/default).
- The parallel `llm_stream` event stream (fold into the message/part model).

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| (none specific here) | â€” | â€” |

## Verification / signoff
- [x] Single prompt path, no delegation branching
- [x] File/agent/MCP-resource parts resolved at prompt time
- [x] ruff + pytest + runtime smoke pass

## Status: Done
