import { Box, Text } from 'ink';
import React, { Component, type ReactNode, useMemo } from 'react';
import { ASCII_SPINNER_FRAMES } from '../../../constants/animation';
import { useTickAnimation } from '../../../hooks/useTickAnimation';
import { useTheme } from '../../../theme/ThemeContext';
import type { ScenarioEvent } from '../../../types/scenario';
import { componentRegistry } from './componentRegistry';

interface ScenarioRendererProps {
  events: ScenarioEvent[];
  isRunning: boolean;
  isHistorical?: boolean;
  thinkingCollapsed?: boolean;
  onRetry?: () => void;
  onDismiss?: () => void;
}

const LiveSpinner: React.FC<{ label: string }> = React.memo(({ label }) => {
  const spinnerTick = useTickAnimation(100);
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" flexWrap="wrap">
        <Text color={theme.colors.status.info} bold>
          [IN PROGRESS]{' '}
        </Text>
        <Text color={theme.colors.status.success} bold>
          {ASCII_SPINNER_FRAMES[spinnerTick % ASCII_SPINNER_FRAMES.length]}{' '}
        </Text>
        <Text color={theme.colors.text.bright} bold>
          {label}
        </Text>
        <Text color={theme.colors.text.muted}> (Press ESC to cancel)</Text>
      </Box>
    </Box>
  );
});

class EventErrorBoundary extends Component<
  { children: ReactNode; eventKind: string; errorColor: string },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <Box paddingX={1} marginBottom={1}>
          <Text color={this.props.errorColor}>[Render error in {this.props.eventKind} event — skipped]</Text>
        </Box>
      );
    }
    return this.props.children;
  }
}

export const ScenarioRenderer: React.FC<ScenarioRendererProps> = React.memo(
  ({ events, isRunning, isHistorical = false, thinkingCollapsed = false, onRetry, onDismiss }) => {
    const { theme } = useTheme();
    const showLiveIndicator = isRunning && !isHistorical;

    const renderContext = useMemo(
      () => ({
        thinkingCollapsed,
        isHistorical,
        isRunning,
        onRetry,
        onDismiss,
      }),
      [thinkingCollapsed, isHistorical, isRunning, onRetry, onDismiss],
    );

    // Use a small limit for dynamic rendering to avoid Ink scrolling bugs.
    // For historical (Static) renders, show all events.
    const dynamicLimit = 8;
    const hasOverflow = !isHistorical && events.length > dynamicLimit;
    const visibleEvents = hasOverflow ? events.slice(-dynamicLimit) : events;

    return (
      <Box flexDirection="column" width="100%">
        {hasOverflow && (
          <Box paddingX={1} marginBottom={1}>
            <Text color={theme.colors.text.muted} italic>
              ... {events.length - dynamicLimit} earlier events hidden
            </Text>
          </Box>
        )}

        {visibleEvents.map((event) => {
          const Component = componentRegistry.getComponent(event.kind);
          return (
            <EventErrorBoundary key={event.id} eventKind={event.kind} errorColor={theme.colors.status.warning}>
              <Component event={event} context={renderContext} />
            </EventErrorBoundary>
          );
        })}

        {showLiveIndicator && <LiveSpinner label={''} />}
      </Box>
    );
  },
);
