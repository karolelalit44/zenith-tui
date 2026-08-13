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
