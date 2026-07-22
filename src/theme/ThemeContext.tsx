import React, { createContext, useContext, useState } from 'react';
import { loadSavedTheme, saveTheme } from '../services/data/userProfileService';
import { type Theme, themes } from './theme';

interface ThemeContextType {
  theme: Theme;
  activeThemeId: string;
  setTheme: (themeId: string) => void;
}

const ThemeContext = createContext<ThemeContextType>({
  theme: themes.graphite,
  activeThemeId: 'graphite',
  setTheme: () => {},
});

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [activeThemeId, setActiveThemeId] = useState<string>(() => loadSavedTheme());

  const theme = themes[activeThemeId] || themes.graphite;

  const setTheme = (themeId: string) => {
    if (themes[themeId]) {
      setActiveThemeId(themeId);
      saveTheme(themeId);
    }
  };

  return <ThemeContext.Provider value={{ theme, activeThemeId, setTheme }}>{children}</ThemeContext.Provider>;
};

export const useTheme = () => useContext(ThemeContext);
