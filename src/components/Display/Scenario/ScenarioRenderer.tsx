import { Box, Text } from 'ink';
import React from 'react';
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

          return <Component key={event.id} event={event} context={renderContext} />;
        })}

        {showLiveIndicator && <LiveSpinner label="Processing event stream..." />}
      </Box>
    );
  },
);
