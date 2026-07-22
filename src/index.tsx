import React from 'react';
import { render } from 'ink';
import { App } from './App';
import { ThemeProvider } from './theme/ThemeContext';
import { NavigationProvider } from './navigation';

render(
  <ThemeProvider>
    <NavigationProvider>
      <App />
    </NavigationProvider>
  </ThemeProvider>
);
