---
name: frontend_ux_audit
description: Expert audit agent for terminal frontend architecture, UI/UX polish, static data externalization, component modularization, and scenario engine decoupling.
---

# Frontend Architecture & UX Audit Agent Skill

This skill defines the operational standards, evaluation criteria, and architectural guidelines for performing continuous frontend audits and code transformations on Zenith TUI.

## Core Responsibilities

1. **UI & UX Polish Evaluation**:
   - Audit visual hierarchy, terminal panel borders, status indicators, spacing, typography, and contrast.
   - Enforce zero-emoji directives across all terminal components (use clean CLI text badges `[CREATE]`, `[MODIFY]`, `[TEST]`, `[BUILD]`, `[PLAN]`, `[COMMAND PROMPT]`, `[FILE]`, `[DIR]`).
   - Validate keyboard-first interactions, touchpad two-finger viewport scrolling, and slash command palette behavior.

2. **Component Architecture & Quality Audit**:
   - Verify single responsibility, modularity, and clean component composition.
   - Eliminate duplicated UI logic and hardcoded styling overrides.

3. **Static Data Externalization**:
   - Enforce strict separation of UI layout from user-facing text strings.
   - Ensure all labels, titles, descriptions, command definitions, shortcuts, status badges, and help text are served via `StaticContentRepository`.

4. **Data Abstraction & Scenario Engine Decoupling**:
   - Enforce the 4-tier data architecture:
     ```
     UI Components (Ink) → View Models / Presenters → Scenario Service → Repositories → Data Sources
     ```
   - Ensure scenario execution is 100% data-driven. UI components consume domain events without knowing whether data comes from static mocks, local repositories, or live AI streaming endpoints.

5. **Simulation Test Strategy**:
   - Isolate test scenarios into domain packages (`scenarios/build/`, `scenarios/plan/`, `scenarios/error/`).
   - Validate end-to-end user workflows using Vitest & Ink Testing Library.
