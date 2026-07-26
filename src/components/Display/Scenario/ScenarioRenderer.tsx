import { Box, Text } from 'ink';
import React, { Component, type ReactNode } from 'react';
import { ASCII_SPINNER_FRAMES } from '../../../constants/animation';
import { useTickAnimation } from '../../../hooks/useTickAnimation';
import { parseJsonEvent } from '../../../services/data/jsonEventNormalizer';
import { useTheme } from '../../../theme/ThemeContext';
import type { ScenarioEvent } from '../../../types/scenario';
import { componentRegistry } from './componentRegistry';

interface ScenarioRendererProps {
  events: ScenarioEvent[];
  isRunning: boolean;
  isHistorical?: boolean;
  thinkingCollapsed?: boolean;
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
          {ASCII_SPINNER_FRAMES[spinnerTick % 4]}{' '}
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
  { children: ReactNode; eventKind: string },
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
          <Text color="yellow">[Render error in {this.props.eventKind} event — skipped]</Text>
        </Box>
      );
    }
    return this.props.children;
  }
}

export const ScenarioRenderer: React.FC<ScenarioRendererProps> = React.memo(
  ({ events, isRunning, isHistorical = false, thinkingCollapsed = false }) => {
    const showLiveIndicator = isRunning && !isHistorical;
    const renderContext = {
      thinkingCollapsed,
      isHistorical,
      isRunning,
    };

    return (
      <Box flexDirection="column" width="100%">
        {events.map((rawEvt) => {
          const event = parseJsonEvent(rawEvt);
          const Component = componentRegistry.getComponent(event.kind);
          return (
            <EventErrorBoundary key={event.id} eventKind={event.kind}>
              <Component event={event} context={renderContext} />
            </EventErrorBoundary>
          );
        })}

        {showLiveIndicator && <LiveSpinner label="Processing event stream..." />}
      </Box>
    );
  },
);
