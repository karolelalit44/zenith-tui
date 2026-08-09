import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { ToolStepCard } from '../src/components/Display/Scenario/ToolStepCard';
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
    expect(frame).toContain('[');
    expect(frame).toContain(']');
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
    expect(frame).toContain('✗ Failed');
    expect(frame).not.toContain('[');
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
});
