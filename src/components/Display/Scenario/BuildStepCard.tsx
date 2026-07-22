import React, { useState, useEffect } from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { BuildStepEvent } from '../../../types/scenario';

interface BuildStepCardProps {
  event: BuildStepEvent;
  isHistorical?: boolean;
}

export const BuildStepCard: React.FC<BuildStepCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (event.status === 'running') {
      const interval = setInterval(() => setTick(t => t + 1), 150);
      return () => clearInterval(interval);
    }
  }, [event.status]);

  const spinners = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

  let icon: string;
  let color: string;
  switch (event.status) {
    case 'success':
      icon = '✔';
      color = '#3FB950';
      break;
    case 'running':
      icon = spinners[tick % spinners.length];
      color = '#58A6FF';
      break;
    case 'error':
      icon = '✗';
      color = '#F85149';
      break;
    default:
      icon = '○';
      color = '#8B949E';
      break;
  }

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" flexWrap="wrap">
        <Box width={2} flexShrink={0}>
          <Text color={color} bold>{icon}</Text>
        </Box>
        <Text color="#E6EDF3" bold>{event.step}</Text>
        {event.duration !== undefined && (
          <Text color="#8B949E"> ({(event.duration / 1000).toFixed(1)}s)</Text>
        )}
      </Box>

      {event.output && event.output.length > 0 && (
        <Box flexDirection="column" paddingLeft={2} marginTop={0} width="100%">
          {event.output.map((line, idx) => (
            <Text key={idx} color="#C9D1D9" wrap="wrap">│ {line}</Text>
          ))}
        </Box>
      )}
    </Box>
  );
});
