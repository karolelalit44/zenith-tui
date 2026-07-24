import { Box, Text } from 'ink';
import React from 'react';
import { ASCII_SPINNER_FRAMES } from '../../../constants/animation';
import { useTickAnimation } from '../../../hooks/useTickAnimation';
import { useTheme } from '../../../theme/ThemeContext';
import type { FileCreateEvent } from '../../../types/scenario';
import { highlightCode } from '../../../utils/syntaxHighlight';
import type { EventRenderContext } from './componentRegistry';

interface FileDiffCardProps {
  event: FileCreateEvent;
  context?: EventRenderContext;
}

const MAX_VISIBLE_LINES = 25;

export const FileDiffCard: React.FC<FileDiffCardProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();
  const spinnerTick = useTickAnimation(100);
  const isLive = context?.isRunning && !context?.isHistorical;
  const linesToShow = Math.min(event.lines.length, MAX_VISIBLE_LINES);
  const displayLines = event.lines.slice(0, linesToShow);
  const truncated = event.lines.length > MAX_VISIBLE_LINES;
  const displayPath = event.filePath.includes('/')
    ? event.filePath.split('/').slice(-2).join('/')
    : event.filePath;

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color={isLive ? theme.colors.status.info : theme.colors.status.success} bold>
          {isLive ? `[WRITING FILE] ${ASCII_SPINNER_FRAMES[spinnerTick % 4]}` : '[CREATE] New File'}
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.bright} bold>
          {displayPath}
        </Text>
        <Text color={theme.colors.text.muted}> ({event.lines.length} lines)</Text>
      </Box>

      <Box flexDirection="column" width="100%" borderStyle="single" borderColor={theme.colors.border.muted} paddingX={1}>
        <Box flexDirection="row" marginBottom={1}>
          <Text color={theme.colors.text.muted}>@@ 0, {event.lines.length} @@ </Text>
          <Text color={theme.colors.status.info}>+{event.filePath.split('.').pop() || event.language}</Text>
        </Box>

        {displayLines.map((line, idx) => (
          <Box key={idx} flexDirection="row" width="100%">
            <Box width={4} flexShrink={0}>
              <Text color={theme.colors.code.lineNum}>{idx + 1}</Text>
            </Box>
            <Box width={2} flexShrink={0}>
              <Text color={theme.colors.diff.addFg}>+</Text>
            </Box>
            <Box flexShrink={1}>
              <Text wrap="wrap">{highlightCode(line.text, event.filePath.split('.').pop() || event.language)}</Text>
            </Box>
          </Box>
        ))}

        {truncated && (
          <Box flexDirection="row" marginTop={1}>
            <Text color={theme.colors.text.muted}> ... {event.lines.length - MAX_VISIBLE_LINES} more lines</Text>
          </Box>
        )}
      </Box>
    </Box>
  );
});
