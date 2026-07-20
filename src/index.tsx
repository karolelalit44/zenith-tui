import React from 'react';
import { render } from 'ink';
import { App } from './App';
import { ThemeProvider } from './theme/ThemeContext';

render(
  <ThemeProvider>
    <App />
  </ThemeProvider>
);
