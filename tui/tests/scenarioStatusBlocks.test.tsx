import { render } from 'ink-testing-library';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MessageBlock } from '../src/components/Display/Scenario/MessageBlock';
import { ProgressBar } from '../src/components/Display/Scenario/ProgressBar';
import { ScenarioRenderer } from '../src/components/Display/Scenario/ScenarioRenderer';
import { SuccessCard } from '../src/components/Display/Scenario/SuccessCard';
import { ThinkingBlock } from '../src/components/Display/Scenario/ThinkingBlock';
import { UserMessageBlock } from '../src/components/Display/Scenario/UserMessageBlock';
import { modelStore } from '../src/services/providers/ModelStore';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type {
  MessageEvent,
  ProgressEvent,
  ScenarioEvent,
  SuccessEvent,
  ThinkingEvent,
  ToolStepEvent,
  TurnManifestEvent,
} from '../src/types/scenario';

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
});

describe('ProgressBar step icons', () => {
  it('uses distinct glyphs for done, active, error, and pending', () => {
    const event: ProgressEvent = {
      kind: 'progress',
      id: 'p1',
      label: 'Build',
      steps: [
        { label: 'read', status: 'done' },
        { label: 'write', status: 'active' },
        { label: 'verify', status: 'error' },
        { label: 'cleanup', status: 'pending' },
      ],
    };
    const { lastFrame } = render(
      <ThemeProvider>
        <ProgressBar event={event} />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('✓ read');
    expect(frame).toContain('✗ verify');
    expect(frame).not.toContain('■');
    expect(frame).not.toContain('□');
  });
});

describe('MessageBlock content rendering', () => {
  it('renders the assistant message text', () => {
    const event: MessageEvent = { kind: 'message', id: 'm1', text: 'hello', iteration: 3 };
    const { lastFrame } = render(
      <ThemeProvider>
        <MessageBlock event={event} />
      </ThemeProvider>,
    );
    expect(lastFrame()).toContain('hello');
  });

  it('does not render a turn indicator', () => {
    const event: MessageEvent = { kind: 'message', id: 'm1', text: 'hello', iteration: 3 };
    const { lastFrame } = render(
      <ThemeProvider>
        <MessageBlock event={event} />
      </ThemeProvider>,
    );
    expect(lastFrame()).not.toContain('turn');
  });

  it('shows the active model name in UserMessageBlock when one is selected', () => {
    vi.spyOn(modelStore, 'current', 'get').mockReturnValue({ providerID: 'openai', modelID: 'gpt-4o-mini' });
    const { lastFrame } = render(
      <ThemeProvider>
        <UserMessageBlock prompt="hello" />
      </ThemeProvider>,
    );
    expect(lastFrame()).toContain('openai/gpt-4o-mini');
  });
});

describe('SuccessCard manifest enrichment', () => {
  const success: SuccessEvent = { kind: 'success', id: 's1', message: 'done', iterations: 5 };
  const manifest: TurnManifestEvent = {
    kind: 'turn_manifest',
    id: 'm1',
    created: ['src/a.ts', 'src/b.ts'],
    modified: ['README.md'],
    remaining: [],
    completed: true,
    stalled: false,
    files: [{ path: 'src/a.ts', exists: true, size: 10 }],
  };

  it('does not duplicate the file count when a manifest is provided', () => {
    const { lastFrame } = render(
      <ThemeProvider>
        <SuccessCard event={success} manifest={manifest} />
      </ThemeProvider>,
    );
    expect(lastFrame()).not.toContain('files created');
    expect(lastFrame()).toContain('5 iters');
  });

  it('renders without a file count when no manifest precedes it', () => {
    const { lastFrame } = render(
      <ThemeProvider>
        <SuccessCard event={success} />
      </ThemeProvider>,
    );
    expect(lastFrame()).not.toContain('files created');
    expect(lastFrame()).toContain('5 iters');
  });

  it('associates a success event with the nearest preceding manifest through ScenarioRenderer', () => {
    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={[manifest, success]} isRunning={false} isHistorical thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    expect(lastFrame()).toContain('✓ Turn complete');
  });
});

describe('SuccessCard token usage and duration', () => {
  const renderSuccess = (event: SuccessEvent, turnEvents?: ScenarioEvent[]) =>
    render(
      <ThemeProvider>
        <SuccessCard event={event} turnEvents={turnEvents} />
      </ThemeProvider>,
    );

  it('shows provider-reported token usage when used > 0', () => {
    const success: SuccessEvent = {
      kind: 'success',
      id: 's1',
      message: 'done',
      tokenInfo: { used: 1500, remaining: 98000, total: 100000, percent: 0.015 },
    };
    const { lastFrame } = renderSuccess(success);
    expect(lastFrame()).toContain('1.5k tokens');
  });

  it('shows the turn duration from elapsedMs on a completed turn', () => {
    const success: SuccessEvent = { kind: 'success', id: 's1', message: 'done', elapsedMs: 3200 };
    const { lastFrame } = renderSuccess(success);
    expect(lastFrame()).toContain('3 s');
  });

  it('does not show a fabricated duration when elapsedMs is missing', () => {
    const success: SuccessEvent = { kind: 'success', id: 's1', message: 'done' };
    const { lastFrame } = renderSuccess(success);
    expect(lastFrame()).not.toContain(' s');
  });

  it('falls back to the frontend estimate when tokenInfo is missing', () => {
    const success: SuccessEvent = { kind: 'success', id: 's1', message: 'done' };
    const turnEvents: ScenarioEvent[] = [
      {
        kind: 'message',
        id: 'm1',
        text: 'A fairly long assistant response that carries enough characters to exceed zero tokens.',
        partial: false,
      },
      {
        kind: 'thinking',
        id: 't1',
        thoughts: ['Some internal reasoning text spanning many characters so the estimate is meaningful.'],
      },
    ];
    const { lastFrame } = renderSuccess(success, turnEvents);
    expect(lastFrame()).toContain('tokens');
  });

  it('falls back to the estimate when tokenInfo.used is zero (estimated usage)', () => {
    const success: SuccessEvent = {
      kind: 'success',
      id: 's1',
      message: 'done',
      tokenInfo: { used: 0, remaining: 0, total: 0, percent: 0, estimated: true },
    };
    const turnEvents: ScenarioEvent[] = [
      {
        kind: 'message',
        id: 'm1',
        text: 'A long message body used to drive the estimation fallback path forward.',
        partial: false,
      },
    ];
    const { lastFrame } = renderSuccess(success, turnEvents);
    expect(lastFrame()).toContain('tokens');
  });
});

describe('ScenarioRenderer tool rendering', () => {
  const step = (tool: string): ToolStepEvent => ({
    kind: 'tool_step',
    id: tool,
    tool,
    params: {},
    success: true,
    output: '',
    error: '',
    metadata: {},
    pending: false,
  });

  it('does not emit exploratory or mutating phase labels', () => {
    const { lastFrame } = render(
      <ThemeProvider>
        <ScenarioRenderer events={[step('grep_search')]} isRunning={false} thinkingCollapsed={false} />
      </ThemeProvider>,
    );
    expect(lastFrame()).not.toContain('Exploring codebase…');
    expect(lastFrame()).not.toContain('Executing plan…');
  });
});
