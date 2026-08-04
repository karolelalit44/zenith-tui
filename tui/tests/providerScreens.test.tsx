import { render } from 'ink-testing-library';
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ModelPickerFlow } from '../src/components/Model/ModelPickerFlow';
import { FieldForm, type FormField } from '../src/screens/Provider/FieldForm';
import { ModelPicker } from '../src/screens/Provider/ModelPicker';
import { ProviderFlow } from '../src/screens/Provider/ProviderFlow';
import { providerRepository } from '../src/services/providers/ProviderRepository';
import type { ProviderListResponse } from '../src/services/providers/types';
import { ThemeProvider } from '../src/theme/ThemeContext';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

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

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(LIST), { status: 200 })),
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

    await wait(100);
    expect(lastFrame()).toContain('Choose a provider');
    expect(lastFrame()).toContain('NVIDIA AI');

    stdin.write('o');
    await wait(50);
    expect(lastFrame()).toContain('OpenAI');
    unmount();
  });

  it('renders the ModelPicker as a flat list of models from configured providers only', async () => {
    await providerRepository.fetchProviderList();
    const { lastFrame, unmount } = renderWithTheme(<ModelPicker onSelect={() => {}} onClose={() => {}} />);

    expect(lastFrame()).toContain('Select a model');
    expect(lastFrame()).toContain('NVIDIA AI');
    expect(lastFrame()).toContain('Nemotron 3 Ultra');
    expect(lastFrame()).not.toContain('OpenAI');
    expect(lastFrame()).not.toContain('GPT-4o Mini');
    unmount();
  });

  it('renders the ModelPickerFlow as a single dialog with a View all providers action', async () => {
    await providerRepository.fetchProviderList();
    const onOpenProvider = vi.fn();
    const { lastFrame, stdin, unmount } = renderWithTheme(
      <ModelPickerFlow onClose={() => {}} onOpenProvider={onOpenProvider} />,
    );

    expect(lastFrame()).toContain('MODEL PICKER');
    expect(lastFrame()).toContain('Select a model');
    expect(lastFrame()).toContain('Nemotron 3 Ultra');

    stdin.write('\t');
    await wait(30);
    stdin.write('\r');
    await wait(50);
    expect(onOpenProvider).toHaveBeenCalled();
    unmount();
  });

  it('omits models from unconfigured providers in the model menu', async () => {
    await providerRepository.fetchProviderList();
    const { lastFrame, unmount } = renderWithTheme(<ModelPickerFlow onClose={() => {}} />);

    expect(lastFrame()).toContain('Nemotron 3 Ultra');
    expect(lastFrame()).not.toContain('GPT-4o Mini');
    unmount();
  });
});
