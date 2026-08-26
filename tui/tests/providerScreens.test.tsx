import { render } from 'ink-testing-library';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FieldForm, type FormField } from '../src/screens/Provider/FieldForm';
import { ModelPicker } from '../src/screens/Provider/ModelPicker';
import { ProviderFlow } from '../src/screens/Provider/ProviderFlow';
import { providerRepository } from '../src/services/providers/ProviderRepository';
import type { ProviderListResponse, ProviderState } from '../src/services/providers/types';
import { ThemeProvider } from '../src/theme/ThemeContext';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Poll lastFrame() until predicate matches; returns the matching frame or throws. */
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

/** Poll a boolean predicate (e.g. a vi.fn() call count) until true or throws. */
const pollUntil = async (predicate: () => boolean, message: string, timeoutMs = 5000): Promise<void> => {
  const start = Date.now();
  while (!predicate()) {
    if (Date.now() - start >= timeoutMs) throw new Error(`Timed out waiting for: ${message}`);
    await wait(25);
  }
};

const LIST: ProviderListResponse = {
  all: [
    {
      id: 'nvidia',
      name: 'NVIDIA AI',
      description: '',
      adapter: 'nvidia',
      swatch: [],
      capabilities: {},
      api_key_prefix: null,
      requires_api_key: true,
      config_fields: [],
      options: {},
      has_api_key: true,
      api_key_masked: '',
      validation_status: 'validated',
      last_validation_error: '',
      is_active: true,
      model: 'nvidia/nemotron-3-ultra-550b-a55b',
      models: {
        'nvidia/nemotron-3-ultra-550b-a55b': {
          id: 'nvidia/nemotron-3-ultra-550b-a55b',
          name: 'Nemotron 3 Ultra',
          context_window: 256000,
          description: 'Flagship model',
          is_default: true,
        },
        'nvidia/nemotron-3-mini-4b': {
          id: 'nvidia/nemotron-3-mini-4b',
          name: 'Nemotron 3 Mini',
          context_window: 131072,
          description: 'Small fast model',
          is_default: false,
        },
      },
    },
    {
      id: 'openai',
      name: 'OpenAI',
      description: '',
      adapter: 'openai_compat',
      swatch: [],
      capabilities: {},
      api_key_prefix: null,
      requires_api_key: true,
      config_fields: [],
      options: {},
      has_api_key: false,
      api_key_masked: '',
      validation_status: 'unconfigured',
      last_validation_error: '',
      is_active: false,
      model: 'gpt-4o-mini',
      models: {
        'gpt-4o-mini': {
          id: 'gpt-4o-mini',
          name: 'GPT-4o Mini',
          context_window: 128000,
          description: '',
          is_default: true,
        },
      },
    },
  ],
  active: 'nvidia',
  connected: ['nvidia'],
};

function renderWithTheme(node: React.ReactNode) {
  return render(<ThemeProvider>{node}</ThemeProvider>);
}

const CATALOG: Array<{ id: string; name: string; type: string }> = [
  { id: 'nvidia', name: 'NVIDIA AI', type: 'default' },
  { id: 'openai', name: 'OpenAI', type: 'default' },
  { id: 'custom', name: 'Custom OpenAI-Compatible', type: 'custom' },
];

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/startup/')) return new Response(JSON.stringify(LIST), { status: 200 });
      if (url.includes('/models')) {
        return new Response(JSON.stringify({ models: [], total: 0, offset: 0, limit: 100 }), { status: 200 });
      }
      if (url.includes('/providers')) return new Response(JSON.stringify(CATALOG), { status: 200 });
      return new Response(JSON.stringify(LIST), { status: 200 });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Provider screens', () => {
  it('renders the FieldForm with required-field validation hint', async () => {
    const fields: FormField[] = [
      { key: 'apiKey', label: 'API Key', type: 'password', required: true },
      { key: 'baseUrl', label: 'Base URL', type: 'text' },
    ];
    const { lastFrame, unmount } = renderWithTheme(
      <FieldForm title="Enter API key" fields={fields} onSubmit={() => {}} onCancel={() => {}} />,
    );
    expect(lastFrame()).toContain('Enter API key');
    expect(lastFrame()).toContain('API Key *');
    expect(lastFrame()).toContain('Base URL');
    unmount();
  });

  it('renders the ProviderFlow picker with SQL-backed providers', async () => {
    const { lastFrame, stdin, unmount } = renderWithTheme(<ProviderFlow onClose={() => {}} />);

    expect(lastFrame()).toContain('Choose a provider');
    await pollForFrame(
      () => lastFrame(),
      (f) => f.includes('NVIDIA AI'),
      'provider catalog rendered',
    );

    stdin.write('o');
    await pollForFrame(
      () => lastFrame(),
      (f) => f.includes('OpenAI'),
      'filter narrowed to OpenAI',
    );
    unmount();
  });
  it('renders the inline ModelPicker from the provider catalog models', async () => {
    const provider: ProviderState = {
      id: 'nvidia',
      meta: {
        id: 'nvidia',
        name: 'NVIDIA AI',
        description: '',
        defaultModel: 'nvidia/nemotron-3-ultra-550b-a55b',
        fields: [],
        availableModels: [
          { id: 'nvidia/nemotron-3-ultra-550b-a55b', name: 'Nemotron 3 Ultra' },
          { id: 'nvidia/other', name: 'Other Model' },
        ],
      },
      config: {},
      isActive: false,
      isConfigured: false,
      isPopular: false,
      isCustomFlow: false,
      baseUrlStyle: '',
      supportsPromptCaching: false,
      supportsThinkingHeaders: false,
    };
    const { lastFrame, unmount } = renderWithTheme(
      <ModelPicker provider={provider} onSelect={() => {}} onClose={() => {}} />,
    );

    expect(lastFrame()).toContain('Choose a model');
    await pollForFrame(
      () => lastFrame(),
      (f) => f.includes('Nemotron 3 Ultra'),
      'model list rendered',
    );
    expect(lastFrame()).toContain('Other Model');
    unmount();
  });
});
