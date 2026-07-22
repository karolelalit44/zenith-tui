import React, { createContext, useContext, useState, useCallback } from 'react';
import { Screen, NavigationState, NavigationContextType } from '../types';

const NavigationContext = createContext<NavigationContextType | undefined>(undefined);

export const NavigationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [state, setState] = useState<NavigationState>({
    currentScreen: 'welcome',
    history: [],
  });

  const navigate = useCallback((screen: Screen) => {
    setState(prev => ({
      currentScreen: screen,
      history: [...prev.history, prev.currentScreen],
    }));
  }, []);

  const goBack = useCallback(() => {
    setState(prev => {
      if (prev.history.length === 0) return prev;
      const newHistory = [...prev.history];
      const previousScreen = newHistory.pop()!;
      return {
        currentScreen: previousScreen,
        history: newHistory,
      };
    });
  }, []);

  const canGoBack = state.history.length > 0;

  return (
    <NavigationContext.Provider value={{ state, navigate, goBack, canGoBack }}>
      {children}
    </NavigationContext.Provider>
  );
};

export const useNavigation = (): NavigationContextType => {
  const context = useContext(NavigationContext);
  if (!context) {
    throw new Error('useNavigation must be used within a NavigationProvider');
  }
  return context;
};
