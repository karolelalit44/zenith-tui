import { render } from 'ink';
// biome-ignore lint/correctness/noUnusedImports: React is required for JSX transform (jsx: "react")
import React from 'react';
import { App } from './App';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import { ThemeProvider } from './theme/ThemeContext';

render(
  <ThemeProvider>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </ThemeProvider>,
);
