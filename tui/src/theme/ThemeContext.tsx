import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { loadUserProfile, onProfileHydrated, saveUserProfile } from '../services/api/userProfileService';
import { type Theme, themes } from './theme';

interface ThemeContextType {
  theme: Theme;
  activeThemeId: string;
  setTheme: (themeId: string) => void;
}

const DEFAULT_THEME = 'graphite';

const ThemeContext = createContext<ThemeContextType>({
  theme: themes[DEFAULT_THEME],
  activeThemeId: DEFAULT_THEME,
  setTheme: () => {},
});

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const initialTheme = loadUserProfile().settings.theme || DEFAULT_THEME;
  const [activeThemeId, setActiveThemeId] = useState<string>(themes[initialTheme] ? initialTheme : DEFAULT_THEME);
  // Skips the persist-write triggered by the initial state value; also gates
  // hydration adoption so a local user change always wins afterwards.
  const mountedRef = useRef(false);
  const adoptedServerThemeRef = useRef(false);

  // The server-owned profile may hydrate after mount; adopt its stored theme
  // exactly once. Any local setTheme() afterwards always wins.
  useEffect(() => {
    onProfileHydrated((p) => {
      if (adoptedServerThemeRef.current) return;
      const t = p.settings.theme;
      if (t && themes[t]) {
        adoptedServerThemeRef.current = true;
        setActiveThemeId(t);
      }
    });
  }, []);

  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return;
    }
    saveUserProfile({ settings: { ...loadUserProfile().settings, theme: activeThemeId } });
  }, [activeThemeId]);

  const theme = themes[activeThemeId] || themes[DEFAULT_THEME];

  const setTheme = (themeId: string) => {
    if (themes[themeId]) {
      adoptedServerThemeRef.current = true;
      setActiveThemeId(themeId);
    }
  };

  return <ThemeContext.Provider value={{ theme, activeThemeId, setTheme }}>{children}</ThemeContext.Provider>;
};

export const useTheme = () => useContext(ThemeContext);
