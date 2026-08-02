import { render } from 'ink-testing-library';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FieldForm, type FormField } from '../src/screens/Provider/FieldForm';
import { ModelPicker } from '../src/screens/Provider/ModelPicker';
import { ProviderFlow } from '../src/screens/Provider/ProviderFlow';
import { providerRepository } from '../src/services/providers/ProviderRepository';
import { ThemeProvider } from '../src/theme/ThemeContext';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function renderWithTheme(node: React.ReactNode) {
  return render(<ThemeProvider>{node}</ThemeProvider>);
}

afterEach(() => {
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

  it('renders the ProviderFlow picker with catalog providers', async () => {
    // No real backend: refreshFromBackend resolves to null, list stays on the
    // catalog fallback so the picker always has options.
    vi.spyOn(providerRepository, 'fetchProviderList').mockResolvedValue(null);
    const { lastFrame, stdin, unmount } = renderWithTheme(<ProviderFlow onClose={() => {}} />);

    await wait(50);
    expect(lastFrame()).toContain('Choose a provider');
    expect(lastFrame()).toContain('NVIDIA AI');

    stdin.write('o');
    await wait(50);
    expect(lastFrame()).toContain('OpenAI');
    unmount();
  });

  it('renders the ModelPicker with the active provider model', async () => {
    vi.spyOn(providerRepository, 'fetchProviderList').mockResolvedValue({
      all: [],
      default: { active: 'nvidia' },
      connected: ['nvidia'],
    });
    const { lastFrame, unmount } = renderWithTheme(<ModelPicker onSelect={() => {}} onClose={() => {}} />);
    expect(lastFrame()).toContain('Select a model');
    unmount();
  });
});
