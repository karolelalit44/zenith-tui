import { Box, Text, useInput } from 'ink';
import React, { Component, type ErrorInfo, type ReactNode, useState } from 'react';
import { useTheme } from '../../theme/ThemeContext';
import { RoundedBox } from './RoundedBox';

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

/**
 * Ink's `useInput` throws when stdin is not a TTY (raw mode unsupported). If the
 * error fallback itself uses `useInput`, a headless run re-throws inside the
 * boundary -> getDerivedStateFromError -> fallback -> throw... until React bails
 * out with "Maximum update depth exceeded" and the whole TUI dies.
 *
 * Fix: pick the fallback once at module load — interactive (useInput) only when
 * stdin is a real TTY, otherwise a static, hook-free panel that cannot re-throw.
 */
const IS_INTERACTIVE_INPUT = typeof process !== 'undefined' && process.stdin?.isTTY === true;

const StaticErrorFallback: React.FC<ErrorFallbackProps> = ({ error }) => {
  const { theme } = useTheme();

  return (
    <RoundedBox title="RUNTIME ERROR" borderColor={theme.colors.status.error} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        <Box marginBottom={1}>
          <Text color={theme.colors.status.error} bold>
            [ERROR] {error.message || 'An unexpected error occurred'}
          </Text>
        </Box>
        <Box paddingX={1} borderStyle="single" borderColor={theme.colors.border.muted}>
          <Text color={theme.colors.text.muted}>
            Interactive input is unavailable (no TTY); restart in a terminal for retry shortcuts.
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};

const InteractiveErrorFallback: React.FC<ErrorFallbackProps> = ({ error, errorInfo, onRetry }) => {
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

const ErrorFallback = IS_INTERACTIVE_INPUT ? InteractiveErrorFallback : StaticErrorFallback;

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };
  private infoCaptured = false;

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack);
    // Capture the component stack exactly once. Calling setState again after the
    // boundary is already showing the fallback re-renders it; if that render
    // throws (e.g. no raw-mode stdin) the boundary catches it again and we loop
    // until React reports "Maximum update depth exceeded".
    if (!this.infoCaptured) {
      this.infoCaptured = true;
      this.setState({ errorInfo: info });
    }
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
