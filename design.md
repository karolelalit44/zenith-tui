# Claude Code TUI: Hyper-Detailed Pixel-Perfect Design Specification

This document contains a forensic, character-by-character analysis of the provided Claude Code reference images. To achieve a true "pixel-perfect" clone, we must replicate the exact box-drawing characters, alignment, word-level diff highlighting, and ANSI color applications.

---

## 1. Anatomy of the UI Elements

### A. The "Welcome & Auth" Screen (Image 1)
*   **The Banner Box:** 
    *   Uses rounded corners: `╭`, `╮`, `╰`, `╯`.
    *   Border color: Muted Gray.
    *   Padding: 1 horizontal space inside the box.
    *   Content: `* Welcome to Claude Code research preview!`
    *   Colors: The `*` is a vibrant orange. The text is pure white.
*   **The ASCII Logo:**
    *   "CLAUDE CODE" is rendered in a massive 3D/Isometric block font.
    *   Color: A solid peach/orange hex.
    *   Spacing: Exactly 1 empty line above and below the logo.
*   **The Security Notes List:**
    *   Header: `Security notes:` (Bold, White).
    *   List Items: `1. `, `2. ` etc. The number and the dot are dark gray. The title next to it (e.g., `Claude Code is currently in research preview`) is White.
    *   Description body: **Indented exactly 3 spaces** so it aligns perfectly under the title, not under the number. The text is dark gray.
    *   Hyperlinks: Rendered with an underline ANSI escape code.
*   **Action Prompt:** `Press Enter to continue...`
    *   "Press" and "to continue..." are a bright blue/indigo.
    *   "Enter" is bold white.

### B. The Main Interface & Mascot Header (Image 2)
*   **The Header Box:**
    *   Border: Orange (`#E57339`).
    *   Top Border Interruption: The top line is broken by the title `╭─ Claude Code v2.0.42 ─...`.
    *   **The Mascot:** An 8-bit space invader built from Unicode block characters (e.g., `█`, `▄`, `▀`), 7 characters wide. In Image 2, it is orange. In Image 5, it is light blue.
    *   **Metadata Line:** `Sonnet 4.5 · Claude Max` (Note the use of the middle dot `·`, NOT a standard bullet or hyphen). The text is gray.
    *   **Path Line:** The current working directory is displayed below the metadata in dark gray.
    *   **Vertical Divider:** A single gray vertical line `│` separates the left profile section from the right "Tips" section.
    *   **Right Section:** "Tips for getting started" (Orange header). Body text is white.

### C. The Command Prompt & Dropdown (Image 2)
*   **The Prompt:** `> /`
    *   `>` is dark gray.
    *   The user's text is white.
    *   The cursor is a blinking solid block `█`.
*   **The Dropdown Anchor:** Exactly one line below the prompt, a full-width horizontal gray line `───` spans the terminal.
*   **The Autocomplete List:**
    *   Strict 2-column grid layout.
    *   Left Column (Command): `/add-dir` (White text).
    *   Right Column (Description): `Add a new working directory` (Blue/Gray text).
    *   The active/hovered row has a subtle background highlight.

### D. The Action Stream & Inline Diff Viewer (Images 3 & 4)
This is the most complex component. Claude Code does not use chat bubbles; it uses a tree-based stream.

*   **Message Types & Bullets:**
    *   **Claude Conversational Text:** Prefixed with a gray bullet `●`. Text is white. File names mentioned in the text (e.g., `StringRankedSearchTests.swift`) are highlighted in clickable light blue.
    *   **Tool Executions:** Prefixed with a **Green bullet** `●`.
    *   Tool Name (e.g., `List`, `Read`, `Update`) is **Bold White**.
    *   Arguments are in parentheses in gray: `(Modules/Tests)`.
*   **Nested Results:**
    *   Indented using the `└` (Box Drawings Light Up and Right) character in gray.
    *   Example: `└ Read 85 lines (ctrl+r to expand)`
    *   The numbers (`85`) are bold white, the rest is gray. The shortcut `(ctrl+r...)` is darker gray.
*   **The Diff Engine (Pixel-Perfect Spec):**
    *   **Structure:**
        *   Line number column: Fixed width, right-aligned, gray text.
        *   Sign column: `+` (green), `-` (red), or empty.
        *   Code column.
    *   **Word-Level Highlighting (Crucial Detail found in Image 3 & 4):**
        *   Removed line: Entire line background is dark red. The exact removed text (e.g., `$thumbPath = __DIR__`) has a *brighter* red background.
        *   Added line: Entire line background is dark green. The exact added text (e.g., `$thumbPath = '/sites...') has a *brighter* green background.
        *   This requires a robust diffing algorithm (like `diff-match-patch`) running at the word/character level inside the TUI.

### E. Interactive Modals & Plugins (Image 5)
*   **The Modal Box:** Appears directly below the `> /plugin` prompt. Standard rounded gray borders.
*   **The Tab Bar:**
    *   `Discover` | `Installed` | `Marketplaces` | `Errors`
    *   The Active Tab (Discover) uses **ANSI Inverted Colors**: Light Blue background with Black text.
    *   Inactive tabs are white text on standard background.
    *   Right-aligned shortcut hint: `(tab to cycle)` in gray.
*   **The Search Box:**
    *   A nested rounded box `╭─╮` inside the modal.
    *   Contains the magnifying glass Unicode character `⌕ Search...`.
*   **The Selectable List:**
    *   Selection Cursor: `> o` (Active) vs `  o` (Inactive).
    *   Title (`context7`) is White.
    *   Metadata tags (`[Community Managed]`) and stats are Gray.
    *   Separators between metadata are middle dots `·`.

### F. Status Bars & Spinners
*   **Loading Footer:**
    *   Located directly above the input box.
    *   `* Searching... (27s · ⌃ 425 tokens · esc to interrupt)`
    *   The `*` is an orange spinner. `Searching...` is orange.
    *   The stats are gray. The `⌃` icon is used to denote tokens.
*   **Mode Footer:**
    *   Located at the absolute bottom of the terminal window.
    *   `▸▸ auto-accept edits on (shift+tab to cycle)`
    *   The arrows `▸▸` and the mode name are bright Purple. The shortcut hint is dark gray.

---

## 2. Technical Translation (React/Ink Primitives)

To achieve this exact fidelity, our component library must include:

1.  **`<IconMascot>`:** A pre-rendered 7x4 ASCII art component supporting color props.
2.  **`<TreeLog>`:** A component that takes `{ action, args, result, type: 'success'|'info' }` and automatically renders the `●`, bolding, and the `└` indentation tree.
3.  **`<WordDiff>`:** The most complex component. Must accept `{ oldStr, newStr }`, compute the Levenshtein/Diff match, and render standard line backgrounds with inner word-level ANSI background highlights.
4.  **`<Tabs>`:** A Flex row that accepts an array of strings and an `activeIndex`, rendering the active index with `chalk.bgBlue.black`.
5.  **`<BottomBar>`:** A fixed `position="absolute"` component anchored to the bottom row of the terminal for the Purple `▸▸` status.
