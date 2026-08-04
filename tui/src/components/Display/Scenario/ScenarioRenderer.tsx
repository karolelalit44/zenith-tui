import { Box, Text } from 'ink';
import React, { Component, type ReactNode, useMemo } from 'react';
import { SPINNER_FRAMES } from '../../../constants/animation';
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

function formatElapsedLive(ms: number): string {
  const totalSec = Math.floor(ms / 1000);
  if (totalSec < 60) return `${totalSec}s`;
  const mins = Math.floor(totalSec / 60);
  const secs = totalSec % 60;
  if (mins < 60) return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
  const hrs = Math.floor(mins / 60);
  const remMins = mins % 60;
  return remMins > 0 ? `${hrs}h ${remMins}m` : `${hrs}h`;
}

const LiveSpinner: React.FC<{ label: string }> = React.memo(() => {
  const spinnerTick = useTickAnimation(100);
  const { theme } = useTheme();

  const spinnerChar = SPINNER_FRAMES[spinnerTick % SPINNER_FRAMES.length];
  const elapsedMs = spinnerTick * 100;
  const elapsedStr = formatElapsedLive(elapsedMs);

  return (
    <Box flexDirection="row" alignItems="center" width="100%" paddingX={1} marginBottom={1}>
      {}
      <Text color={theme.colors.status.accent} bold>
        {spinnerChar}{' '}
      </Text>
      <Text color={theme.colors.text.bright} bold>
        Working
      </Text>
      <Text color={theme.colors.text.dim}> · </Text>
      <Text color={theme.colors.text.muted}>{elapsedStr}</Text>

      {}
      <Box flexGrow={1} />
      <Text color={theme.colors.text.dim}>esc to interrupt</Text>
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

    const dynamicLimit = 20;
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
