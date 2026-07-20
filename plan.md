# Claude Code TUI: Mock-Driven Architecture & 3-Phase Implementation Plan

## Overview
This document serves as the comprehensive, granular blueprint for building a highly professional, modern, and pixel-perfect Terminal User Interface (TUI) that strictly replicates the official Anthropic **Claude Code CLI** (as seen in the reference images). 

This build will be **entirely mock-driven**, functioning as a high-fidelity prototype to demonstrate an end-to-end "happy flow." There is no backend; all data, tool executions, diffs, and delays are simulated to focus purely on delivering a stunning, True Color, keyboard-centric terminal UI using **React and Ink**.

---

## 1. Architectural Shift: From Web to Native CLI

Unlike the Claude.ai web interface (which uses sidebars and split panes), the **Claude Code CLI** operates as a continuous vertical scroll of inline events, augmented by floating, interactive modal components.

### A. Core Layout Structure
There are no permanent sidebars. The layout consists of:
1.  **The Scrolling Stream (Main View):** A history of prompts, Claude's text responses, and nested tool executions (List, Read, Update).
2.  **The Floating Input Layer:** The `> ` prompt anchored near the bottom, which dynamically spawns autocomplete menus or plugin modals directly beneath it.
3.  **The Fixed Footers:** Loading spinners (`* Searching...`) and mode indicators (`▸▸ auto-accept edits on`) rendered at the absolute bottom.

### B. Component Architecture
To achieve pixel-perfection, we will build specialized components:
*   `<WelcomeHeader>`: Renders the orange border box, space invader mascot, and metadata.
*   `<TreeLog>`: Renders tool executions (e.g., `● Update(file.php)`) with proper `└` indentation and nested gray text.
*   `<WordDiffViewer>`: Renders code diffs featuring both full-line red/green backgrounds and inner word-level brighter background highlights.
*   `<DropdownMenu>`: Renders the 2-column `/` command autocomplete list.
*   `<PluginModal>`: Renders the tabbed interface (`Discover | Installed`) with inverted ANSI colors for the active tab and a nested search box.

---

## 2. The Mock Engine & State Management

### A. Data Shapes
```typescript
// Represents an entry in the continuous CLI stream
type LogEntry = 
  | { type: 'user_prompt', content: string }
  | { type: 'claude_text', content: string }
  | { 
      type: 'tool_execution', 
      toolName: string, 
      args: string, 
      resultText: string, 
      diff?: { oldCode: string, newCode: string } 
    };

type AppState = {
  history: LogEntry[];
  currentInput: string;
  activeOverlay: 'none' | 'autocomplete' | 'plugin_modal';
  footerStatus: string;
};
```

### B. The Target "Happy Flow" Scenario
The dummy app will simulate a specific, complex interaction derived directly from the reference images:
1.  **Boot:** Shows the orange Mascot Welcome box and `> ` prompt.
2.  **Autocomplete:** User types `/`, the dropdown menu appears perfectly formatted.
3.  **Plugin Modal:** User types `/plugin`, the modal pops up showing the tabbed interface.
4.  **Simulated Task:** User hits Enter on a mocked task (e.g., fixing a PHP file). The UI prints Claude's conversational text (`● Ich zahle dir...`), followed by a tool execution (`● Update(routes/api.php)`), and finally streams a pixel-perfect red/green diff viewer showing the exact word changes.

---

## 3. The 3-Phase Execution Plan

The entire project is consolidated into three distinct phases for rapid, focused execution.

### Phase 1: Foundation & Core Primitives
*   **Goal:** Initialize the React/Ink environment and build the foundational visual language (colors, borders, fonts).
*   **Tasks:**
    *   Initialize Node.js + TypeScript project with `ink`, `ink-text-input`, and `chalk`.
    *   Define the exact True Color hex theme (deep charcoal bg, orange/blue accents, specific gray tones).
    *   Build primitive components: `<RoundedBox>` (supporting top-border title interruptions) and the ASCII `<Mascot>`.
    *   Build the base `<InputPrompt>` (`> `) and the fixed bottom `<StatusFooter>`.

### Phase 2: Complex Pixel-Perfect Components
*   **Goal:** Construct the intricate UI widgets seen in the reference images without hooking them into logic yet.
*   **Tasks:**
    *   Build the `<TreeLog>` component for rendering nested tool outputs (`●`, `└`).
    *   Build the highly complex `<WordDiffViewer>` (calculating line-level and word-level ANSI background colors).
    *   Build the floating `<PluginModal>` with inverted tab colors and interactive selections.
    *   Build the `<AutocompleteDropdown>` with strict 2-column alignment.

### Phase 3: The End-to-End Mock Engine & Happy Flow
*   **Goal:** Wire the components together into a fully interactive, simulated application.
*   **Tasks:**
    *   Implement global keyboard state (managing focus between the prompt, the autocomplete menu, and the plugin modal tabs).
    *   Build the `MockEngine` to simulate typing delays, loading spinners (`* Searching... (27s)`), and sequential event streaming.
    *   Assemble the final "Happy Flow": User types -> fake loading spinner -> fake tool execution log -> fake word-level diff rendering -> completion.
