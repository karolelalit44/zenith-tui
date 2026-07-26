import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { SuccessEvent } from '../../../types/scenario';

interface SuccessCardProps {
  event: SuccessEvent;
}

export const SuccessCard: React.FC<SuccessCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();

  const details: string[] = [];
  if (event.iterations !== undefined) {
    details.push(`${event.iterations} iter${event.iterations === 1 ? '' : 's'}`);
  }
  if (event.tokenInfo) {
    details.push(`${event.tokenInfo.used} tokens (${Math.round(event.tokenInfo.percent * 100)}%)`);
  }
  if (event.filesCreated && event.filesCreated.length > 0) {
    details.push(`${event.filesCreated.length} file${event.filesCreated.length === 1 ? '' : 's'} created`);
  }
  if (event.commandsExecuted && event.commandsExecuted.length > 0) {
    details.push(`${event.commandsExecuted.length} cmd${event.commandsExecuted.length === 1 ? '' : 's'}`);
  }

  // For file_read and similar tools, show the result output
  const toolOutput = event.result?.output || '';
  const toolName = event.tool || '';
  const isFileRead = toolName === 'file_read';
  const hasOutput = toolOutput.length > 0;

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box
        flexDirection="row"
        width="100%"
        borderStyle="round"
        borderColor={theme.colors.status.success}
        alignItems="center"
        justifyContent="space-between"
        paddingX={1}
        paddingY={0}
      >
        <Box flexDirection="row" alignItems="center" flexShrink={1}>
          <Text color={theme.colors.status.success} bold>
            ✓ [SUCCESS]{' '}
          </Text>
          <Text color={theme.colors.text.bright}>{event.message || 'Completed successfully'}</Text>
        </Box>

        {details.length > 0 && (
          <Box flexDirection="row" alignItems="center" flexShrink={0} paddingLeft={2}>
            <Text color={theme.colors.text.muted}>{details.join(' · ')}</Text>
          </Box>
        )}
      </Box>

      {/* Show file content for file_read and other tools with output */}
      {isFileRead && hasOutput && (
        <Box
          flexDirection="column"
          width="100%"
          borderStyle="round"
          borderColor={theme.colors.text.muted}
          paddingX={1}
          marginTop={1}
        >
          {toolOutput.split('\n').slice(0, 50).map((line, i) => (
            <Text key={i} color={theme.colors.text.bright} wrap="wrap">
              {line}
            </Text>
          ))}
          {toolOutput.split('\n').length > 50 && (
            <Text color={theme.colors.text.muted}>
              ... ({toolOutput.split('\n').length - 50} more lines)
            </Text>
          )}
        </Box>
      )}
    </Box>
  );
});
