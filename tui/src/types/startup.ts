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

export interface AppStartupState {
  phase: 'loading' | 'setup' | 'ready' | 'error';
  result: StartupResult | null;
  error: string | null;
}
