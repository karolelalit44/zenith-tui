import { render } from 'ink-testing-library';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProviderFlow } from '../src/screens/Provider/ProviderFlow';
import type { ProviderCatalogItem, ProviderListResponse } from '../src/services/providers/types';
import { ThemeProvider } from '../src/theme/ThemeContext';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function provider(id: string, name: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    name,
    description: '',
    adapter: 'openai_compat',
    swatch: [],
    capabilities: {},
    api_key_prefix: '',
    requires_api_key: true,
    config_fields: [],
    options: {},
    has_api_key: false,
    api_key_masked: '',
    validation_status: 'unconfigured',
    last_validation_error: '',
    is_active: false,
    model: '',
    models: {},
    is_popular: false,
    base_url_style: '',
    supports_prompt_caching: true,
    supports_thinking_headers: false,
    custom_flow: false,
    env_keys: [],
    ...extra,
  } as const;
}

/** Rich provider list for the legacy /startup/providers payload. */
const LIST: ProviderListResponse = {
  all: [
    provider('openrouter', 'OpenRouter', {
      has_api_key: true,
      validation_status: 'validated',
      is_active: true,
      is_popular: true,
      model: 'openrouter/free',
    }),
    provider('tokenrouter', 'TokenRouter', { model: 'moonshotai/kimi-k3-free' }),
    provider('openai_compatible', 'OpenAI Compatible', { model: 'moonshotai/kimi-k3-free' }),
    provider('openai', 'OpenAI', {
      has_api_key: true,
      validation_status: 'validated',
      is_popular: true,
      model: 'o3-mini',
    }),
    provider('nvidia', 'NVIDIA AI', {
      has_api_key: true,
      validation_status: 'validated',
      is_popular: true,
      model: 'nvidia/nemotron-3-ultra-550b-a55b',
    }),
    provider('groq', 'Groq', { is_popular: true, model: 'llama-3.3-70b-versatile' }),
    provider('anthropic', 'Anthropic', { is_popular: true, model: 'claude-sonnet-4-20250514' }),
    provider('google', 'Google AI Studio', { is_popular: true, model: 'gemini-3.5-flash-lite', adapter: 'gemini' }),
    provider('custom', 'Custom OpenAI-Compatible', { custom_flow: true, model: 'llama3' }),
  ],
  active: 'openrouter',
  connected: ['openrouter', 'openai', 'nvidia'],
};

/** Lightweight provider catalog served by GET /providers (carries no models). */
const CATALOG: ProviderCatalogItem[] = [
  { id: 'openrouter', name: 'OpenRouter', type: 'default' },
  { id: 'tokenrouter', name: 'TokenRouter', type: 'default' },
  { id: 'openai_compatible', name: 'OpenAI Compatible', type: 'custom' },
  { id: 'openai', name: 'OpenAI', type: 'default' },
  { id: 'nvidia', name: 'NVIDIA AI', type: 'default' },
  { id: 'groq', name: 'Groq', type: 'default' },
  { id: 'anthropic', name: 'Anthropic', type: 'default' },
  { id: 'google', name: 'Google AI Studio', type: 'default' },
  { id: 'custom', name: 'Custom OpenAI-Compatible', type: 'custom' },
];

/** Models served by GET /providers/{id}/models — comes from the backend only. */
const MODELS = {
  google: [
    {
      id: 'gemini-3.5-flash-lite',
      name: 'Gemini 3.5 Flash-Lite',
      context_window: 1048576,
      description: '',
      is_default: true,
    },
    { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', context_window: 1048576, description: '', is_default: false },
  ],
  anthropic: [
    {
      id: 'claude-sonnet-4-20250514',
      name: 'Claude Sonnet 4',
      context_window: 200000,
      description: '',
      is_default: true,
    },
  ],
} as const;

const validateCalls: { url: string; body: { api_key: string; model: string } }[] = [];
const setModelCalls: { url: string; body: { model: string } }[] = [];

beforeEach(() => {
  validateCalls.length = 0;
  setModelCalls.length = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | RequestInit | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/startup/providers') && (init?.method === 'GET' || init?.method === undefined)) {
        return new Response(JSON.stringify(LIST), { status: 200 });
      }
      if (url.includes('/validate')) {
        validateCalls.push({ url, body: JSON.parse(String(init?.body)) });
        const encoder = new TextEncoder();
        const stream = new ReadableStream({
          start(controller) {
            controller.enqueue(
              encoder.encode(
                `${JSON.stringify({ type: 'result', valid: true, provider: 'google', steps: [], models: [], error: null })}\n`,
              ),
            );
            controller.close();
          },
        });
        return new Response(stream, { status: 200 });
      }
      if (url.includes('/model-selection')) {
        return new Response(JSON.stringify({ current: null, recent: [], favorite: [] }), { status: 200 });
      }
      if (url.includes('/model') && init?.method === 'POST') {
        setModelCalls.push({ url, body: JSON.parse(String(init?.body)) });
        return new Response(JSON.stringify(LIST.all[7]), { status: 200 });
      }
      if (url.includes('/models')) {
        const seg = url.split('/');
        const pid = seg[seg.length - 2]?.split('?')[0];
        const models = (MODELS as Record<string, unknown>)[pid as string] ?? [];
        return new Response(
          JSON.stringify({ models, total: Array.isArray(models) ? models.length : 0, offset: 0, limit: 100 }),
          { status: 200 },
        );
      }
      if (url.includes('/providers')) {
        return new Response(JSON.stringify(CATALOG), { status: 200 });
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function renderFlow() {
  return render(
    <ThemeProvider>
      <ProviderFlow onClose={() => {}} />
    </ThemeProvider>,
  );
}

describe('ProviderFlow pick -> models -> key -> validate', () => {
  it('searching "goo" selects Google, which loads Google models before the API key', async () => {
    const { stdin, lastFrame, unmount } = renderFlow();
    await wait(150);
    stdin.write('goo');
    await wait(80);
    const frame1 = lastFrame();
    expect(frame1).toContain('Google AI Studio');
    expect(frame1).not.toContain('Anthropic');
    expect(frame1).not.toContain('Groq');

    // Enter selects Google (search and keyboard resolve to the same handler).
    stdin.write('\r');
    await wait(150);
    // Models are fetched from the backend for the selected provider.
    expect(lastFrame()).toContain('Gemini 3.5 Flash-Lite');
    expect(lastFrame()).toContain('Page 1 of 1');

    // Select the default Google model.
    stdin.write('\r');
    await wait(80);
    expect(lastFrame()).toContain('Enter API key');

    stdin.write('AQ.test999');
    await wait(50);
    stdin.write('\r');
    await wait(500);

    const calls = validateCalls.filter((c) => c.url.includes('/validate'));
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain('/google/validate');
    expect(calls[0].body.model).toBe('gemini-3.5-flash-lite');
    expect(calls[0].body.api_key).toBe('AQ.test999');

    // Provider/model only becomes active after successful backend validation.
    expect(setModelCalls.some((c) => c.url.includes('/google/model') && c.body.model === 'gemini-3.5-flash-lite')).toBe(
      true,
    );
    unmount();
  });

  it('searching "an" ranks Anthropic first (regression: pick goes to anthropic)', async () => {
    const { stdin, lastFrame, unmount } = renderFlow();
    await wait(150);
    stdin.write('an');
    await wait(80);
    expect(lastFrame()).toContain('Anthropic');
    expect(lastFrame()).not.toContain('Google AI Studio');

    stdin.write('\r');
    await wait(150);
    // Same shared model selector, fed from the backend for Anthropic.
    expect(lastFrame()).toContain('Claude Sonnet 4');
    unmount();
  });
});
