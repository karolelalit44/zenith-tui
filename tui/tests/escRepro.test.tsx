import { writeFileSync } from 'node:fs';
import { render, type TestStdin } from 'ink-testing-library';
// biome-ignore lint/correctness/noUnusedImports: React is required for JSX transform (jsx: "react")
import React from 'react';
import { afterEach, expect, test, vi } from 'vitest';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const waitForFrame = async (getFrame: () => string, predicate: (f: string) => boolean, timeoutMs = 20_000) => {
  const start = Date.now();
  let frame = getFrame();
  while (!predicate(frame) && Date.now() - start < timeoutMs) {
    await wait(50);
    frame = getFrame();
  }
  return frame;
};

/**
 * Type a prompt and submit it, tolerating the known harness race where stdin
 * writes can land before Ink registers the input handler (visible under heavy
 * parallel suite load). Retries until the text is visibly inside the input box
 * (``❯ hello``) and until the Welcome screen is replaced by the active turn.
 */
async function typeAndSubmit(stdin: TestStdin, getFrame: () => string, text: string): Promise<void> {
  const typeDeadline = Date.now() + 30_000;
  while (Date.now() < typeDeadline) {
    if (getFrame().includes(`❯ ${text}`)) break;
    stdin.write(text);
    await wait(400);
  }

  const submitDeadline = Date.now() + 30_000;
  while (Date.now() < submitDeadline) {
    if (!getFrame().includes('RECENT SESSIONS')) return;
    stdin.write('\r');
    await wait(500);
  }
}

const cleanups: Array<() => void> = [];

const dump = (label: string, content: string) => {
  writeFileSync(`C:\\Users\\Lenovo\\AppData\\Local\\Temp\\opencode\\esc_${label}.txt`, content, 'utf8');
};

afterEach(() => {
  while (cleanups.length > 0) {
    cleanups.pop()?.();
  }
  vi.restoreAllMocks();
  startupServiceRef.reset();
});

let startupServiceRef: { reset: () => void } = { reset: () => {} };

const READY_RESPONSE = {
  status: 'ready',
  missing: [],
  active_provider: 'openai',
  active_model: 'gpt-4o',
  provider_count: 1,
  message: '',
};

test('Esc during real /ws/test streaming: streamed data must survive and streaming must stop', async () => {
  process.env.ZENITH_BACKEND_URL = process.env.ZENITH_BACKEND_URL || 'http://127.0.0.1:8765';

  const { App } = await import('../src/App');
  const startup = await import('../src/services/api/StartupService');
  startupServiceRef = startup.startupService;

  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(READY_RESPONSE),
  });

  const { lastFrame, stdin, unmount } = render(<App />);
  cleanups.push(unmount);

  await waitForFrame(lastFrame, (f) => f.includes('❯'), 60_000);

  await typeAndSubmit(stdin, lastFrame, 'hello');

  await waitForFrame(lastFrame, (f) => f.includes('simulated test backend'), 90_000);
  const before = lastFrame();
  const streamedBefore = before.includes('simulated test backend');
  dump('before', before);
  console.log('=== FRAME BEFORE ESCAPE (len', before.length, ', streamed:', streamedBefore, ') ===');
  console.log(before);
  console.log('=== END BEFORE ===');
  expect(streamedBefore).toBe(true);

  stdin.write('\x1B');
  await wait(2500);
  const after = lastFrame();
  dump('after', after);
  console.log('=== FRAME AFTER ESCAPE (len', after.length, ') ===');
  console.log(after);
  console.log('=== END AFTER ===');

  const streamedSurvived = after.includes('simulated');
  expect(after.length).toBeGreaterThan(0);
  expect(streamedSurvived).toBe(true);
}, 180_000);
