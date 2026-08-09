import { render } from 'ink-testing-library';
import { describe, expect, it } from 'vitest';
import { PlanReadyBlock } from '../src/components/Display/Scenario/PlanReadyBlock';
import { ThemeProvider } from '../src/theme/ThemeContext';
import type { PlanReadyEvent } from '../src/types/scenario';

function renderPlan(event: PlanReadyEvent) {
  return render(
    <ThemeProvider>
      <PlanReadyBlock event={event} />
    </ThemeProvider>,
  );
}

describe('PlanReadyBlock', () => {
  it('renders a distinct plan-ready header instead of the message fallback', () => {
    const { lastFrame } = renderPlan({
      kind: 'plan_ready',
      id: 'p1',
      plan: '## Steps\n1. Read\n2. Write',
      sessionId: 's1',
    });
    const frame = lastFrame();
    expect(frame).toContain('◈');
    expect(frame).toContain('Plan ready');
    expect(frame).not.toContain('(empty response)');
  });

  it('renders the plan markdown content', () => {
    const { lastFrame } = renderPlan({
      kind: 'plan_ready',
      id: 'p1',
      plan: 'Read the codebase first.',
      sessionId: 's1',
    });
    const frame = lastFrame();
    expect(frame).toContain('Read the codebase first.');
  });
});
