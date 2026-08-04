import { render } from 'ink';
// biome-ignore lint/correctness/noUnusedImports: React is required for JSX transform (jsx: "react")
import React from 'react';
import { App } from './App';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import { wsClient } from './services/transport/WebSocketClient';
import { ThemeProvider } from './theme/ThemeContext';

const app = render(
  <ThemeProvider>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </ThemeProvider>,
);

// Graceful shutdown — close the WebSocket (and stop it reconnecting) and tear
// down the Ink renderer before the process exits on SIGINT/SIGTERM. Guarded so
// repeated signals only trigger it once.
let shuttingDown = false;
const shutdown = (): void => {
  if (shuttingDown) return;
  shuttingDown = true;
  void wsClient
    .close()
    .catch(() => {})
    .finally(() => {
      app.unmount();
      process.exit(0);
    });
};

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
