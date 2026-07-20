import React, { createContext, useContext, useState } from 'react';
import { Theme, themes } from './theme';

interface ThemeContextType {
  theme: Theme;
  activeThemeId: string;
  setTheme: (themeId: string) => void;
}

const ThemeContext = createContext<ThemeContextType>({
  theme: themes.deep_forest,
  activeThemeId: 'deep_forest',
  setTheme: () => {},
});

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [activeThemeId, setActiveThemeId] = useState<string>('deep_forest');
  
  const theme = themes[activeThemeId] || themes.deep_forest;

  const setTheme = (themeId: string) => {
    if (themes[themeId]) {
      setActiveThemeId(themeId);
    }
  };

  return (
    <ThemeContext.Provider value={{ theme, activeThemeId, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => useContext(ThemeContext);
