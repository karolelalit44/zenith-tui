import { ProviderService, providerService } from '../providers/ProviderService';
import { loadUserProfile, saveUserProfile, UserProfile } from './userProfileService';

export interface StartupResult {
  initialized: boolean;
  profile: UserProfile;
  activeProviderId: string;
  timestamp: string;
}

export class StartupService {
  private providerSvc: ProviderService;

  constructor(providerSvc: ProviderService = providerService) {
    this.providerSvc = providerSvc;
  }

  public initialize(): StartupResult {
    // 1. Check & load user profile configuration
    const profile = loadUserProfile();

    // 2. Ensure default active provider exists in profile
    if (!profile.activeProvider) {
      saveUserProfile({ activeProvider: 'openai' });
    }

    // 3. Initialize ProviderService state
    const activeProviderState = this.providerSvc.getActiveProvider();

    // 4. Return startup metadata summary
    return {
      initialized: true,
      profile,
      activeProviderId: activeProviderState.id,
      timestamp: new Date().toISOString(),
    };
  }
}

export const startupService = new StartupService();
