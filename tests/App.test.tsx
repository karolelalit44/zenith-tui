import { render } from 'ink-testing-library';
// biome-ignore lint/correctness/noUnusedImports: React is required for JSX transform (jsx: "react")
import React from 'react';
import { afterEach, beforeAll, expect, test, vi } from 'vitest';
import { App } from '../src/App';
import { startupService } from '../src/services/data/StartupService';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// ── Mock backend for tests that need the main app ─────────────────

// Mock WebSocket to fail immediately in tests (no real backend running)
class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSING = 2;
  readonly CLOSED = 3;
  readyState = 3;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: ((evt: Event) => void) | null = null;
  onmessage: ((evt: MessageEvent) => void) | null = null;
  close() {}
  send(_data: string) {}
  constructor(_url: string) {
    setTimeout(() => {
      this.readyState = 3;
      this.onerror?.(new Event('error'));
      this.onclose?.(new Event('close'));
    }, 0);
  }
  addEventListener() {}
  removeEventListener() {}
  dispatchEvent(_e: Event) {
    return false;
  }
}
beforeAll(() => {
  (globalThis as any).WebSocket = MockWebSocket;
});

const READY_RESPONSE = {
  status: 'ready',
  missing: [],
  active_provider: 'openai',
  active_model: 'gpt-4o',
  provider_count: 1,
  message: '',
};

function mockBackendReady() {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(READY_RESPONSE),
  });
}

function mockBackendUnavailable() {
  global.fetch = vi.fn().mockRejectedValue(new Error('fetch failed: connection refused'));
}

afterEach(() => {
  vi.restoreAllMocks();
  startupService.reset();
});

// ── Startup / Welcome Tests ───────────────────────────────────────

test('App shows Welcome screen when backend validates ready', async () => {
  mockBackendReady();
  const { lastFrame, unmount } = render(<App />);

  // Initially loading
  expect(lastFrame()).toContain('Initializing');

  // Wait for async startup to complete
  await wait(500);

  const frame = lastFrame();
  expect(frame).toContain('Try asking:');
  expect(frame).toContain('Help me understand this codebase');
  unmount();
});

test('Input is ready after startup', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = render(<App />);

  await wait(500);

  stdin.write('hello');
  await wait(300);
  expect(lastFrame()).toContain('hello');
  unmount();
});

test('Submitting a prompt triggers scenario flow', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = render(<App />);

  await wait(500);

  stdin.write('create a todo app');
  await wait(300);
  stdin.write('\n');
  await wait(500);

  expect(lastFrame()).toContain('Cannot connect to backend');
  unmount();
});

test('/mode command opens mode selector overlay', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = render(<App />);

  await wait(500);

  stdin.write('/mode');
  await wait(200);
  stdin.write('\r');
  await wait(300);

  expect(lastFrame()).toContain('Select Mode');
  expect(lastFrame()).toContain('CHOOSE OPERATING MODE');
  expect(lastFrame()).toContain('Plan');
  expect(lastFrame()).toContain('Build');
  unmount();
});

test('Mode selection changes current mode', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = render(<App />);

  await wait(500);

  // Open mode selector
  stdin.write('/mode');
  await wait(200);
  stdin.write('\r');
  await wait(300);

  // Select Plan (first option, up arrow from Build)
  stdin.write('\x1B[A');
  await wait(100);
  stdin.write('\r');
  await wait(300);

  // Mode selector should have closed — input box should be visible again
  expect(lastFrame()).toContain('❯');
  unmount();
});

test('Escape closes mode selector without changing mode', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = render(<App />);

  await wait(500);

  // Open mode selector
  stdin.write('/mode');
  await wait(200);
  stdin.write('\r');
  await wait(300);

  // Press Escape
  stdin.write('\x1B');
  await wait(300);

  // Input box should reappear — mode selector is closed
  expect(lastFrame()).toContain('❯');
  unmount();
});

test('Escape during scenario stops execution', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = render(<App />);

  await wait(500);

  stdin.write('test');
  await wait(200);
  stdin.write('\n');
  await wait(500);

  expect(lastFrame()).toContain('Cannot connect to backend');

  stdin.write('\x1B');
  await wait(300);

  expect(lastFrame()).toContain('❯');
  unmount();
});

test('Full Build Scenario shows backend error', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = render(<App />);

  await wait(500);

  stdin.write('create a todo app');
  await wait(400);
  stdin.write('\n');
  await wait(1200);

  expect(lastFrame()).toContain('Cannot connect to backend');
  unmount();
});

test('Full Plan Scenario shows backend error', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = render(<App />);

  await wait(500);

  stdin.write('/mode');
  await wait(400);
  stdin.write('\r');
  await wait(400);
  stdin.write('\x1B[A');
  await wait(200);
  stdin.write('\r');
  await wait(500);

  stdin.write('design a REST API');
  await wait(400);
  stdin.write('\n');
  await wait(1200);

  expect(lastFrame()).toContain('Cannot connect to backend');
  unmount();
});

// ── Startup Error / Setup Flow Tests ──────────────────────────────

test('App shows SetupWizard when backend is unavailable', async () => {
  mockBackendUnavailable();
  const { lastFrame, unmount } = render(<App />);

  // Initially loading
  expect(lastFrame()).toContain('Initializing');

  // Wait for startup to fail
  await wait(1000);

  const frame = lastFrame();
  expect(frame).toContain('ZENITH SETUP');
  expect(frame).toContain('Setup Required');
  unmount();
});
