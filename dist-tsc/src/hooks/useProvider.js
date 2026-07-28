import { useEffect, useState } from 'react';
import { providerService } from '../services/providers/ProviderService';
export function useProvider() {
    const [activeProvider, setActiveProviderState] = useState(() => providerService.getActiveProvider());
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
