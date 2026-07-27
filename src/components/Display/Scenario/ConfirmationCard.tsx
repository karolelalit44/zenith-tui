import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { ConfirmationRequestEvent } from '../../../types/scenario';

interface ConfirmationCardProps {
  event: ConfirmationRequestEvent;
}

export const ConfirmationCard: React.FC<ConfirmationCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  const riskColor =
    event.riskLevel === 'high'
      ? theme.colors.status.error
      : event.riskLevel === 'medium'
        ? theme.colors.status.warning
        : theme.colors.status.success;

  const riskLabel =
    event.riskLevel === 'high'
      ? '[HIGH RISK]'
      : event.riskLevel === 'medium'
        ? '[MEDIUM RISK]'
        : '[LOW RISK]';

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box
        flexDirection="column"
        width="100%"
        borderStyle="round"
        borderColor={riskColor}
        paddingX={1}
        paddingY={0}
      >
        <Box flexDirection="row" alignItems="center">
          <Text color={riskColor} bold>
            {riskLabel}{' '}
          </Text>
          <Text color={theme.colors.text.bright}>
            Confirm: {event.tool}
          </Text>
        </Box>
        <Box marginTop={0}>
          <Text color={theme.colors.text.muted}>{event.reason}</Text>
        </Box>

        {event.answered ? (
          <Box marginTop={0}>
            <Text
              color={event.approved ? theme.colors.status.success : theme.colors.status.error}
              bold
            >
              {event.approved ? '✓ Approved' : '✗ Denied'}
            </Text>
          </Box>
        ) : (
          <Box marginTop={0}>
            <Text color={theme.colors.text.bright}>
              Press{' '}
              <Text color={theme.colors.status.success} bold>
                y
              </Text>{' '}
              to approve or{' '}
              <Text color={theme.colors.status.error} bold>
                n
              </Text>{' '}
              to deny
            </Text>
          </Box>
        )}
      </Box>
    </Box>
  );
});
