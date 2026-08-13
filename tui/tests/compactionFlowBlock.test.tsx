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
  it('renders a single block for the preparing phase', () => {
    const event: ContextCompactionFlowEvent = { ...baseEvent, phase: 'preparing' };
    const { lastFrame } = render(
      <ThemeProvider>
        <CompactionFlowBlock event={event} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
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

  it('renders the ready state with success checkmark and saved tokens', () => {
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
    expect(frame).toContain('Context ready');
    expect(frame).toContain('43.0k used');
    expect(frame).toContain('saved 85.0k');
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
