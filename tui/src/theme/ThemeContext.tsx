import React, { createContext, useContext, useEffect, useState } from 'react';
import { loadUserProfile, saveUserProfile } from '../services/api/userProfileService';
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

  useEffect(() => {
    saveUserProfile({ settings: { ...loadUserProfile().settings, theme: activeThemeId } });
  }, [activeThemeId]);

  const theme = themes[activeThemeId] || themes[DEFAULT_THEME];

  const setTheme = (themeId: string) => {
    if (themes[themeId]) {
      setActiveThemeId(themeId);
    }
  };

  return <ThemeContext.Provider value={{ theme, activeThemeId, setTheme }}>{children}</ThemeContext.Provider>;
};

export const useTheme = () => useContext(ThemeContext);
