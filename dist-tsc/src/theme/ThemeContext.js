import React, { createContext, useContext, useState } from 'react';
import { themes } from './theme';
const ThemeContext = createContext({
    theme: themes.graphite,
    activeThemeId: 'graphite',
    setTheme: () => { },
});
export const ThemeProvider = ({ children }) => {
    const [activeThemeId, setActiveThemeId] = useState('graphite');
    const theme = themes[activeThemeId] || themes.graphite;
    const setTheme = (themeId) => {
        if (themes[themeId]) {
            setActiveThemeId(themeId);
        }
    };
    return React.createElement(ThemeContext.Provider, { value: { theme, activeThemeId, setTheme } }, children);
};
export const useTheme = () => useContext(ThemeContext);
