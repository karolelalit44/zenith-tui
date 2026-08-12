import { render } from 'ink-testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ModelPicker } from '../src/screens/Provider/ModelPicker';
import type { ProviderModelInfo } from '../src/services/providers/types';
import { ThemeProvider } from '../src/theme/ThemeContext';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const pollForFrame = async (
  getFrame: () => string,
  predicate: (frame: string) => boolean,
  message: string,
  timeoutMs = 5000,
): Promise<string> => {
  const start = Date.now();
  let frame = getFrame();
  while (!predicate(frame)) {
    if (Date.now() - start >= timeoutMs) throw new Error(`Timed out waiting for: ${message}`);
    await wait(25);
    frame = getFrame();
  }
  return frame;
};

function model(id: string, name: string): ProviderModelInfo {
  return { id, name, context_window: 128000, description: '', is_default: false };
}

const MODELS: ProviderModelInfo[] = Array.from({ length: 8 }, (_, i) => model(`m-${i + 1}`, `Model ${i + 1}`));

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/models')) {
        return new Response(JSON.stringify({ models: MODELS, total: MODELS.length, offset: 0, limit: 100 }), {
          status: 200,
        });
      }
      return new Response(JSON.stringify({ all: [], active: '', connected: [] }), { status: 200 });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function renderPicker(providerID = 'nvidia') {
  return render(
    <ThemeProvider>
      <ModelPicker providerID={providerID} providerName="NVIDIA AI" onSelect={() => {}} onClose={() => {}} />
    </ThemeProvider>,
  );
}

/**
 * Press ↓ once per `expected` entry, polling until the frame shows the '▸'
 * selection marker on that model, then draining the microtask queue.
 *
 * The drain matters: `useInput`'s handler is re-subscribed in a passive effect
 * AFTER the frame commits, so without it the next ↓ can be handled by a stale
 * closure and move the selection by the wrong amount under parallel load.
 */
async function pressDown(stdin: { write: (s: string) => void }, lastFrame: () => string, expected: string[]) {
  // SearchList mounts only after the models fetch resolves; that render is not
  // act-wrapped, so its useInput subscription can still be pending when the
  // 'Page 1 of 2' frame first appears. Drain microtasks so the very first ↓ is
  // not dropped before any handler is subscribed.
  await wait(0);
  for (const modelName of expected) {
    stdin.write('\u001B[B');
    await pollForFrame(
      () => lastFrame(),
      (f) => f.includes(`▸ ${modelName}`),
      `selection on ${modelName}`,
    );
    await wait(0);
  }
}

describe('ModelPicker pagination (5 models/page)', () => {
  it('shows 5 models per page and a Page indicator', async () => {
    const { lastFrame, unmount } = renderPicker();
    await pollForFrame(
      () => lastFrame(),
      (f) => f.includes('Page 1 of 2'),
      'page 1 rendered',
    );

    const frame = lastFrame();
    expect(frame).toContain('Model 1');
    expect(frame).toContain('Model 5');
    expect(frame).not.toContain('Model 6');
    unmount();
  });

  it('moves to the next page with keyboard navigation and preserves selection', async () => {
    const { stdin, lastFrame, unmount } = renderPicker();
    await pollForFrame(
      () => lastFrame(),
      (f) => f.includes('Page 1 of 2'),
      'page 1 rendered',
    );

    // Page 1 of 2 selected on Model 1; move to the last item (Model 5).
    await pressDown(stdin, lastFrame, ['Model 2', 'Model 3', 'Model 4', 'Model 5']);

    // One more ↓ crosses into page 2 and selects the first item there.
    await pressDown(stdin, lastFrame, ['Model 6']);

    const frame2 = lastFrame();
    expect(frame2).toContain('Page 2 of 2');
    expect(frame2).toContain('Model 8');
    expect(frame2).not.toContain('Model 1');
    unmount();
  });

  it('cannot navigate past the last page (no empty pages)', async () => {
    const { stdin, lastFrame, unmount } = renderPicker();
    await pollForFrame(
      () => lastFrame(),
      (f) => f.includes('Page 1 of 2'),
      'page 1 rendered',
    );
    // 5 downs: 4 to reach Model 5, then cross to page 2.
    await pressDown(stdin, lastFrame, ['Model 2', 'Model 3', 'Model 4', 'Model 5', 'Model 6']);
    expect(lastFrame()).toContain('Page 2 of 2');
    // Pressing down again stays on page 2 (last page has 3 items).
    await pressDown(stdin, lastFrame, ['Model 7', 'Model 8']);
    stdin.write('\u001B[B');
    await wait(0);
    const frame = lastFrame();
    expect(frame).toContain('Page 2 of 2');
    expect(frame).toContain('Model 8');
    unmount();
  });
});
