import { render } from 'ink-testing-library';
// biome-ignore lint/correctness/noUnusedImports: React is required for JSX transform (jsx: "react")
import React from 'react';
import { afterEach, beforeAll, expect, test, vi } from 'vitest';
import { App } from '../src/App';
import { startupService } from '../src/services/api/StartupService';
import { wsClient } from '../src/services/transport/WebSocketClient';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Unmounts queued by mountApp(), drained in afterEach to prevent leaks. */
const cleanups: Array<() => void> = [];

/**
 * Poll lastFrame() until `predicate` matches or the timeout elapses, then return the
 * final frame. Replaces fixed-wait-then-assert patterns that race with ink rendering
 * under parallel test load (see flaky `/plan`/`/build`/Escape tests).
 */
const waitForFrame = async (getFrame: () => string, predicate: (frame: string) => boolean, timeoutMs = 10_000) => {
  const start = Date.now();
  let frame = getFrame();
  while (!predicate(frame) && Date.now() - start < timeoutMs) {
    await wait(50);
    frame = getFrame();
  }
  return frame;
};

/**
 * Waits until the CommandInput is mounted and enabled (its '❯' prompt is
 * rendered). stdin writes sent before the input exists are dropped silently, so
 * every interactive test must gate its first keystroke on this instead of a
 * fixed sleep (fixed waits race the async startup under parallel load).
 */
const waitForReady = async (getFrame: () => string, timeoutMs = 15_000) => {
  return waitForFrame(getFrame, (f) => f.includes('❯'), timeoutMs);
};

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
      // Fire only `onerror` — NOT `onclose`. The app's WebSocketClient triggers
      // its reconnect() from onclose, which spawns background reconnect timers
      // that race the render loop and make these integration tests flaky.
      this.onerror?.(new Event('error'));
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
  // Unmount any App left mounted by a timed-out or assertion-failing test, so
  // its timers/renders cannot leak into the next test (root cause of cross-test
  // flakiness where an unlucky failure cascades through the file).
  while (cleanups.length > 0) {
    cleanups.pop()?.();
  }
  vi.restoreAllMocks();
  startupService.reset();
  // Stop the singleton wsClient's reconnect timers so background MockWebSocket
  // churn from one test cannot bleed into the next. close() halts reconnect()
  // while leaving connect() usable for subsequent tests.
  wsClient.close();
});

/**
 * Wrap render() so the mounted App is guaranteed to be unmounted in afterEach
 * even when a test times out or an assertion throws before unmount().
 */
function mountApp() {
  const result = render(<App />);
  cleanups.push(result.unmount);
  return result;
}

// ── Startup / Welcome Tests ───────────────────────────────────────

test('App shows Welcome screen when backend validates ready', async () => {
  mockBackendReady();
  const { lastFrame, unmount } = mountApp();

  // Initially loading
  expect(lastFrame()).toContain('ZENITH');

  // Wait for async startup to complete
  const frame = await waitForFrame(lastFrame, (f) => f.includes('SYSTEM STATUS'));
  expect(frame).toContain('RECENT SESSIONS');
  unmount();
});

test('Input is ready after startup', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = mountApp();

  await waitForReady(lastFrame);

  stdin.write('hello');
  const frame = await waitForFrame(lastFrame, (f) => f.includes('hello'));
  expect(frame).toContain('hello');
  unmount();
});

test('Submitting a prompt triggers scenario flow', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = mountApp();

  await waitForReady(lastFrame);

  stdin.write('create a todo app');
  // Submit with '\r' (real Enter → key.return). A bare '\n' is parsed by ink as
  // key.newline with input='', so it never reaches the composer's submit path.
  stdin.write('\r');

  const frame = await waitForFrame(lastFrame, (f) => f.includes('Cannot connect to backend'));
  expect(frame).toContain('Cannot connect to backend');
  unmount();
});

test('/plan command switches to Plan mode', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = mountApp();

  await waitForReady(lastFrame);

  stdin.write('/plan');
  await waitForFrame(lastFrame, (f) => f.includes('[SLASH COMMANDS]'));

  stdin.write('\r');

  const frame = await waitForFrame(lastFrame, (f) => f.includes('[PLAN]'));
  expect(frame).toContain('[PLAN]');
  unmount();
});

test('/build command switches to Build mode', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = mountApp();

  await waitForReady(lastFrame);

  stdin.write('/build');
  await waitForFrame(lastFrame, (f) => f.includes('[SLASH COMMANDS]'));
  stdin.write('\r');

  const frame = await waitForFrame(lastFrame, (f) => f.includes('BUILD'));
  expect(frame).toContain('BUILD');
  unmount();
});

// ── Slash command menu UX ─────────────────────────────────────────

test('slash menu opens inline without hiding the input', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = mountApp();

  await waitForReady(lastFrame);

  stdin.write('/');

  const frame = await waitForFrame(lastFrame, (f) => f.includes('[SLASH COMMANDS]'));
  expect(frame).toContain('❯ /');
  unmount();
});

test('slash menu filters as the user types', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = mountApp();

  await waitForReady(lastFrame);

  stdin.write('/pl');

  const frame = await waitForFrame(lastFrame, (f) => f.includes('❯ /pl'));
  expect(frame).toContain('[SLASH COMMANDS]');
  expect(frame).toContain('❯ /pl');
  unmount();
});

test('slash menu stays closed for text that is not a slash command', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = mountApp();

  await waitForReady(lastFrame);

  stdin.write('Hello /');
  const frame = await waitForFrame(lastFrame, (f) => f.includes('Hello /'));
  expect(frame).not.toContain('[SLASH COMMANDS]');
  expect(frame).toContain('Hello /');
  unmount();
});

test('Esc closes the slash menu but keeps the input', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = mountApp();

  await waitForReady(lastFrame);

  stdin.write('/plan');
  await waitForFrame(lastFrame, (f) => f.includes('[SLASH COMMANDS]'));

  stdin.write('\x1B');

  const frame = await waitForFrame(lastFrame, (f) => !f.includes('[SLASH COMMANDS]') && f.includes('/plan'));
  expect(frame).toContain('/plan');
  unmount();
});

test('Escape during scenario stops execution', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = mountApp();

  await waitForReady(lastFrame);

  stdin.write('test');
  stdin.write('\r');

  const running = await waitForFrame(lastFrame, (f) => /Working|Cannot connect to backend/.test(f));
  expect(running).toMatch(/Working|Cannot connect to backend/);

  stdin.write('\x1B');

  const stopped = await waitForFrame(lastFrame, (f) => f.includes('❯'));
  expect(stopped).toContain('❯');
  unmount();
});

test('Full Build Scenario shows backend error', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = mountApp();

  await waitForReady(lastFrame);

  stdin.write('create a todo app');
  stdin.write('\r');

  const frame = await waitForFrame(lastFrame, (f) => f.includes('Cannot connect to backend'));
  expect(frame).toContain('Cannot connect to backend');
  unmount();
});

test('Full Plan Scenario shows backend error', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = mountApp();

  await waitForReady(lastFrame);

  stdin.write('/plan');
  await waitForFrame(lastFrame, (f) => f.includes('[SLASH COMMANDS]'));
  stdin.write('\r');
  await waitForFrame(lastFrame, (f) => f.includes('[PLAN]'));

  stdin.write('design a REST API');
  stdin.write('\r');

  const frame = await waitForFrame(lastFrame, (f) => f.includes('Cannot connect to backend'));
  expect(frame).toContain('Cannot connect to backend');
  unmount();
});

// ── Startup Error / Setup Flow Tests ──────────────────────────────

test('App shows SetupWizard when backend is unavailable', async () => {
  mockBackendUnavailable();
  const { lastFrame, unmount } = mountApp();

  // Initially loading
  expect(lastFrame()).toContain('ZENITH');

  // Wait for startup to fail
  const frame = await waitForFrame(lastFrame, (f) => f.includes('ZENITH SETUP'));
  expect(frame).toContain('Setup Required');
  unmount();
});
