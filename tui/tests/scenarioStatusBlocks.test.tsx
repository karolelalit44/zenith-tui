import { render } from 'ink-testing-library';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProgressBar } from '../src/components/Display/Scenario/ProgressBar';
import { ScenarioRenderer } from '../src/components/Display/Scenario/ScenarioRenderer';
import { ThinkingBlock } from '../src/components/Display/Scenario/ThinkingBlock';
import { ToolStepCard } from '../src/components/Display/Scenario/ToolStepCard';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ProgressEvent, ScenarioEvent, ThinkingEvent, ToolStepEvent } from '../src/types/scenario';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ThinkingBlock', () => {
  it('shows a preview of the first thought while collapsed', () => {
    const event: ThinkingEvent = {
      kind: 'thinking',
      id: 't1',
      thoughts: ['Let me first understand the project structure before writing any code.'],
      duration: 3200,
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <ThinkingBlock event={event} context={{ thinkingCollapsed: true, isHistorical: false }} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('Thought for 3 s');
    expect(frame).toContain('Let me first understand the project structure');
  });

  it('does not leak the generic status thought into the preview', () => {
    const event: ThinkingEvent = {
      kind: 'thinking',
      id: 't1',
      thoughts: ['Processing your request'],
      duration: 500,
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <ThinkingBlock event={event} />
      </ThemeProvider>,
    );
    expect(lastFrame()).toBe('');
  });

  it('renders all thoughts immediately when historical (expanded)', () => {
    const event: ThinkingEvent = {
      kind: 'thinking',
      id: 't2',
      thoughts: ['first', 'second', 'third'],
      duration: 1200,
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <ThinkingBlock event={event} context={{ thinkingCollapsed: false, isHistorical: true }} />
      </ThemeProvider>,
    );
    expect(lastFrame()).toContain('first');
    expect(lastFrame()).toContain('second');
    expect(lastFrame()).toContain('third');
  });

  it('renders the first-thought preview when collapsed', () => {
    const event: ThinkingEvent = {
      kind: 'thinking',
      id: 't2',
      thoughts: ['first', 'second', 'third'],
      duration: 1200,
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <ThinkingBlock event={event} context={{ thinkingCollapsed: true, isHistorical: false }} />
      </ThemeProvider>,
    );
    expect(lastFrame()).toContain('first');
    expect(lastFrame()).not.toContain('second');
    expect(lastFrame()).not.toContain('third');
  });
});

describe('ThinkingBlock live streaming', () => {
  it('renders streamed thoughts immediately (backend streams, no fake reveal)', () => {
    const event: ThinkingEvent = {
      kind: 'thinking',
      id: 't3',
      thoughts: ['alpha', 'beta', 'gamma'],
      duration: 1200,
      partial: true,
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <ThinkingBlock event={event} context={{ thinkingCollapsed: false, isHistorical: false }} />
      </ThemeProvider>,
    );
    const frame = lastFrame() || '';
    expect(frame).toContain('alpha');
    expect(frame).toContain('beta');
    expect(frame).toContain('gamma');
    // Streaming marker while no duration is known yet.
    expect(frame).toContain('Thinking');
  });

  it('shows the measured duration once the final event lands', () => {
    const event: ThinkingEvent = {
      kind: 'thinking',
      id: 't4',
      thoughts: ['alpha'],
      duration: 4200,
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <ThinkingBlock event={event} context={{ thinkingCollapsed: false, isHistorical: false }} />
      </ThemeProvider>,
    );
    const frame = lastFrame() || '';
    expect(frame).toContain('Thinking');
    expect(frame).toContain('4 s');
  });
});

describe('ToolStepCard pending duration', () => {
  it('starts the live timer at the step itself, not app mount (shows ~ 1 s on first render)', () => {
    const event: ToolStepEvent = {
      kind: 'tool_step',
      id: 'bash-1',
      tool: 'bash',
      params: { command: 'Get-Date -Format "yyyy-MM-dd"' },
      success: false,
      output: '',
      error: '',
      metadata: {},
      text: undefined,
      pending: true,
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <ToolStepCard event={event} context={{ isRunning: true, isHistorical: false }} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('~ 1 s');
    expect(frame).toContain('Get-Date');
  });
});

describe('ProgressBar compact live row', () => {
  it('shows only the active step, a done/total counter, and no big bar', () => {
    const event: ProgressEvent = {
      kind: 'progress',
      id: 'p1',
      label: 'Build',
      steps: [
        { label: 'read files', status: 'done' },
        { label: 'edit config', status: 'active' },
        { label: 'verify', status: 'pending' },
      ],
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <ProgressBar event={event} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('edit config');
    expect(frame).toContain('1/3');
    // Old noisy chrome is gone: no percent bar, no full checklist.
    expect(frame).not.toContain('\u2588');
    expect(frame).not.toContain('read files');
    expect(frame).not.toContain('* Build');
  });

  it('renders an error glyph when the current step failed', () => {
    const event: ProgressEvent = {
      kind: 'progress',
      id: 'p2',
      label: 'Build',
      steps: [{ label: 'run tests', status: 'error' }],
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <ProgressBar event={event} />
      </ThemeProvider>,
    );
    expect(lastFrame()).toContain('\u2717');
    expect(lastFrame()).toContain('run tests');
  });
});

describe('thinking positional fidelity', () => {
  it('keeps one block PER ITERATION at its timeline position (no turn-level merge)', () => {
    const mkThinking = (id: string, text: string): ScenarioEvent => ({
      kind: 'thinking',
      id,
      thoughts: [text],
      duration: 0,
    });
    const events: ScenarioEvent[] = [
      mkThinking('t1', 'first reasoning segment before the command'),
      {
        kind: 'tool_step',
        id: 's1',
        tool: 'bash',
        params: { command: 'npm test' },
        success: true,
        output: '',
        error: '',
        metadata: {},
        pending: false,
      },
      mkThinking('t2', 'second reasoning segment after the command'),
      { kind: 'message', id: 'm1', text: 'answer', partial: false },
    ];
    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={events} isRunning={false} isHistorical={true} />
      </ThemeProvider>,
    );
    const frame = lastFrame() || '';
    expect(frame).toContain('first reasoning segment');
    expect(frame).toContain('second reasoning segment');
    expect(frame.indexOf('first reasoning segment')).toBeLessThan(frame.indexOf('npm test'));
    expect(frame.indexOf('npm test')).toBeLessThan(frame.indexOf('second reasoning segment'));
  });

  it('preserves multi-iteration thinking -> tool_step -> thinking -> message sequence', () => {
    const events: ScenarioEvent[] = [
      {
        kind: 'thinking',
        id: 't1',
        thoughts: ['* Goal: Create a new file sms-plan.md'],
        duration: 12000,
        partial: false,
      },
      {
        kind: 'tool_step',
        id: 's1',
        tool: 'file_write',
        params: { path: 'sms-plan.md', content: '# Plan' },
        success: true,
        output: 'Created sms-plan.md',
        error: '',
        metadata: {},
        pending: false,
      },
      {
        kind: 'thinking',
        id: 't2',
        thoughts: ['The user has provided a success message from file_write'],
        duration: 3100,
        partial: false,
      },
      {
        kind: 'message',
        id: 'm1',
        text: 'The file sms-plan.md has been created with Django and HTMX.',
        partial: false,
      },
      {
        kind: 'turn_manifest',
        id: 'manifest1',
        completed: true,
        created: ['sms-plan.md'],
        modified: [],
      },
      {
        kind: 'success',
        id: 'succ1',
        message: 'done',
        elapsedMs: 15100,
      },
    ];

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={events} isRunning={false} isHistorical={true} />
      </ThemeProvider>,
    );
    const frame = lastFrame() || '';
    expect(frame).toContain('Create a new file sms-plan.md');
    expect(frame).toContain('sms-plan.md');
    expect(frame).toContain('The user has provided a success message');
    expect(frame).toContain('The file sms-plan.md has been created');

    const idxT1 = frame.indexOf('Create a new file sms-plan.md');
    const idxTool = frame.indexOf('sms-plan.md');
    const idxT2 = frame.indexOf('The user has provided a success message');
    const idxMsg = frame.indexOf('The file sms-plan.md has been created');

    expect(idxT1).toBeLessThan(idxTool);
    expect(idxTool).toBeLessThan(idxT2);
    expect(idxT2).toBeLessThan(idxMsg);
  });

  it('suppresses empty turn_manifest noise and renders success card with tokens and duration', () => {
    const events: ScenarioEvent[] = [
      {
        kind: 'thinking',
        id: 't1',
        thoughts: ['The user wants me to analyze the sms-plan.md file'],
        duration: 5000,
        partial: false,
      },
      {
        kind: 'message',
        id: 'm1',
        text: 'Analysis of sms-plan.md',
        partial: false,
      },
      {
        kind: 'turn_manifest',
        id: 'tm1',
        completed: true,
        created: [],
        modified: [],
        remaining: [],
        files: [],
      },
      {
        kind: 'success',
        id: 'succ1',
        message: 'Turn finished',
        iterations: 1,
        elapsedMs: 5200,
        tokenInfo: { used: 2765, remaining: 125235, total: 128000, percent: 0.022 },
      },
    ];

    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={events} isRunning={false} isHistorical={true} />
      </ThemeProvider>,
    );
    const frame = lastFrame() || '';
    expect(frame).toContain('Analysis of sms-plan.md');
    // Turn manifest noise should be suppressed when there are no file changes
    expect(frame).not.toContain('Turn paused');
    expect(frame).not.toContain('no changes');
    // Success card metrics should render with iteration, duration and token count
    expect(frame).toContain('1 iter');
    expect(frame).toContain('5 s');
    expect(frame).toContain('2.8k tokens');
  });
});
