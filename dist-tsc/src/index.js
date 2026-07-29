import { render } from 'ink';
// biome-ignore lint/correctness/noUnusedImports: React is required for JSX transform (jsx: "react")
import React from 'react';
import { App } from './App';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ThemeProvider } from './theme/ThemeContext';
render(React.createElement(ThemeProvider, null,
    React.createElement(ErrorBoundary, null,
        React.createElement(App, null))));
