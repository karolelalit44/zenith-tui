import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { FileCreateEvent } from '../../../types/scenario';
import { highlightCode } from '../../../utils/syntaxHighlight';

interface FileDiffCardProps {
  event: FileCreateEvent;
}

const MAX_VISIBLE_LINES = 25;

export const FileDiffCard: React.FC<FileDiffCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const linesToShow = Math.min(event.lines.length, MAX_VISIBLE_LINES);
  const displayLines = event.lines.slice(0, linesToShow);
  const truncated = event.lines.length > MAX_VISIBLE_LINES;
  const ext = event.filePath.split('.').pop() || event.language;

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color={theme.colors.status.success} bold>
          [CREATE] New File
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.bright} bold>
          {event.filePath}
        </Text>
        <Text color={theme.colors.text.muted}> ({event.lines.length} lines)</Text>
      </Box>

      <Box flexDirection="column" width="100%" borderStyle="round" borderColor={theme.colors.code.border} paddingX={1}>
        <Box flexDirection="row" marginBottom={1}>
          <Text color={theme.colors.text.muted}>@@ 0, {event.lines.length} @@ </Text>
          <Text color={theme.colors.status.info}>+{ext}</Text>
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
              <Text wrap="wrap">{highlightCode(line.text, ext)}</Text>
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
