import { Box, Text, useInput } from 'ink';
import React, { Component, type ErrorInfo, type ReactNode, useState } from 'react';
import { useTheme } from '../theme/ThemeContext';
import { RoundedBox } from './ui/RoundedBox';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
  errorInfo?: ErrorInfo;
}

interface ErrorFallbackProps {
  error: Error;
  errorInfo?: ErrorInfo;
  onRetry: () => void;
}

const ErrorFallback: React.FC<ErrorFallbackProps> = ({ error, errorInfo, onRetry }) => {
  const { theme } = useTheme();
  const [showDetails, setShowDetails] = useState(false);

  useInput((_char, key) => {
    if (key.escape) {
      onRetry();
    }
    if (key.tab) {
      setShowDetails((prev) => !prev);
    }
  });

  return (
    <RoundedBox title="RUNTIME ERROR" borderColor={theme.colors.status.error} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        <Box marginBottom={1}>
          <Text color={theme.colors.status.error} bold>
            [ERROR] {error.message || 'An unexpected error occurred'}
          </Text>
        </Box>

        {showDetails && errorInfo && (
          <Box marginBottom={1} paddingX={1} borderStyle="single" borderColor={theme.colors.border.muted}>
            <Text color={theme.colors.text.muted} wrap="wrap">
              {errorInfo.componentStack || 'No stack trace available'}
            </Text>
          </Box>
        )}

        <Box marginTop={1} paddingTop={1} borderStyle="single" borderTop={true} borderColor={theme.colors.border.muted}>
          <Text color={theme.colors.text.muted}>
            <Text color={theme.colors.status.info} bold>
              [Esc]
            </Text>{' '}
            Retry{' · '}
            <Text color={theme.colors.status.info} bold>
              [Tab]
            </Text>{' '}
            {showDetails ? 'Hide' : 'Show'} Details
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack);
    this.setState({ errorInfo: info });
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: undefined, errorInfo: undefined });
  };

  render() {
    if (this.state.hasError && this.state.error) {
      return <ErrorFallback error={this.state.error} errorInfo={this.state.errorInfo} onRetry={this.handleRetry} />;
    }
    return this.props.children;
  }
}
