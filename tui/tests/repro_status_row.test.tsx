import { readFileSync, writeFileSync } from 'node:fs';
import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { ScenarioRenderer } from '../src/components/Display/Scenario/ScenarioRenderer';
import { AnimationProvider } from '../src/context/AnimationContext';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ScenarioEvent } from '../src/types/scenario';
import { mapRawEvent } from '../src/services/transport/rawEventMapper';

const makeSuccess = (): ScenarioEvent => ({
  kind: 'success',
  id: 'evt_success_real',
  message: 'Request processed successfully',
  iterations: 8,
  elapsedMs: 87516,
  tokenInfo: {
    used: 51944,
    remaining: 76056,
    total: 128000,
    percent: 0.406,
    estimated: false,
  },
});

const makeEvents = (): ScenarioEvent[] => [
  {
    kind: 'tool_step',
    id: 'glob1',
    tool: 'glob',
    params: { pattern: '*' },
    success: true,
    output: '.env\n.env.example\n.gitignore\n.keys\n... 13 more lines',
    error: '',
    metadata: {},
    pending: false,
  },
  {
    kind: 'tool_step',
    id: 'read1',
    tool: 'file_read',
    params: { path: 'task.md' },
    success: true,
    output: '# Architectural Analysis',
    error: '',
    metadata: {},
    pending: false,
  },
  makeSuccess(),
];

describe('repro: completed response status row', () => {
  it('shows token usage and duration after completion (historical)', () => {
    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={makeEvents()} isRunning={false} isHistorical thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    writeFileSync('repro_frames.txt', `=== HISTORICAL ===\n${frame}\n\n=== LIVE ===\n`, { encoding: 'utf-8' });
    expect(frame).toContain('8 iters');
    expect(frame).toContain('minutes');
    expect(frame).toContain('tokens');
  });

  it('shows live row during generation (no success event yet)', () => {
    const partial = makeEvents().filter((e) => e.kind !== 'success');
    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={partial} isRunning thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    writeFileSync('repro_frames.txt', frame, { encoding: 'utf-8', flag: 'a' });
    expect(frame).toContain('tokens');
  });

  it('shows the running duration on the live status row (elapsedMs:0 must not freeze the timer)', async () => {
    const partial = makeEvents().filter((e) => e.kind !== 'success');
    const { lastFrame, unmount } = render(
      <AnimationProvider>
        <ThemeProvider>
          <ScenarioRenderer events={partial} isRunning thinkingCollapsed={false} />
        </ThemeProvider>
      </AnimationProvider>,
    );
    // tick advances every 100ms; duration appears once tick >= 10 (>= 1s).
    const start = Date.now();
    let frame = lastFrame();
    while (!/\d+ s/.test(frame) && Date.now() - start < 5000) {
      await new Promise((r) => setTimeout(r, 100));
      frame = lastFrame();
    }
    writeFileSync('repro_frames.txt', `\n=== LIVE DURATION ===\n${frame}\n`, {
      encoding: 'utf-8',
      flag: 'a',
    });
    expect(frame).toMatch(/\d+ s/);
    expect(frame).toContain('tokens');
    unmount();
  });

  it('shows row with estimated tokenInfo (real backend shape)', () => {
    const success: ScenarioEvent = {
      kind: 'success',
      id: 'evt_success_real2',
      message: 'Request processed successfully',
      iterations: 1,
      elapsedMs: 184950,
      tokenInfo: { used: 1743, remaining: 126257, total: 128000, percent: 0.014, estimated: true },
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer
          events={[...makeEvents().filter((e) => e.kind !== 'success'), success]}
          isRunning={false}
          isHistorical
          thinkingCollapsed={false}
        />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    writeFileSync('repro_frames.txt', `\n=== ESTIMATED ===\n${frame}\n`, { encoding: 'utf-8', flag: 'a' });
    expect(frame).toContain('tokens');
  });

  it('shows status row for pure text turn with thinking, message, and success', () => {
    const textEvents: ScenarioEvent[] = [
      {
        kind: 'thinking',
        id: 'think_1',
        thoughts: ['The user is asking about tech stack.'],
        duration: 2000,
        partial: false,
      },
      {
        kind: 'message',
        id: 'msg_1',
        text: 'The tech stack includes React, Ink, and TypeScript.',
        partial: false,
      },
      {
        kind: 'success',
        id: 'evt_success_pure_text',
        message: 'Request processed successfully',
        iterations: 1,
        elapsedMs: 2500,
        tokenInfo: {
          used: 12300,
          remaining: 115700,
          total: 128000,
          percent: 0.096,
          estimated: false,
        },
      },
    ];

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={textEvents} isRunning={false} isHistorical thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    console.log(`PURE_TEXT_FRAME>>>\n${frame}\n<<<PURE_TEXT_FRAME`);
    expect(frame).toContain('1 iter');
    expect(frame).toContain('2 s');
    expect(frame).toContain('12.3k tokens');
  });

  it('shows status row when success event has elapsedMs: 0 and tokenInfo with runTotal but used: 0', () => {
    const textEvents: ScenarioEvent[] = [
      {
        kind: 'thinking',
        id: 'think_1',
        thoughts: ['Analyzing...'],
        duration: 2000,
        partial: false,
      },
      {
        kind: 'message',
        id: 'msg_1',
        text: 'Here is the answer.',
        partial: false,
      },
      {
        kind: 'success',
        id: 'evt_success_zero_elapsed',
        message: 'Completed',
        iterations: 0,
        elapsedMs: 0,
        tokenInfo: {
          used: 0,
          runTotal: 12300,
          remaining: 128000,
          total: 128000,
          percent: 0,
          estimated: false,
        },
      },
    ];

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={textEvents} isRunning={false} isHistorical thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    console.log(`ZERO_ELAPSED_FRAME>>>\n${frame}\n<<<ZERO_ELAPSED_FRAME`);
    expect(frame).toContain('iter');
    expect(frame).toContain('tokens');
  });

  it('renders status row for exact openrouter session cf60e0db', () => {
    const sessionEvents: ScenarioEvent[] = [
      {
        kind: 'tool_step',
        id: 'evt_glob_1',
        tool: 'glob',
        params: { pattern: '**/SCHOOL_MANAGEMENT_SYSTEM_PRD.md' },
        success: true,
        output: 'SCHOOL_MANAGEMENT_SYSTEM_PRD.md',
        error: '',
        metadata: {},
        pending: false,
      },
      {
        kind: 'tool_step',
        id: 'evt_glob_2',
        tool: 'glob',
        params: { pattern: '**/todo.md' },
        success: true,
        output: 'todo.md',
        error: '',
        metadata: {},
        pending: false,
      },
      {
        kind: 'message',
        id: 'evt_msg_1',
        text: 'Let me read the rest of both files to complete the comparison.',
        partial: false,
      },
      {
        kind: 'thinking',
        id: 'evt_think_1',
        thoughts: ['Now I have a complete picture of both files.'],
        duration: 24000,
        partial: false,
      },
      {
        kind: 'message',
        id: 'evt_msg_final',
        text: '## Verification Summary\n\nAll tasks covered.\n\nWould you like me to update the todo.md to address these gaps?',
        partial: false,
      },
      {
        kind: 'turn_manifest',
        id: 'evt_manifest_1',
        created: [],
        modified: [],
        remaining: [],
        completed: true,
        stalled: false,
        files: [],
      },
      {
        kind: 'session_summarized',
        id: 'evt_summarized_1',
        summary: 'All tasks covered.',
        findings: [],
        runState: {
          status: 'completed',
          final: { kind: 'success', message: 'Request processed successfully' },
        },
      },
      {
        kind: 'success',
        id: 'evt_success_1',
        message: 'Request processed successfully',
        iterations: 6,
        elapsedMs: 62821,
        tokenInfo: {
          used: 17001,
          remaining: 110999,
          total: 128000,
          percent: 0.133,
          runTotal: 64758,
          estimated: false,
        },
      },
    ];

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={sessionEvents} isRunning={false} isHistorical thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    console.log(`CF60E0DB_FRAME>>>\n${frame}\n<<<CF60E0DB_FRAME`);
    expect(frame).toContain('6 iters');
    expect(frame).toContain('1.0 minutes');
    expect(frame).toContain('17.0k tokens');
  });

  it.skip('renders exact cf60e0db session loaded from raw jsonl file (local-only: requires ~/.zenith session file)', () => {
    // This test reads a session file that only exists on the author's machine.
    // To run it locally: ensure the JSONL file at the path below is present,
    // then change `it.skip` to `it`.
    const sessionPath =
      'C:/Users/Lenovo/.zenith/projects/D--vdo-code-zenith-frontend-tui/cf60e0db-ce83-4ae1-a370-002db95f0ceb.jsonl';
    const content = readFileSync(sessionPath, 'utf-8');
    const lines = content.trim().split('\n');
    const events: ScenarioEvent[] = [];

    for (const line of lines) {
      const parsed = JSON.parse(line);
      if (parsed.t === 'sync') {
        const mapped = mapRawEvent(parsed.event_type, parsed.event_data, parsed.id || `seq_${parsed.sequence}`);
        events.push(mapped);
      }
    }

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer
          events={events}
          isRunning={false}
          isHistorical={true}
          thinkingCollapsed={true}
          calmMode={true}
        />
      </ThemeProvider>,
    );

    const frame = lastFrame();
    console.log(`EXACT_JSONL_FRAME>>>\n${frame}\n<<<EXACT_JSONL_FRAME`);
    expect(frame).toContain('6 iters');
    expect(frame).toContain('1.0 minutes');
    expect(frame).toContain('17.0k tokens');
  });
});

