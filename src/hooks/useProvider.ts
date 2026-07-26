import { useEffect, useState } from 'react';
import { providerService } from '../services/providers/ProviderService';
import type { ProviderState } from '../services/providers/types';

export function useProvider(): { activeProvider: ProviderState } {
  const [activeProvider, setActiveProviderState] = useState<ProviderState>(() => providerService.getActiveProvider());

  useEffect(() => {
    providerService.refreshFromBackend().then(() => {
      setActiveProviderState(providerService.getActiveProvider());
    });
    const unsubscribe = providerService.subscribe((state) => {
      setActiveProviderState(state);
    });
    return unsubscribe;
  }, []);

  return { activeProvider };
}
