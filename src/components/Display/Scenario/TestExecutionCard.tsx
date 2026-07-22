import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { TestExecutionEvent } from '../../../types/scenario';

interface TestExecutionCardProps {
  event: TestExecutionEvent;
}

export const TestExecutionCard: React.FC<TestExecutionCardProps> = ({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      {/* Header */}
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color={theme.colors.status.success} bold>
          [TEST SUITE]
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.status.info} bold>
          {event.framework}
        </Text>
        <Text color={theme.colors.text.muted}> · </Text>
        <Text color={theme.colors.text.bright} bold>
          {event.command}
        </Text>
      </Box>

      {/* Test Execution Container */}
      <Box
        flexDirection="column"
        width="100%"
        borderStyle="round"
        borderColor={theme.colors.status.success}
        paddingX={2}
        paddingY={1}
      >
        <Box flexDirection="column" marginBottom={1}>
          {event.results.map((result, idx) => (
            <Box key={idx} flexDirection="row" alignItems="center">
              <Box width={3}>
                <Text
                  color={
                    result.status === 'pass'
                      ? theme.colors.status.success
                      : result.status === 'fail'
                        ? theme.colors.status.error
                        : theme.colors.text.muted
                  }
                  bold
                >
                  {result.status === 'pass' ? '✔' : result.status === 'fail' ? '✗' : '○'}
                </Text>
              </Box>
              <Text color={result.status === 'fail' ? theme.colors.status.error : theme.colors.text.ethereal}>
                {result.name}
              </Text>
              {result.duration !== undefined && (
                <Text color={theme.colors.text.muted}> ({(result.duration / 1000).toFixed(2)}s)</Text>
              )}
            </Box>
          ))}
        </Box>

        <Box
          flexDirection="row"
          paddingTop={1}
          borderStyle="single"
          borderTop={true}
          borderColor={theme.colors.border.muted}
        >
          <Text color={theme.colors.text.muted}>{event.summary.total} total tests · </Text>
          <Text color={theme.colors.status.success} bold>
            {event.summary.passed} passed
          </Text>
          {event.summary.failed > 0 && (
            <>
              <Text color={theme.colors.text.muted}> · </Text>
              <Text color={theme.colors.status.error} bold>
                {event.summary.failed} failed
              </Text>
            </>
          )}
          {event.summary.skipped > 0 && (
            <>
              <Text color={theme.colors.text.muted}> · </Text>
              <Text color={theme.colors.text.muted}>{event.summary.skipped} skipped</Text>
            </>
          )}
        </Box>
      </Box>
    </Box>
  );
};
