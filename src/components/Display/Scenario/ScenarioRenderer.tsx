import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import { useTickAnimation } from '../../../hooks/useTickAnimation';
import { parseJsonEvent } from '../../../services/data/jsonEventNormalizer';
import { useTheme } from '../../../theme/ThemeContext';
import type { ScenarioEvent } from '../../../types/scenario';
import { componentRegistry } from './componentRegistry';

interface ScenarioRendererProps {
  events: ScenarioEvent[];
  isRunning: boolean;
  isHistorical?: boolean;
}

const SPINNER_FRAMES = ['|', '/', '-', '\\'];

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
          {SPINNER_FRAMES[spinnerTick % 4]}{' '}
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
  ({ events, isRunning, isHistorical = false }) => {
    const [thinkingVisible, setThinkingVisible] = useState(true);

    useInput((char, key) => {
      if (key.shift && (char === 't' || char === 'T')) {
        setThinkingVisible((prev) => !prev);
      }
    });

    const lastEvent = events[events.length - 1];
    const showLiveIndicator =
      isRunning && !isHistorical && (lastEvent?.kind === 'thinking' || lastEvent?.kind === 'waiting');
    const renderContext = {
      thinkingCollapsed: !thinkingVisible,
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
