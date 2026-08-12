# 11 - TUI Pixel-Perfect UI/UX Audit & Refinement Specification

## Objective
Elevate the `zenith-frontend-tui` user interface to achieve pixel-perfect, sleek, compact design parity with the reference screenshots (`Image 1`, `Image 2`, `Image 3`, `Image 4`), strictly adhering to user design preferences:
- Modern, professional, and elegant aesthetic
- Compact layout with minimal padding/margins
- Sleek, high-contrast typography and subtle colors
- Minimalistic look with fewer box borders and decorative lines

---

## UI/UX Inventory & Requirements Breakdown

### 1. Processing Wave Label (ABOVE Input Box) & Input Field Simplification
- **Above-Input Processing Wave Label**:
  - Position a dedicated status/processing banner directly **ABOVE** the command input box.
  - When the assistant is processing or executing tools, display a sleek, animated colored wave indicator (e.g., smooth sine-wave character sequence `░▒▓█▓▒░` or `⠋⠙⠹⠸⠼⠴⠦⠧` rendered in a cyan-to-emerald gradient wave) alongside the active action text (e.g., `Processing...`, `Executing plan...`).
  - Automatically hide when idle or show a subtle status mode indicator.
- **Input Box Minimization**:
  - Remove all changing/rotating placeholder text effects (`PLACEHOLDERS` interval loop).
  - Use a clean, static, minimal placeholder string: `Ask anything...`.
  - Remove any internal loading indicators, end-of-input spinners, or busy icons from inside the input box frame.
  - Render prompt prefix `❯` in vibrant cyan/emerald when focused, muted when blurred.

### 2. File Diff & Code Edits Display (`Image 1` & `Image 2`)
- **File Editor Header Badge**:
  - Format file edit cards with an action badge: `* editor(D:\vdo\code\zenith-frontend-tui\file.py)` using cyan star `*` and full normalized file path.
- **Diff Line Metrics Pill**:
  - Display line stats subheader: `L +27 lines (new) | python` or `L +9 -14 lines | python` featuring green `+` additions and red `-` deletions.
- **Line-Level Diff Highlight**:
  - Insertion lines (`+`): Full-width soft green background strip (`#112B1C`), line number column with `1 +`, `2 +` symbols.
  - Deletion lines (`-`): Full-width soft red background strip (`#2B1111`), line number column with `3 -`, `6 -` symbols.
  - Support multi-chunk diff rendering inside a single editor view with sub-editor headers (`L +6 -11 lines | python`).

### 3. Tool Execution & Terminal Shell Cards (`Image 1` & `Image 4`)
- **Shell Command Formatting**:
  - Display `$ command` inside a dark terminal frame with syntax-highlighted arguments.
  - Indent standard output and wrap long outputs inside an expandable container with a `Click to expand` text button.
- **Search & Grep Cards**:
  - Display query badges like `* Grep "PRN|Unable..." in server (2 matches)` featuring result count metrics.
- **Tool Trace Lines**:
  - Format file reads as `→ Read path/to/file.py` with golden execution duration badges (e.g., `Thought: 1.5s`).

### 4. Thinking & Reasoning Blocks (`Image 1`, `Image 2`, `Image 4`)
- **Collapsed Thought View**:
  - Format collapsed thought as single line: `▶ Thinking: <italic preview text...>` with dim cyan arrow and muted preview snippet.
- **Expanded Thought Header**:
  - Render gold/amber title badge: `Thought: 1.5s` or `Thought (3 steps)` when expanded or completed.
- **Nested Step List**:
  - Display numbered or bulleted reasoning steps with clean indentation and active step indicators.

### 5. Composer Footer & Status Bar (`Image 1` & `Image 2`)
- **Model Pill & Token Usage**:
  - Format left section with provider/model badge: `ClinePass: Laguna S 2.1 (medium)` and token usage badge `(93,591)` in dark gray container.
- **Git Repository & Diff Metrics**:
  - Display branch and workspace metrics: `zenith-frontend-tui (branch) | 30 files +0 -942` with green additions and red deletions.
- **Auto-Approve Indicator**:
  - Render amber auto-approve mode status: `>> Auto-approve all enabled (Shift+Tab)`.
- **Mode Switcher Pill**:
  - Right-align mode toggle: `○ Plan • Act (Tab)` highlighting active selection (`Act` in bright cyan, `Plan` muted with dot).

### 6. Markdown Typography & Content Formatting (`Image 3` & `Image 4`)
- **Section Heading Palette**:
  - Render major section headings (`Objective`, `Important Details`, `Work State`, `Completed`) in purple/magenta bold text without heavy horizontal divider line spam.
- **High-Contrast Code Spans**:
  - Style inline code with amber warning tint on dark modal background.
- **Monospace Tables**:
  - Format markdown tables with clean border lines (`┌─`, `├─`, `└─`) and column alignment.

### 7. Additional Component Polish
- **User Message Cards**: Clean compact layout with `> user prompt` styling.
- **Success & Warning Cards**: Subtle border highlights without intrusive box frames.
- **Scroll Indicators**: Minimal right-edge scrollbar ticks when content overflows stdout bounds.

---

## Codebase Target Map

| Component | Target File | Key Modifications |
| :--- | :--- | :--- |
| **Processing Wave & Input** | [CommandInput.tsx](file:///d:/vdo/code/zenith-frontend-tui/tui/src/components/Input/CommandInput.tsx) | Position wave label above input, static placeholder `Ask anything...`, remove loading states in input |
| **Wave Animation Component** | [ProcessingWaveBar.tsx](file:///d:/vdo/code/zenith-frontend-tui/tui/src/components/Input/ProcessingWaveBar.tsx) | [NEW] Animated gradient wave indicator for running/processing state |
| **File Diffs & Markdown** | [TerminalMarkdown.tsx](file:///d:/vdo/code/zenith-frontend-tui/tui/src/components/Display/Scenario/TerminalMarkdown.tsx) | `* editor(path)` header, `L +X -Y` stats, `+`/`-` line gutters, magenta headers |
| **Tool Execution Cards** | [ToolStepCard.tsx](file:///d:/vdo/code/zenith-frontend-tui/tui/src/components/Display/Scenario/ToolStepCard.tsx) | Terminal `$ command` frame, `Click to expand` log output, search match counts |
| **Thinking Blocks** | [ThinkingBlock.tsx](file:///d:/vdo/code/zenith-frontend-tui/tui/src/components/Display/Scenario/ThinkingBlock.tsx) | `▶ Thinking: <preview>` collapsed view, gold `Thought: Xs` header |
| **Composer Status Footer** | [ComposerFooter.tsx](file:///d:/vdo/code/zenith-frontend-tui/tui/src/components/Input/ComposerFooter.tsx) | Token pill `(93,591)`, Git diff `+0 -942`, auto-approve badge, `Plan • Act (Tab)` pill |
| **Theme & Tokens** | [theme.ts](file:///d:/vdo/code/zenith-frontend-tui/tui/src/theme/theme.ts) | Color tokens for wave animation, thought gold, diff line strips, mode pills |
