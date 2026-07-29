import React, { createContext, useContext, useEffect, useState } from 'react';
import { loadUserProfile, saveUserProfile } from '../services/data/userProfileService';
import { themes } from './theme';
const DEFAULT_THEME = 'graphite';
const ThemeContext = createContext({
    theme: themes[DEFAULT_THEME],
    activeThemeId: DEFAULT_THEME,
    setTheme: () => { },
});
export const ThemeProvider = ({ children }) => {
    const initialTheme = loadUserProfile().settings.theme || DEFAULT_THEME;
    const [activeThemeId, setActiveThemeId] = useState(themes[initialTheme] ? initialTheme : DEFAULT_THEME);
    useEffect(() => {
        saveUserProfile({ settings: { ...loadUserProfile().settings, theme: activeThemeId } });
    }, [activeThemeId]);
    const theme = themes[activeThemeId] || themes[DEFAULT_THEME];
    const setTheme = (themeId) => {
        if (themes[themeId]) {
            setActiveThemeId(themeId);
        }
    };
    return React.createElement(ThemeContext.Provider, { value: { theme, activeThemeId, setTheme } }, children);
};
export const useTheme = () => useContext(ThemeContext);
