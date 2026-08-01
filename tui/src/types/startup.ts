export type StartupStatus = 'ready' | 'configuration_required' | 'loading' | 'error';

export type MissingItem = 'provider' | 'model' | 'apiKey' | 'configFile' | 'workspace' | 'dbPath';

export interface StartupResult {
  status: StartupStatus;
  missing: MissingItem[];
  active_provider: string;
  active_model: string;
  provider_count: number;
  message: string;
}

export interface ProviderSetupRequest {
  provider: string;
  api_key: string;
  model: string;
  base_url: string;
  max_tokens: number;
  temperature: number;
}

export interface ProviderSetupResult {
  valid: boolean;
  provider: string;
  model: string;
  message: string;
}

export interface AppStartupState {
  phase: 'loading' | 'setup' | 'ready' | 'error';
  result: StartupResult | null;
  error: string | null;
}
