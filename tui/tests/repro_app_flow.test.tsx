import { render } from 'ink-testing-library';
import { afterEach, beforeAll, expect, test, vi } from 'vitest';
import { App } from '../src/App';
import { startupService } from '../src/services/api/StartupService';
import { wsClient } from '../src/services/transport/WebSocketClient';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const cleanups: Array<() => void> = [];

const waitForFrame = async (getFrame: () => string, predicate: (frame: string) => boolean, timeoutMs = 15_000) => {
  const start = Date.now();
  let frame = getFrame();
  while (!predicate(frame) && Date.now() - start < timeoutMs) {
    await wait(50);
    frame = getFrame();
  }
  return frame;
};

// ── Mock backend that CONNECTS and streams a full turn ────────────

interface Pending {
  resolve: (v: unknown) => void;
  reject: (e: Error) => void;
}

class MockWs {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSING = 2;
  readonly CLOSED = 3;
  readyState = 0;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: ((evt: Event) => void) | null = null;
  onmessage: ((evt: MessageEvent) => void) | null = null;
  private pending = new Map<string, Pending>();
  private streamed = false;

  close() {
    this.readyState = 3;
    this.onclose?.();
  }

  private sendJson(obj: unknown) {
    this.onmessage?.({ data: JSON.stringify(obj) } as MessageEvent);
  }

  send(data: string) {
    const req = JSON.parse(data);
    const { id, method } = req;
    if (method === 'session.create') {
      this.sendJson({ jsonrpc: '2.0', id, result: { id: 'sess_1', title: 't' } });
      return;
    }
    if (method === 'prompt.send') {
      this.sendJson({ jsonrpc: '2.0', id, result: { session_id: 'sess_1', status: 'ok' } });
      if (!this.streamed) {
        this.streamed = true;
        this.stream();
      }
      return;
    }
    const pending = this.pending.get(String(id));
    if (pending) {
      this.pending.delete(String(id));
      pending.resolve({ ok: true });
    }
  }

  private stream() {
    const evt = (kind: string, data: Record<string, unknown>, id: string) =>
      this.sendJson({ jsonrpc: '2.0', method: 'event', params: { kind, id, data } });

    evt('tool_call', { tool: 'glob', params: { pattern: '**/todo.md' } }, 'evt_1');
    evt(
      'tool_result',
      { tool: 'glob', success: true, output: 'todo.md', error: '', metadata: {} },
      'evt_2',
    );
    evt('message', { text: 'Would you like me to update the todo.md to address these gaps?', partial: false }, 'evt_3');
    evt(
      'success',
      {
        message: 'Request processed successfully',
        iterations: 6,
        tokenInfo: { used: 17001, remaining: 110999, total: 128000, percent: 0.133, runTotal: 64758, estimated: false },
        elapsedMs: 62821,
        duration: 62821,
      },
      'evt_4',
    );
  }

  addEventListener() {}
  removeEventListener() {}
  dispatchEvent(_e: Event) {
    return false;
  }

  constructor(_url: string) {
    setTimeout(() => {
      this.readyState = 1;
      this.onopen?.();
    }, 0);
  }
}

beforeAll(() => {
  (globalThis as any).WebSocket = MockWs;
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

afterEach(() => {
  while (cleanups.length > 0) {
    cleanups.pop()?.();
  }
  vi.restoreAllMocks();
  startupService.reset();
  wsClient.close();
});

function mountApp() {
  const result = render(<App />);
  cleanups.push(result.unmount);
  return result;
}

test('completed static response shows token usage + duration status row', async () => {
  mockBackendReady();
  const { lastFrame, stdin, unmount } = mountApp();

  await waitForFrame(lastFrame, (f) => f.includes('❯'));
  await new Promise((r) => setTimeout(r, 100));

  stdin.write('Hey');
  stdin.write('\r');

  const done = await waitForFrame(lastFrame, (f) => f.includes('Would you like me to update'), 20_000);
  console.log(`DONE_FRAME_HAS_TOKENS: ${done.includes('17.0k tokens')}`);
  if (!done.includes('17.0k tokens')) {
    console.log(`DONE_FRAME_BOTTOM>>>\n${done.slice(-500)}\n<<<DONE_FRAME_BOTTOM`);
  }
  // Allow completeActiveTurn + Static commit to settle.
  const hasTokens = await waitForFrame(lastFrame, (f) => f.includes('17.0k tokens'), 20_000);

  expect(done).toBeTruthy();
  const frame = lastFrame();
  console.log(`FLOW_CF60E0DB_FINAL>>>\n${frame}\n<<<FLOW_CF60E0DB_FINAL`);
  expect(hasTokens).toBeTruthy();
  expect(frame).toContain('17.0k tokens');
  unmount();
});
