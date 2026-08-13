import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { ScenarioRenderer } from '../src/components/Display/Scenario/ScenarioRenderer';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type {
  ContextCompactedEvent,
  ContextCompactionEndedEvent,
  ContextCompactionPhaseEvent,
  ContextCompactionStartedEvent,
  ScenarioEvent,
} from '../src/types/scenario';
import { consolidateCompactionEvents } from '../src/utils/compaction';

describe('consolidateCompactionEvents captures model context numbers', () => {
  it('carries beforeTokens, afterTokens and totalTokens from started/ended events', () => {
    const flow = consolidateCompactionEvents([
      {
        kind: 'context_compaction_started',
        id: 'evt_1',
        message: 'started',
        used: 118_000,
        total: 128_000,
      },
      {
        kind: 'context_compaction_ended',
        id: 'evt_2',
        message: 'finished',
        used: 43_000,
        total: 128_000,
        tokensSaved: 75_000,
        failed: false,
      },
    ]);

    expect(flow?.phase).toBe('ready');
    expect(flow?.beforeTokens).toBe(118_000);
    expect(flow?.afterTokens).toBe(43_000);
    expect(flow?.totalTokens).toBe(128_000);
    expect(flow?.tokensSaved).toBe(75_000);
  });

  it('tracks the live before→after transition from phase events', () => {
    const flow = consolidateCompactionEvents([
      {
        kind: 'context_compaction_started',
        id: 'evt_1',
        message: 'started',
        used: 118_000,
        total: 128_000,
      },
      {
        kind: 'context_compaction_phase',
        id: 'evt_2',
        phase: 'compacting',
        label: 'Compacting context',
        beforeTokens: 118_000,
        afterTokens: 43_000,
      },
    ]);

    expect(flow?.phase).toBe('compacting');
    expect(flow?.beforeTokens).toBe(118_000);
    expect(flow?.afterTokens).toBe(43_000);
    expect(flow?.totalTokens).toBe(128_000);
  });

  it('treats context_compaction_ended as terminal even after phase events', () => {
    const flow = consolidateCompactionEvents([
      {
        kind: 'context_compaction_started',
        id: 'evt_1',
        message: 'started',
        used: 118_000,
        total: 128_000,
      },
      {
        kind: 'context_compaction_phase',
        id: 'evt_2',
        phase: 'verifying',
        label: 'Verifying preserved context',
      },
      {
        kind: 'context_compaction_ended',
        id: 'evt_3',
        message: 'finished',
        used: 43_000,
        total: 128_000,
        tokensSaved: 75_000,
        failed: false,
      },
    ]);

    expect(flow?.phase).toBe('ready');
    expect(flow?.afterTokens).toBe(43_000);
    expect(flow?.tokensSaved).toBe(75_000);
  });
});

describe('ScenarioRenderer compaction consolidation', () => {
  it('renders a single compaction card for multiple compaction events', () => {
    const started: ContextCompactionStartedEvent = {
      kind: 'context_compaction_started',
      id: 'evt_1',
      message: 'started',
      used: 118_000,
      total: 128_000,
    };
    const compacted: ContextCompactedEvent = {
      kind: 'context_compacted',
      id: 'evt_2',
      message: 'Compacted bash_output: removed 30000 chars, saved ~7500 tokens — compaction',
      tool: 'bash_output',
      tokensSaved: 7_500,
    };
    const phase: ContextCompactionPhaseEvent = {
      kind: 'context_compaction_phase',
      id: 'evt_3',
      phase: 'verifying',
      label: 'Verifying preserved context',
    };
    const ended: ContextCompactionEndedEvent = {
      kind: 'context_compaction_ended',
      id: 'evt_4',
      message: 'finished',
      used: 43_000,
      total: 128_000,
      tokensSaved: 75_000,
      summaryChars: 12_000,
      failed: false,
    };

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={[started, compacted, phase, ended]} isRunning={false} thinkingCollapsed={false} />
      </ThemeProvider>,
    );

    const frame = lastFrame();
    // ended is terminal: the card collapses to one ready banner, not 4 separate rows
    expect(frame).toContain('Context compacted (manual)');
    expect(frame).not.toContain('Verifying preserved context');
    // Only one card should appear (single Context Compaction flow block)
    const cardCount = (frame.match(/Compaction/g) || []).length;
    expect(cardCount).toBeLessThanOrEqual(2); // once in the phase label + possible title
  });

  it('renders the ready state when ended event has no failure', () => {
    const started: ContextCompactionStartedEvent = {
      kind: 'context_compaction_started',
      id: 'evt_1',
      message: 'started',
      used: 118_000,
      total: 128_000,
    };
    const ended: ContextCompactionEndedEvent = {
      kind: 'context_compaction_ended',
      id: 'evt_2',
      message: 'finished',
      used: 43_000,
      total: 128_000,
      tokensSaved: 75_000,
      failed: false,
    };

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={[started, ended]} isRunning={false} thinkingCollapsed={false} />
      </ThemeProvider>,
    );

    expect(lastFrame()).toContain('Context compacted (manual)');
  });

  it('renders the ready banner when ended arrives after a non-terminal phase', () => {
    const started: ContextCompactionStartedEvent = {
      kind: 'context_compaction_started',
      id: 'evt_1',
      message: 'started',
      used: 118_000,
      total: 128_000,
    };
    const phase: ContextCompactionPhaseEvent = {
      kind: 'context_compaction_phase',
      id: 'evt_2',
      phase: 'verifying',
      label: 'Verifying preserved context',
    };
    const ended: ContextCompactionEndedEvent = {
      kind: 'context_compaction_ended',
      id: 'evt_3',
      message: 'finished',
      used: 43_000,
      total: 128_000,
      tokensSaved: 75_000,
      failed: false,
    };

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={[started, phase, ended]} isRunning={false} thinkingCollapsed={false} />
      </ThemeProvider>,
    );

    expect(lastFrame()).toContain('Context compacted (manual)');
  });

  it('renders the failed state when ended event is marked failed', () => {
    const started: ContextCompactionStartedEvent = {
      kind: 'context_compaction_started',
      id: 'evt_1',
      message: 'started',
      used: 118_000,
      total: 128_000,
    };
    const ended: ContextCompactionEndedEvent = {
      kind: 'context_compaction_ended',
      id: 'evt_2',
      message: 'finished',
      used: 118_000,
      total: 128_000,
      tokensSaved: 0,
      failed: true,
    };

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={[started, ended]} isRunning={false} thinkingCollapsed={false} />
      </ThemeProvider>,
    );

    expect(lastFrame()).toContain('Unable to safely compact context');
    expect(lastFrame()).toContain('Conversation unchanged');
  });

  it('does not render a compaction card when no compaction events present', () => {
    const events: ScenarioEvent[] = [{ kind: 'message', id: 'm1', text: 'hello' }];
    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={events} isRunning={false} thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    expect(lastFrame()).not.toContain('Compacting');
    expect(lastFrame()).not.toContain('Context ready');
  });
});
