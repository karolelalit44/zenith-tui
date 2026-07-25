export type ProviderId = 'openrouter' | 'openai' | 'anthropic' | 'google' | 'groq' | 'nvidia' | 'custom';

export interface ProviderConfigField {
  key: string;
  label: string;
  type: 'text' | 'password' | 'select' | 'number';
  placeholder?: string;
  options?: { label: string; value: string }[];
  required?: boolean;
  defaultValue?: string | number;
  description?: string;
}

export interface ProviderConfig {
  apiKey?: string;
  model?: string;
  baseUrl?: string;
  organizationId?: string;
  timeout?: number;
  temperature?: number;
  [key: string]: unknown;
}

export interface ProviderMeta {
  id: ProviderId;
  name: string;
  description: string;
  defaultModel: string;
  swatch: string[];
  fields: ProviderConfigField[];
  availableModels?: ModelInfo[];
}

export interface ModelInfo {
  id: string;
  name: string;
  description?: string;
  context_window?: number;
  parameters?: string;
  architecture?: string;
  input_modalities?: string[];
  output_modalities?: string[];
  tags?: string[];
  model_capabilities?: {
    function_calling?: boolean;
    structured_output?: boolean;
    reasoning?: boolean;
    thinking?: boolean;
  };
  speed_tier?: 'fast' | 'moderate' | 'slow';
  best_for?: string[];
}

export interface ProviderState {
  id: ProviderId;
  meta: ProviderMeta;
  config: ProviderConfig;
  isActive: boolean;
  isConfigured: boolean;
}
