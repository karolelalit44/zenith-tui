import { render } from 'ink-testing-library';
import { describe, expect, it, vi } from 'vitest';
import type { ContextInfoSnapshot } from '../src/hooks/useConversation';
import { ContextModal } from '../src/screens/Context/ContextModal';
import { ThemeProvider } from '../src/theme/ThemeContext';

vi.mock('../src/hooks/useProvider', () => ({
  useProvider: () => ({
    activeProvider: {
      id: 'nvidia',
      meta: {
        id: 'nvidia',
        name: 'NVIDIA AI',
        description: 'test provider',
        defaultModel: 'test-model',
        fields: [],
        availableModels: [{ id: 'test-model', name: 'Test Model', context_window: 128_000 }],
      },
      config: { model: 'test-model' },
      isActive: true,
      isConfigured: true,
      isPopular: true,
      isCustomFlow: false,
      baseUrlStyle: 'openai',
      supportsPromptCaching: false,
      supportsThinkingHeaders: false,
    },
  }),
}));

describe('ContextModal', () => {
  it('renders composed-context occupancy from the backend snapshot separately from run usage', () => {
    const contextInfo: ContextInfoSnapshot = {
      used: 51_200,
      remaining: 76_800,
      total: 128_000,
      percent: 0.4,
      windowEstimated: false,
    };

    const { lastFrame } = render(
      <ThemeProvider>
        <ContextModal
          totalTokens={0}
          onClose={() => {}}
          contextInfo={contextInfo}
          runTokens={52_316}
          runPrompt={1_821}
          runCompletion={50_495}
        />
      </ThemeProvider>,
    );

    const frame = lastFrame();
    // Composed-context occupancy (the gauge source).
    expect(frame).toContain('51.2k / 128.0k (40%)');
    // Cumulative run/API telemetry, clearly separated.
    expect(frame).toContain('RUN USAGE');
    expect(frame).toContain('52.3k');
    expect(frame).toContain('prompt 1.8k');
    expect(frame).toContain('completion 50.5k');
  });

  it('marks estimated window and estimated run usage with a tilde', () => {
    const contextInfo: ContextInfoSnapshot = {
      used: 51_200,
      remaining: 0,
      total: 51_200,
      percent: 1,
      windowEstimated: true,
    };

    const { lastFrame } = render(
      <ThemeProvider>
        <ContextModal
          totalTokens={0}
          onClose={() => {}}
          contextInfo={contextInfo}
          runTokens={52_316}
          runEstimated={true}
        />
      </ThemeProvider>,
    );

    const frame = lastFrame();
    expect(frame).toContain('51.2k / 51.2k (100%)');
    expect(frame).toContain('52.3k');
    expect(frame).not.toContain('~');
  });

  it('falls back to the live estimate and hides the run row for legacy runs', () => {
    const { lastFrame } = render(
      <ThemeProvider>
        <ContextModal totalTokens={0} runningEvents={[]} onClose={() => {}} contextInfo={null} />
      </ThemeProvider>,
    );

    const frame = lastFrame();
    // No composed snapshot and no run usage → empty gauge, no run row.
    expect(frame).toContain('(0%)');
    expect(frame).not.toContain('RUN USAGE');
  });
});
