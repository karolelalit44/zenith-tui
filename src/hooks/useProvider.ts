import { useEffect, useState } from 'react';
import { providerService } from '../services/providers/ProviderService';
import type { ProviderState } from '../services/providers/types';

export interface UseProviderReturn {
  activeProvider: ProviderState;
  allProviders: ProviderState[];
  setActiveProvider: (id: ProviderState['id']) => void;
}

export function useProvider(): UseProviderReturn {
  const [activeProvider, setActiveProviderState] = useState<ProviderState>(() => providerService.getActiveProvider());

  useEffect(() => {
    const unsubscribe = providerService.subscribe((state) => {
      setActiveProviderState(state);
    });
    return unsubscribe;
  }, []);

  const setActiveProvider = (id: ProviderState['id']) => {
    const updated = providerService.setActiveProvider(id);
    setActiveProviderState(updated);
  };

  const allProviders = providerService.getAllProviders();

  return {
    activeProvider,
    allProviders,
    setActiveProvider,
  };
}
