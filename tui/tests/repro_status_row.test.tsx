import { writeFileSync } from 'node:fs';
import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { ScenarioRenderer } from '../src/components/Display/Scenario/ScenarioRenderer';
import { AnimationProvider } from '../src/context/AnimationContext';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ScenarioEvent } from '../src/types/scenario';

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
});
