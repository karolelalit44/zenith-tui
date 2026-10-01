import { render } from 'ink-testing-library';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { WelcomeScreen } from '../src/screens/Welcome/WelcomeScreen';
import { ThemeProvider } from '../src/theme/ThemeContext';

const mocks = vi.hoisted(() => ({
  listSessionSummaries: vi.fn(),
}));

const providerState = {
  id: 'local',
  meta: {
    name: 'Local LLM',
    defaultModel: 'gpt-oss-20b-Q8_0.gguf',
  },
  config: {
    model: 'gpt-oss-20b-Q8_0.gguf',
  },
};

vi.mock('../src/hooks/useProvider', () => ({
  useProvider: () => ({ activeProvider: providerState }),
}));

vi.mock('../src/services/transport/WebSocketClient', () => ({
  wsClient: {
    listSessionSummaries: mocks.listSessionSummaries,
  },
}));

const cleanups: Array<() => void> = [];

function mount(node: React.ReactNode) {
  const app = render(node);
  cleanups.push(app.unmount);
  return app;
}

function stubColumns(columns: number) {
  const original = Object.getOwnPropertyDescriptor(process.stdout, 'columns');
  Object.defineProperty(process.stdout, 'columns', { configurable: true, get: () => columns });
  return () => {
    if (original) Object.defineProperty(process.stdout, 'columns', original);
    else delete (process.stdout as { columns?: number }).columns;
  };
}

function stripAnsi(s: string): string {
  // eslint-disable-next-line no-control-regex
  return s.replace(/\u001b\[[0-9;]*m/g, '');
}

describe('WelcomeScreen responsive layout', () => {
  afterEach(() => {
    for (const unmount of cleanups.splice(0)) unmount();
    vi.clearAllMocks();
  });

  it('switches to compact layout before the ASCII logo wraps', () => {
    mocks.listSessionSummaries.mockResolvedValue([]);
    const restore = stubColumns(120);

    const app = mount(
      <ThemeProvider>
        <WelcomeScreen workspace="/Users/in-lalitkarole/Developer/personal/zenith-tui" />
      </ThemeProvider>,
    );

    const frame = stripAnsi(app.lastFrame() || '');
    expect(frame).toContain('ZENITH');
    expect(frame).not.toContain('███████╗ ███████╗');
    restore();
  });

  it('renders compact recent session titles as single-line labels', async () => {
    mocks.listSessionSummaries.mockResolvedValue([
      {
        id: 's1',
        title: 'Run a live autonomous orchestration smoke test.\n\nDo not leave dangling rows',
        updated_at: '2026-10-01T01:04:00Z',
        created_at: '2026-10-01T01:04:00Z',
        total_tokens: 0,
      },
    ]);
    const restore = stubColumns(120);

    const app = mount(
      <ThemeProvider>
        <WelcomeScreen workspace="/Users/in-lalitkarole/Developer/personal/zenith-tui" />
      </ThemeProvider>,
    );

    try {
      // Poll rather than sleep a fixed interval: the session list arrives from an
      // async wsClient call, so a fixed wait passed or failed depending on load.
      await vi.waitFor(() => {
        expect(stripAnsi(app.lastFrame() || '')).toContain('Run a live autonomous orchestration smoke test.');
      });

      const frame = stripAnsi(app.lastFrame() || '');
      expect(frame).not.toContain('Do not leave dangling rows');
      expect(frame).not.toContain('\n  D\n');
    } finally {
      restore();
    }
  });
});
