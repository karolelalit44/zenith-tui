import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { ToolStepCard } from '../src/components/Display/Scenario/ToolStepCard';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ToolStepEvent } from '../src/types/scenario';

function makeExplore(overrides: Partial<ToolStepEvent> = {}): ToolStepEvent {
  return {
    id: 'explore_1',
    kind: 'tool_step',
    tool: 'explore',
    params: { objective: 'find where compaction is triggered' },
    success: true,
    output:
      'Summary: Compaction triggers at 85 percent context usage.\nFindings:\n - [verified] Threshold gate in ContextManager',
    error: '',
    metadata: {
      explore_status: 'completed',
      crewmate_name: 'Apogee',
      crewmate_role: 'Codebase Explorer',
      thoroughness: 'standard',
      tokens_used: 18_400,
      tool_calls: 9,
      verified_count: 3,
      proposed_count: 2,
      unverified_count: 1,
      affected_files: ['server/agents/context.py'],
    },
    pending: false,
    ...overrides,
  };
}

function renderStep(event: ToolStepEvent) {
  return render(
    <ThemeProvider>
      <ToolStepCard event={event} />
    </ThemeProvider>,
  );
}

describe('ExploreCrewCard (WP5)', () => {
  it('renders the crewmate identity and mission while flying', () => {
    const { lastFrame } = renderStep(makeExplore({ pending: true, success: true, output: '' }));
    const frame = lastFrame() || '';
    expect(frame).toContain('Apogee');
    expect(frame).toContain('Codebase Explorer');
    expect(frame).toContain('standard');
    expect(frame).toContain('find where compaction is triggered');
  });

  it('renders confidence chips, stats and affected files on completion', () => {
    const { lastFrame } = renderStep(makeExplore());
    const frame = lastFrame() || '';
    expect(frame).toContain('✓');
    expect(frame).toContain('3 verified');
    expect(frame).toContain('2 proposed');
    expect(frame).toContain('1 unverified');
    expect(frame).toContain('18.4k tok');
    expect(frame).toContain('9 calls');
    expect(frame).toContain('server/agents/context.py');
    expect(frame).toContain('Compaction triggers at 85 percent');
  });

  it('marks cached intelligence with the reuse badge', () => {
    const { lastFrame } = renderStep(
      makeExplore({ metadata: { ...(makeExplore().metadata as object), cached: true } }),
    );
    expect(lastFrame() || '').toContain('reused intelligence');
  });

  it('renders failures with the error line', () => {
    const { lastFrame } = renderStep(
      makeExplore({
        success: false,
        output: '[explore] failed\nError: child provider down',
        metadata: { explore_status: 'failed', crewmate_name: 'Vasco' },
        error: 'child provider down',
      }),
    );
    const frame = lastFrame() || '';
    expect(frame).toContain('✗');
    expect(frame).toContain('child provider down');
  });
});
