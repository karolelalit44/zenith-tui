import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { ToolTraceBlock } from '../src/components/Display/Scenario/ToolTraceBlock';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { ToolCallEvent, ToolResultEvent } from '../src/types/scenario';

function renderTrace(event: ToolCallEvent | ToolResultEvent) {
  return render(
    <ThemeProvider>
      <ToolTraceBlock event={event} />
    </ThemeProvider>,
  );
}

describe('ToolTraceBlock', () => {
  it('renders a tool_call with tool name and primary param', () => {
    const call: ToolCallEvent = {
      kind: 'tool_call',
      id: 'c1',
      tool: 'file_read',
      params: { path: 'src/main.ts' },
    };
    const { lastFrame } = renderTrace(call);
    const frame = lastFrame();
    expect(frame).toContain('Read');
    expect(frame).toContain('path: src/main.ts');
  });

  it('renders a successful tool_result', () => {
    const result: ToolResultEvent = {
      kind: 'tool_result',
      id: 'r1',
      tool: 'file_read',
      success: true,
      output: 'ok',
      error: '',
      metadata: {},
    };
    const { lastFrame } = renderTrace(result);
    const frame = lastFrame();
    expect(frame).toContain('');
    expect(frame).toContain('Read');
  });

  it('renders a failed tool_result with the error detail', () => {
    const result: ToolResultEvent = {
      kind: 'tool_result',
      id: 'r1',
      tool: 'file_write',
      success: false,
      output: '',
      error: 'Permission denied',
      metadata: {},
    };
    const { lastFrame } = renderTrace(result);
    const frame = lastFrame();
    expect(frame).toContain('✗');
    expect(frame).toContain('Permission denied');
  });

  it('truncates long output to a safe preview', () => {
    const result: ToolResultEvent = {
      kind: 'tool_result',
      id: 'r1',
      tool: 'bash',
      success: true,
      output: 'x'.repeat(500),
      error: '',
      metadata: {},
    };
    const { lastFrame } = renderTrace(result);
    expect(lastFrame().length).toBeLessThan(300);
  });
});
