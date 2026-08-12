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
    expect(frame).toContain('✓ Loaded tool definition file_write');
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
    expect(frame).toContain('✗ Ran command');
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
    expect(frame).toContain('✓ Ran command');
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
    expect(frame).toContain('✓ Ran command (5.5s)');
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
    expect(frame).toContain('~ took 5.5s');
    expect(frame).toContain('TERMINAL');
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
    expect(frame).toContain('~/zenith-frontend-tui');
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
    expect(frame).toContain('line 49');
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
    expect(frame).toContain('out 19');
    expect(frame).toContain('more lines');
    expect(frame).toContain('✗ Ran command (2.2s)');
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
});
