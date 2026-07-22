import { Box, Text } from 'ink';
// biome-ignore lint/correctness/noUnusedImports: React is required for JSX transform (jsx: "react")
import React, { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <Box flexDirection="column" padding={1}>
          <Text color="red">An error occurred</Text>
          <Text>{this.state.error?.message}</Text>
        </Box>
      );
    }
    return this.props.children;
  }
}
