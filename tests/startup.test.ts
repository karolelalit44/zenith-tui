import { describe, expect, it } from 'vitest';
import { ProviderRepository } from '../src/modules/providers/ProviderRepository';
import { ProviderService } from '../src/modules/providers/ProviderService';
import { StartupService } from '../src/services/data/StartupService';

describe('StartupService Initialization', () => {
  it('bootstraps application configuration and active provider', () => {
    const repo = new ProviderRepository();
    const providerSvc = new ProviderService(repo);
    const startupSvc = new StartupService(providerSvc);

    const result = startupSvc.initialize();

    expect(result.initialized).toBe(true);
    expect(result.profile).toBeDefined();
    expect(result.activeProviderId).toBeDefined();
    expect(typeof result.timestamp).toBe('string');
  });
});
