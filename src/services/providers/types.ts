export type ProviderId = 'openrouter' | 'openai' | 'anthropic' | 'gemini' | 'groq' | 'custom';

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
  availableModels?: { id: string; name: string; description?: string }[];
}

export interface ProviderState {
  id: ProviderId;
  meta: ProviderMeta;
  config: ProviderConfig;
  isActive: boolean;
  isConfigured: boolean;
}
