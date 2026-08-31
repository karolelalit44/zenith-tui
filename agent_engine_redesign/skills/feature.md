# Skills

## Overview

How skills (SKILL.md packages of instructions) are discovered, parsed, and presented to the model.

### How opencode does it

- Roots scanned (`skill/index.ts:21-25`): `.claude/skills/**/SKILL.md`, `.agents/skills/**/SKILL.md`, `{skill,skills}/**/SKILL.md` config dirs, explicit config `skills.paths`, plus remote **URL/git pull** (`config.skills.urls` â†’ `Discovery.pull`), and a built-in `customize-opencode` skill.
- Discovery scope: global + project-ancestor + config dirs + remote URLs, with caching.
- **Real YAML frontmatter** via `ConfigMarkdown.parse`, validated through `isSkillFrontmatter` (requires `name`, optional `description`). Duplicate names warned; last-wins.
- Injection: model gets `<available_skills>` block (name/description/**location**), not full bodies (`Skill.fmt`). Full content loaded on demand by the **`skill` tool** (`tool/skill.ts`), which reads SKILL.md + a sampled file list via ripgrep.
- Permissions: `available(agent)` filters by permission system.

### How codex does it

- Skills are plugin/extension based (`codex_skills`, `codex_skills_extension`), `HostSkillsLoadInput.from(config, skill_roots, config_layer_stack)`.
- Explicit invocation (`emit_explicit_skill_invocations`) and implicit detection (`detect_implicit_skill_invocation`) by matching command/text against skill metadata.
- Rich telemetry (`codex.skill.injected` counters) and contributance via `skill_invocation_contributors()`.
- Scopes: `User | Repo | System | Admin`.

### What zenith has today

- `server/skills/loader.py` (105): `SkillLoader.find_skills()` scans `SKILL_ROOTS = ("skills", "agents/skills", ".zenith/skills", ".agent/skills")` (`constants.py:456`), skipping dot-prefixed parts.
- **No real YAML frontmatter parse** â€” only regex `_extract_yaml_field("^field:\\s*(.+)$")` for `description` (not `name`), falling back to first heading `^#{1,2}`. **No `name` read at all.**
- `get_skill_prompt()` inlines **every** skill's summary (first ~250 chars) directly into the prompt, capped `MAX_SKILLS_IN_PROMPT = 20`. **It is the injection itself, not a tool.**
- Budget constants to compensate for inlining: `SKILLS_BUDGET_RATIO`, `SKILLS_MAX_CHARS`.

### What is correct

- Scanning multiple roots + skipping hidden dirs mirrors opencode.

### What is wrong / over-engineered / incorrect / missing

**Over-engineered / incorrect:**
- `_summarize_skill` (`loader.py:23-52`) hand-rolls a fragile regex YAML/heading/`---` splitter that **cannot read `name`**, mis-treats documents lacking frontmatter, and fakes descriptions from headings. This reinvents opencode's `ConfigMarkdown` badly.
- **Inlining skill bodies/summaries into the system prompt every turn** is the wrong model. opencode injects only `<available_skills>` (name+description) and loads full content on demand via a `skill` tool. Zenith's `SKILLS_BUDGET_RATIO`/`SKILLS_MAX_CHARS` exist only to cap its own broken inlining.

**Missing:**
- Skill `name` frontmatter â†’ skills keyed by dir only; no duplicate detection; no explicit `skill` tool invocation; no permission filtering; no remote pull; no built-in skill; no telemetry.

## What we will do

- Parse real YAML frontmatter (`name` + `description`) via a proper YAML parser.
- Inject only an `<available_skills>` index (name/description/location).
- Add a `skill` tool that loads a SKILL.md body on demand.
- Add permission filtering (subagent permissions control skill availability).

## What we will REMOVE
- `_summarize_skill` regex frontmatter handling and the `---` body-partition logic
- Inline-summaries-in-prompt model and `SKILLS_BUDGET_RATIO`/`SKILLS_MAX_CHARS`
- `MAX_SKILLS_IN_PROMPT` cap (replaced by on-demand tool)

## Regex audit
| Regex | opencode/codex uses it? | Action |
|---|---|---|
| `_extract_yaml_field` `^field:\s*(.+)$` | No (real YAML frontmatter) | Remove |
| `^#{1,2}\s+` first-heading-as-description | No | Remove |

## Verification / signoff
- [ ] Real YAML frontmatter (name+description)
- [ ] `<available_skills>` index only, on-demand skill tool
- [ ] Permission-gated skill availability
- [ ] ruff + pytest + runtime smoke pass

## Status: Pending
