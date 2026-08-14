import { render } from 'ink-testing-library';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ScenarioRenderer } from '../src/components/Display/Scenario/ScenarioRenderer';
import { collectFixtureEvents, emitCompactionFixture } from '../src/services/transport/fixtureEmitter';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ScenarioEvent } from '../src/types/scenario';
import { consolidateCompactionEvents } from '../src/utils/compaction';
import { upsertEvent } from '../src/utils/eventUpsert';

/**
 * The /compact pipeline is fully data-driven: a single JSON fixture holds the
 * exact AI-model output (opencode-style anchored summary), a shared emitter
 * replays it, and the renderer consumes the same typed events. These tests run
 * the SAME emitter + renderer path that the production UI uses, so a passing
 * suite means /compact shows precisely what the fixture specifies.
 */

afterEach(() => {
  vi.useRealTimers();
});

describe('collectFixtureEvents', () => {
  it('maps the fixture to the exact event sequence the UI will receive', () => {
    const events = collectFixtureEvents();
    expect(events.map((e) => e.kind)).toEqual([
      'thinking',
      'context_compaction_started',
      'context_compaction_phase',
      'context_compacted',
      'context_compacted',
      'context_compacted',
      'context_compaction_phase',
      'context_compaction_phase',
      'context_compaction_ended',
    ]);
  });

  it('carries every typed metric the card consumes', () => {
    const ended = collectFixtureEvents().find((e) => e.kind === 'context_compaction_ended');
    expect(ended).toMatchObject({
      kind: 'context_compaction_ended',
      used: 43_000,
      total: 128_000,
      tokensSaved: 75_000,
      summaryChars: 28_000,
      failed: false,
    });
    const preserved = ended && ended.kind === 'context_compaction_ended' ? ended.preserved : undefined;
    expect(preserved).toMatchObject({
      requirements: 12,
      decisions: 7,
      openTasks: 4,
      findings: 3,
      artifacts: 3,
      agents: 2,
      compressedDiscussions: 9,
      redundantExchanges: 6,
      obsoleteStates: 4,
    });
    const summary = ended && ended.kind === 'context_compaction_ended' ? ended.summary : undefined;
    expect(summary).toContain('## Objective');
    expect(summary).toContain('## Important Details');
    expect(summary).toContain('## Work State');
    expect(summary).toContain('## Next Move');
    expect(summary).toContain('## Relevant Files');
  });
});

describe('emitCompactionFixture', () => {
  it('replays every fixture event then completes', async () => {
    vi.useFakeTimers();
    const received: ScenarioEvent[] = [];
    let completed = false;
    const runner = emitCompactionFixture(
      (event) => {
        received.push(event);
      },
      () => {
        completed = true;
      },
    );

    await vi.advanceTimersByTimeAsync(10_000);
    runner.abort();

    expect(completed).toBe(true);
    expect(received).toHaveLength(collectFixtureEvents().length);
    expect(received[1]).toMatchObject({ kind: 'context_compaction_started', used: 118_000, total: 128_000 });
    expect(received[received.length - 1]).toMatchObject({
      kind: 'context_compaction_ended',
      used: 43_000,
      tokensSaved: 75_000,
      failed: false,
    });
  });

  it('aborts a partially replayed fixture', async () => {
    vi.useFakeTimers();
    const received: ScenarioEvent[] = [];
    const runner = emitCompactionFixture((event) => {
      received.push(event);
    }, vi.fn());

    await vi.advanceTimersByTimeAsync(600);
    runner.abort();
    await vi.advanceTimersByTimeAsync(10_000);

    expect(received.length).toBeGreaterThan(0);
    expect(received.length).toBeLessThan(collectFixtureEvents().length);
  });
});

describe('fixture playback renders the compaction card', () => {
  it('replays through the shared upsert/consolidate/render path used by /compact', () => {
    const raw = collectFixtureEvents();
    let state: ScenarioEvent[] = [];
    raw.forEach((event, index) => {
      state = upsertEvent(state, event, index);
    });

    // Lifecycle folded into one terminal card carrying every metric.
    const flow = consolidateCompactionEvents(state);
    expect(flow?.phase).toBe('ready');
    expect(flow?.beforeTokens).toBe(118_000);
    expect(flow?.afterTokens).toBe(43_000);
    expect(flow?.totalTokens).toBe(128_000);
    expect(flow?.tokensSaved).toBe(75_000);
    expect(flow?.preserved?.requirements).toBe(12);
    expect(flow?.preserved?.compressedDiscussions).toBe(9);
    expect(flow?.summary).toContain('## Next Move');

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={state} isRunning={false} thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    const flattened = frame.replace(/\s+/g, ' ');

    // Branded card header.
    expect(frame).toContain('▣ Compaction');
    // Completion banner with the token transition + savings.
    expect(frame).toContain('✻ Context compacted (manual) · 118.0k → 43.0k tokens · saved 75.0k tokens ✻');
    // The model's structured summary renders inside the card (headings + bullets).
    expect(frame).toContain('Objective');
    expect(frame).toContain('Next Move');
    expect(flattened).toContain('single JSON fixture holds the exact AI-model compaction output');
    expect(flattened).toContain('Render the summary body with TerminalMarkdown');
    // Preserved-context metrics (truncate-end may cut the tail, so match the prefix).
    expect(frame).toContain('Preserved · 12 requirements · 7 decisions');
  });

  it('emitted events are identical whether collected or played back', async () => {
    vi.useFakeTimers();
    const collected = collectFixtureEvents();
    const played: ScenarioEvent[] = [];
    let completed = false;

    emitCompactionFixture(
      (event) => {
        played.push(event);
      },
      () => {
        completed = true;
      },
    );
    await vi.advanceTimersByTimeAsync(10_000);

    expect(completed).toBe(true);
    expect(played.map((e) => e.kind)).toEqual(collected.map((e) => e.kind));
  });
});
