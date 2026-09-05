import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { ToolStepCard } from '../src/components/Display/Scenario/ToolStepCard';
import { SPINNER_FRAMES } from '../src/constants/animation';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ToolStepEvent } from '../src/types/scenario';

function makeStep(overrides: Partial<ToolStepEvent> = {}): ToolStepEvent {
  return {
    id: 'evt_1',
    kind: 'tool_step',
    tool: 'file_write',
    params: { path: 'src/a.ts' },
    success: true,
    output: '',
    error: '',
    metadata: {},
    pending: false,
    ...overrides,
  };
}

describe('execution timeline polish', () => {
  it('renders a cancelled execution with the distinct interrupted state', () => {
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'bash',
        params: { command: 'npm run build' },
        success: false,
        error: 'Execution interrupted by user',
      }),
    );
    const frame = lastFrame() || '';
    expect(frame).toContain('\u2298');
    expect(frame).toContain('interrupted');
  });

  it('renders an unpaired historical call as interrupted (never a pending arrow)', () => {
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'file_read',
        params: { path: 'a.ts' },
        success: false,
        error: 'execution interrupted before completion',
        metadata: { interrupted: true },
      }),
    );
    const frame = lastFrame() || '';
    expect(frame).toContain('\u2298');
    expect(frame).not.toContain('\u2192');
  });

  it('shows the exit code chip for failed shell commands', () => {
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'bash',
        params: { command: 'exit 3' },
        success: false,
        error: 'command failed',
        metadata: { exit_code: 3, duration_ms: 1200 },
      }),
    );
    expect(lastFrame()).toContain('exit 3');
  });

  it('shows a duration pill for non-shell tools via metadata.duration_ms', () => {
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'grep',
        params: { pattern: 'foo' },
        output: 'a\nb',
        metadata: { duration_ms: 2400 },
      }),
    );
    expect(lastFrame()).toContain('~ 2 s');
  });

  it('renders the repeat badge for folded consecutive reads', () => {
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'file_read',
        params: { path: 'App.tsx' },
        output: 'x',
        metadata: { repeatCount: 4 },
      }),
    );
    expect(lastFrame()).toContain('\u00d74');
  });
});

function renderStep(event: ToolStepEvent, context?: { isRunning?: boolean; isHistorical?: boolean }) {
  return render(
    <ThemeProvider>
      <ToolStepCard event={event} context={context} />
    </ThemeProvider>,
  );
}

describe('ToolStepCard', () => {
  it('renders a completed file_write step with the Create verb and its path', () => {
    const { lastFrame } = renderStep(makeStep({ metadata: { path: 'src/a.ts', size: 42 } }));
    const frame = lastFrame();
    expect(frame).toContain('●');
    expect(frame).toContain('Create');
    expect(frame).toContain('src/a.ts');
  });

  it('renders a failed step with the failed status', () => {
    const { lastFrame } = renderStep(makeStep({ success: false }));
    const frame = lastFrame();
    expect(frame).toContain('✗ Failed');
  });

  it('replaces the generic "Executing <tool>…" template with the verb label', () => {
    const { lastFrame } = renderStep(makeStep({ text: 'Executing file_write…' }));
    const frame = lastFrame();
    expect(frame).not.toContain('Executing file_write');
    expect(frame).toContain('Create');
    expect(frame).toContain('src/a.ts');
  });

  it('keeps a non-generic backend text field as the call header when present', () => {
    const { lastFrame } = renderStep(makeStep({ text: 'Custom header text here' }));
    const frame = lastFrame();
    expect(frame).toContain('Custom header text here');
  });

  it('renders GET_TOOL_DEFINITION as a compact loaded line without raw JSON', () => {
    const json = '{"tool":{"name":"file_write","parameters":{"$schema":"http://json-schema.org/"}}}';
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'get_tool_definition',
        params: {},
        success: true,
        metadata: { tool_name: 'file_write' },
        text: 'Getting tool definition for file_write',
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain(' Loaded tool definition file_write');
    expect(frame).not.toContain('$schema');
    expect(frame).not.toContain(json);
  });

  it('shows a spinner and elapsed seconds while pending in a live run', () => {
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'bash',
        params: { command: 'npm test' },
        success: false,
        pending: true,
      }),
      { isRunning: true, isHistorical: false },
    );
    const frame = lastFrame();
    expect(frame).toContain(SPINNER_FRAMES[0]);
    expect(frame).toContain('npm test');
  });

  it('does not render a spinner for a pending event during historical replay', () => {
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'bash',
        params: { command: 'npm test' },
        success: false,
        pending: true,
      }),
      { isRunning: true, isHistorical: true },
    );
    const frame = lastFrame();
    // Historical replay renders the terminal window frozen (no live spinner),
    // showing the failed command prompt rather than a "Ran command" verdict.
    expect(frame).toContain('npm test');
    expect(frame).toContain('✗');
    expect(frame).not.toContain(SPINNER_FRAMES[0]);
  });

  it('renders a bash step as a completed run command', () => {
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'bash',
        params: { command: 'npm test' },
        metadata: { duration_ms: 1200 },
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain('');
    expect(frame).toContain('❯❯');
    expect(frame).toContain('npm test');
    expect(frame).toContain('~ 1 s');
  });

  it('renders bash stdout between the prompt and the footer', () => {
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'bash',
        params: { command: 'python -m unittest' },
        output: 'Ran 3 tests in 0.004s\n\nOK',
        metadata: { duration_ms: 5500 },
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain('python -m unittest');
    expect(frame).toContain('Ran 3 tests in 0.004s');
    expect(frame).toContain('OK');
    expect(frame).toContain('~ 5 s');
  });

  it('shows the ~ took timing pill and command tab name in the titlebar', () => {
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'bash',
        params: { command: 'npm test' },
        metadata: { duration_ms: 5500 },
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain('~ 5 s');
    expect(frame).toContain('npm test');
  });

  it('renders the workspace path and git branch when provided in context', () => {
    const { lastFrame } = render(
      <ThemeProvider>
        <ToolStepCard
          event={makeStep({ tool: 'bash', params: { command: 'npm test' }, metadata: { duration_ms: 800 } })}
          context={{
            isRunning: false,
            isHistorical: false,
            workspaceName: 'C:/work/zenith-frontend-tui',
            gitBranch: 'main',
          }}
        />
      </ThemeProvider>,
    );
    const frame = lastFrame();
    expect(frame).toContain('zenith-frontend-tui');
    expect(frame).toContain('main');
  });

  it('caps very long bash output with an overflow line', () => {
    const longOutput = Array.from({ length: 60 }, (_, i) => `line ${i}`).join('\n');
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'bash',
        params: { command: 'make test' },
        output: longOutput,
        metadata: { duration_ms: 100 },
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain('more lines');
    expect(frame).toContain('line 0');
    expect(frame).not.toContain('line 59');
  });

  it('collapses a multi-line bash command to its first line in the prompt', () => {
    const multi = 'New-Item -ItemType Directory -Path $epoch\n$code = @"\nWrite-Output $code';
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'bash',
        params: { command: multi },
        metadata: { duration_ms: 100 },
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain('New-Item -ItemType Directory -Path $epoch …');
    expect(frame).not.toContain('Write-Output $code');
  });

  it('renders the failure error and caps failed output tighter', () => {
    const longOutput = Array.from({ length: 30 }, (_, i) => `out ${i}`).join('\n');
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'bash',
        params: { command: 'Set-Content -Path x.txt -Value $epoch' },
        output: longOutput,
        error: 'Set-Content : A positional parameter cannot be found that accepts argument',
        success: false,
        metadata: { duration_ms: 2200 },
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain('Set-Content : A positional parameter');
    expect(frame).toContain('out 0');
    expect(frame).toContain('more lines');
    expect(frame).not.toContain('out 19');
    expect(frame).toContain('✗');
    expect(frame).toContain('~ 2 s');
  });

  it('truncates an over-long tab name in the titlebar', () => {
    const longCmd = `$epoch = [int](Get-Date -UFormat %s); ${'x'.repeat(80)}`;
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'bash',
        params: { command: longCmd },
        metadata: { duration_ms: 100 },
      }),
    );
    const frame = lastFrame();
    expect(frame).not.toContain('x'.repeat(80));
  });

  it('renders a file_edit step with its server-captured unified diff', () => {
    const diff = '@@ -1,2 +1,2 @@\n-old line\n+new line\n';
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'file_edit',
        params: { path: 'src/a.ts', old_content: 'old line', new_content: 'new line' },
        success: true,
        metadata: { path: 'src/a.ts', diff },
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain('Update');
    expect(frame).toContain('src/a.ts');
    expect(frame).toContain('old line');
    expect(frame).toContain('new line');
  });

  it('builds a fallback hunk diff for a file_edit with no server diff', () => {
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'file_edit',
        params: { path: 'src/a.ts', old_content: 'before', new_content: 'after' },
        success: true,
        metadata: { path: 'src/a.ts' },
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain('before');
    expect(frame).toContain('after');
  });

  it('renders a multi_edit step with its captured diff', () => {
    const diff = '@@ -1,2 +1,2 @@\n-alpha\n+beta\n';
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'multi_edit',
        params: { filepath: 'src/b.ts' },
        success: true,
        metadata: { filepath: 'src/b.ts', diff },
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain('Update');
    expect(frame).toContain('src/b.ts');
    expect(frame).toContain('alpha');
    expect(frame).toContain('beta');
  });

  it('renders a successful file_delete with the destructive icon and muted note', () => {
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'file_delete',
        params: { path: 'src/gone.ts' },
        success: true,
        metadata: { path: 'src/gone.ts' },
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain('✗ Delete');
    expect(frame).toContain('src/gone.ts');
    expect(frame).toContain('removed from workspace');
  });

  it('renders the rich status label for a successful websearch', () => {
    const { lastFrame } = renderStep(
      makeStep({
        tool: 'websearch',
        params: { query: 'ink components' },
        metadata: { query: 'ink components' },
      }),
    );
    const frame = lastFrame();
    expect(frame).toContain(' Web search');
    expect(frame).toContain('ink components');
  });
});
