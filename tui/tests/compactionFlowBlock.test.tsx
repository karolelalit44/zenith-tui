import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { CompactionFlowBlock } from '../src/components/Display/Scenario/CompactionFlowBlock';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ContextCompactionFlowEvent } from '../src/types/scenario';

const baseEvent: ContextCompactionFlowEvent = {
  kind: 'context_compaction_flow',
  id: 'evt_1',
  phase: 'preparing',
};

describe('CompactionFlowBlock', () => {
  it('renders a branded card for the preparing phase', () => {
    const event: ContextCompactionFlowEvent = { ...baseEvent, phase: 'preparing' };
    const { lastFrame } = render(
      <ThemeProvider>
        <CompactionFlowBlock event={event} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('Compaction');
    expect(frame).toContain('Preparing conversation context');
  });

  it('shows before/after token transition in compacting phase', () => {
    const event: ContextCompactionFlowEvent = {
      ...baseEvent,
      phase: 'compacting',
      beforeTokens: 128_000,
      afterTokens: 43_000,
      notes: ['removed old bash output', 'trimmed tool traces'],
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <CompactionFlowBlock event={event} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('128.0k');
    expect(frame).toContain('43.0k');
    expect(frame).toContain('→');
    expect(frame).toContain('removed old bash output');
    expect(frame).toContain('trimmed tool traces');
  });

  it('renders the ready state as a compacted summary banner with tokens', () => {
    const event: ContextCompactionFlowEvent = {
      ...baseEvent,
      phase: 'ready',
      beforeTokens: 128_000,
      afterTokens: 43_000,
      tokensSaved: 85_000,
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <CompactionFlowBlock event={event} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('Context compacted (manual)');
    expect(frame).toContain('128.0k → 43.0k tokens');
    expect(frame).toContain('saved 85.0k');
  });

  it('labels the banner with the structured automatic trigger', () => {
    const event: ContextCompactionFlowEvent = {
      ...baseEvent,
      phase: 'ready',
      trigger: 'automatic',
      beforeTokens: 128_000,
      afterTokens: 43_000,
      tokensSaved: 85_000,
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <CompactionFlowBlock event={event} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('Context compacted (automatic)');
  });

  it('labels the banner with the structured manual trigger', () => {
    const event: ContextCompactionFlowEvent = {
      ...baseEvent,
      phase: 'ready',
      trigger: 'manual',
      beforeTokens: 128_000,
      afterTokens: 43_000,
      tokensSaved: 85_000,
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <CompactionFlowBlock event={event} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('Context compacted (manual)');
  });

  it('renders the structured summary and preserved breakdown when ready', () => {
    const event: ContextCompactionFlowEvent = {
      ...baseEvent,
      phase: 'ready',
      beforeTokens: 128_000,
      afterTokens: 43_000,
      tokensSaved: 85_000,
      summary:
        '## Objective\n- Make the zenith TUI /compact turn fully data-driven: a single JSON fixture holds the exact model output.\n\n## Next Move\n1. Render the summary body with TerminalMarkdown.\n\n## Relevant Files\n- `tui/src/fixtures/compaction-output.json` — canonical output.',
      preserved: { requirements: 12, decisions: 7, openTasks: 4, agents: 2 },
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <CompactionFlowBlock event={event} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    const flattened = frame.replace(/\s+/g, ' ');
    // Headings render without the markdown prefix.
    expect(frame).toContain('Objective');
    expect(frame).toContain('Next Move');
    expect(frame).toContain('Relevant Files');
    // Bullets and numbered steps render as structured list rows.
    expect(flattened).toContain(
      'Make the zenith TUI /compact turn fully data-driven: a single JSON fixture holds the exact model output.',
    );
    expect(flattened).toContain('Render the summary body with TerminalMarkdown.');
    expect(frame).toContain('Preserved');
    expect(frame).toContain('12 requirements');
    expect(frame).toContain('7 decisions');
    expect(frame).toContain('2 agents');
  });

  it('renders the failure state with conversation-unchanged message', () => {
    const event: ContextCompactionFlowEvent = {
      ...baseEvent,
      phase: 'failed',
      failed: true,
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <CompactionFlowBlock event={event} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('Unable to safely compact context');
    expect(frame).toContain('Conversation unchanged');
  });

  it('caps notes at 3 entries', () => {
    const event: ContextCompactionFlowEvent = {
      ...baseEvent,
      phase: 'compacting',
      notes: ['a', 'b', 'c', 'd', 'e'],
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <CompactionFlowBlock event={event} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('↳ a');
    expect(frame).not.toContain('↳ e');
  });
});
