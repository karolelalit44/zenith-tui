import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { FileEditEvent } from '../../../types/scenario';
import { highlightCode } from '../../../utils/syntaxHighlight';

interface FileEditDiffCardProps {
  event: FileEditEvent;
}

const MAX_VISIBLE_LINES = 25;

export const FileEditDiffCard: React.FC<FileEditDiffCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const totalLines = event.removedLines.length + event.addedLines.length;
  const ext = event.filePath.split('.').pop() || event.language;

  const visibleRemoved = event.removedLines.slice(0, MAX_VISIBLE_LINES);
  const remainingBudget = MAX_VISIBLE_LINES - visibleRemoved.length;
  const visibleAdded = event.addedLines.slice(0, remainingBudget);
  const hiddenCount = totalLines - (visibleRemoved.length + visibleAdded.length);

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color={theme.colors.status.warning} bold>
          [MODIFY]
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.bright} bold>
          {event.filePath}
        </Text>
        <Text color={theme.colors.text.muted}>
          {' '}
          (-{event.removedLines.length} +{event.addedLines.length})
        </Text>
      </Box>

      <Box flexDirection="column" width="100%" borderStyle="round" borderColor={theme.colors.code.border} paddingX={1}>
        {visibleRemoved.map((line, idx) => (
          <Box key={`rm-${idx}`} flexDirection="row" width="100%">
            <Box width={4} flexShrink={0}>
              <Text color={theme.colors.code.lineNum}>{idx + 1}</Text>
            </Box>
            <Box width={2} flexShrink={0}>
              <Text color={theme.colors.diff.removeFg}>-</Text>
            </Box>
            <Box flexShrink={1}>
              <Text color={theme.colors.diff.removeFg} strikethrough wrap="wrap">
                {line.text}
              </Text>
            </Box>
          </Box>
        ))}

        {visibleAdded.map((line, idx) => (
          <Box key={`add-${idx}`} flexDirection="row" width="100%">
            <Box width={4} flexShrink={0}>
              <Text color={theme.colors.code.lineNum}>{visibleRemoved.length + idx + 1}</Text>
            </Box>
            <Box width={2} flexShrink={0}>
              <Text color={theme.colors.diff.addFg}>+</Text>
            </Box>
            <Box flexShrink={1}>
              <Text wrap="wrap">{highlightCode(line.text, ext)}</Text>
            </Box>
          </Box>
        ))}

        {hiddenCount > 0 && (
          <Box flexDirection="row" marginTop={1}>
            <Text color={theme.colors.text.muted}> ... {hiddenCount} more lines</Text>
          </Box>
        )}
      </Box>
    </Box>
  );
});
