# Web Tools (webfetch / websearch)

## Overview

How zenith fetches web pages and searches the web.

### How opencode does it

- `tool/webfetch.ts`: 5MB max, 30s default / 120s max timeout, `format` text|markdown|html â€” **no LLM extract step**. Pure fetch + convert.
- `tool/websearch.ts`: **provider abstraction** â€” `exa` or `parallel` selected via env `OPENCODE_WEBSEARCH_PROVIDER` or runtime flags; rich params `numResults`(8), `livecrawl`(fallback|preferred), `type`(auto|fast|deep), `contextMaxCharacters`(10000).
- `tool/mcp-websearch.ts`: calls Exa/Parallel **over MCP JSON-RPC over HTTP** with SSE-response parsing.

### How codex does it

- `web_search.rs` only formats a `WebSearchAction` into the model context. **No client-side search backend** â€” delegated to the model/action layer.

### What zenith has today

- `server/toolkit/tools/webfetch.py` (169): httpx GET + `html_to_markdown`, `max_chars` clamp (1000..200000, default `DEFAULT_WEBFETCH_MAX_BYTES=40_000`), and an **optional `extract` LLM-extraction pass** (`_extract_answer`, `_EXTRACT_MAX_CHARS=25000`).
- `server/toolkit/tools/_html_text.py` (197): HTMLâ†’Markdown converter.
- `server/toolkit/tools/websearch.py` (230): `_DEFAULT_MAX_RESULTS=8`, backend via env `ZENITH_SEARCH_API`/`_KEY` (tavily|brave|serper|bing) else **DuckDuckGo HTML scrape** fallback. Optional `allowed_domains` filter.
- Constants: `WEBFETCH_TIMEOUT_*`, `WEBSEARCH_TIMEOUT_*`, `DEFAULT_WEB_TIMEOUT=30`, `_EXTRACT_MAX_CHARS`, `DEFAULT_USER_AGENT`, plus duplicate module-local `_DEFAULT_MAX_CHARS`/`_DEFAULT_MAX_RESULTS`.

### What is correct

- webfetch returning Markdown (never raw HTML) + output cap matches opencode.
- DuckDuckGo no-key fallback is pragmatic/defensible.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered / invented:**
- The `extract` **LLM round-trip** (`webfetch.py:149-169`) has **no counterpart** in opencode/codex (both are pure fetch+convert). It adds `_EXTRACT_MAX_CHARS`, an extra model call, `ZENITH_EXTRACT_MODEL`, and a "page does not contain this information" prompt contract â€” and leaks model availability into the tool path. Candidate for removal unless productized.

**Missing / wrong:**
- websearch lacks the **provider abstraction** (`exa`/`parallel`), `livecrawl`/`type` (fast/deep) params, `contextMaxCharacters`, and session-seeded provider selection that opencode ships.
- No MCP-fronted search (opencode `mcp-websearch.ts`).

**Cleanup:**
- Duplicate `_DEFAULT_MAX_CHARS`/`_DEFAULT_MAX_RESULTS` module-local defaults and excess `WEBFETCH_*`/`WEBSEARCH_*` env aliases â€” single sources of truth exist.

## What we will do

- Keep webfetch as pure fetch+convert (remove the LLM `extract` pass).
- Abstract websearch behind a provider with rich params (`numResults`, `livecrawl`, `type`, `contextMaxCharacters`) and provider selection.
- Front search optionally over MCP (opencode pattern).
- Deduplicate constants.

## What we will REMOVE
- The `extract` LLM round-trip in `webfetch.py`
- `_EXTRACT_MAX_CHARS`, `ZENITH_EXTRACT_MODEL`
- Duplicate module-local defaults and excess `WEBFETCH_*`/`WEBSEARCH_*` aliases

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| (none specific here) | â€” | â€” |

## Verification / signoff
- [x] webfetch = pure fetch+convert surface added (`fetch_page` / `FetchResult`), legacy `extract` kept for Phase 3
- [ ] websearch provider abstraction with rich params (Phase 2)
- [ ] optional MCP-fronted search (Phase 3)
- [x] constants deduplicated (single sources of truth)
- [x] ruff + pytest pass

## §9 report (Module 20 — Interface-Locked, additive Phase 1)

Additive changes, no removal (per progress.md §11):

- **`server/toolkit/tools/webfetch.py`:**
  - NEW `FetchResult` dataclass (`url`, `content_type`, `chars`, `markdown`, `truncated`).
  - NEW async `fetch_page(url, *, max_chars, timeout, user_agent) -> FetchResult` — the pure
    fetch + convert-to-Markdown surface matching opencode's `tool/webfetch.ts` (plain GET +
    HTML→Markdown, capped at `max_chars`, never raw HTML, no LLM extraction). Raises on
    transport/HTTP errors; unwraps redirects; honours `DEFAULT_USER_AGENT`.
  - `WebfetchTool.execute` refactored to call `fetch_page` for the fetch+convert portion,
    preserving the legacy LLM `extract` branch byte-for-byte in behavior (kept for Phase 3).
- **Constants deduplication (single sources of truth):**
  - `DEFAULT_WEBSEARCH_MAX_RESULTS = 8` added to `server/config/constants.py`; `websearch.py`
    now aliases `_DEFAULT_MAX_RESULTS = DEFAULT_WEBSEARCH_MAX_RESULTS` (no hardcoded literal).
  - `webfetch.py` `_DEFAULT_MAX_CHARS` already resolves from `DEFAULT_WEBFETCH_MAX_BYTES`; both
    `webfetch`/`websearch` timeouts already resolve from `DEFAULT_WEB_TIMEOUT`. `_EXTRACT_MAX_CHARS`
    and `ZENITH_EXTRACT_MODEL` are Phase-3 removals (extract round-trip).

Tests: `server/tests/test_web_tools.py` (**16 pass**: 13 existing + 3 new `TestFetchPage`
covering converted markdown, non-HTML truncation, and HTTP-error propagation). Ruff clean.

**Decision:** websearch **provider abstraction** (`exa`/`parallel`, `livecrawl`/`type`,
`contextMaxCharacters`, session-seeded selection) and optional **MCP-fronted search** are
Phase 2/3 additions (deferred) — they are not additive and would otherwise duplicate the
existing ZENITH_SEARCH_API backend; the dual constant source is already resolved. The legacy
`extract` LLM round-trip stays until its consumers adopt the pure `fetch_page` surface
(Phase 3 coordinated removal). No EventKind/transport change (G5 preserved).

## Status: Interface-Locked
