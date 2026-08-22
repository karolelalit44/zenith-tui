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

    evt('tool_call', { tool: 'glob', params: { pattern: '*' } }, 'evt_1');
    evt(
      'tool_result',
      { tool: 'glob', success: true, output: '.env\n.env.example\n.gitignore\n.keys', error: '', metadata: {} },
      'evt_2',
    );
    evt('message', { text: 'Verified all tasks are done.', partial: false }, 'evt_3');
    evt(
      'success',
      {
        message: 'Request processed successfully',
        iterations: 8,
        tokenInfo: { used: 51944, remaining: 76056, total: 128000, percent: 0.406, estimated: false },
        elapsedMs: 87516,
        duration: 87516,
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

  const done = await waitForFrame(lastFrame, (f) => f.includes('Verified all tasks'), 20_000);
  // Allow completeActiveTurn + Static commit to settle.
  await waitForFrame(lastFrame, (f) => f.includes('51.9k tokens'), 20_000);

  expect(done).toBeTruthy();
  const frame = lastFrame();
  console.log(`FINAL>>>\n${frame}\n<<<FINAL`);
  expect(frame).toContain('51.9k tokens');
  unmount();
});
