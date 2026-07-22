import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { FileEditEvent } from '../../../types/scenario';
import { highlightCode } from '../../../utils/syntaxHighlight';

interface FileEditDiffCardProps {
  event: FileEditEvent;
  isHistorical?: boolean;
}

const MAX_VISIBLE_LINES = 25;

export const FileEditDiffCard: React.FC<FileEditDiffCardProps> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const totalLines = event.removedLines.length + event.addedLines.length;
  const truncated = totalLines > MAX_VISIBLE_LINES;
  const ext = event.filePath.split('.').pop() || event.language;

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      {/* File Header - No emojis */}
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color="#D29922" bold>[MODIFY]</Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color="#E6EDF3" bold>{event.filePath}</Text>
        <Text color="#8B949E"> (-{event.removedLines.length} +{event.addedLines.length})</Text>
      </Box>

      {/* Diff Box Container */}
      <Box flexDirection="column" width="100%" borderStyle="round" borderColor="#30363D" paddingX={1}>
        {event.removedLines.map((line, idx) => (
          <Box key={`rm-${idx}`} flexDirection="row" width="100%">
            <Box width={4} flexShrink={0}>
              <Text color="#6E7681">{idx + 1}</Text>
            </Box>
            <Box width={2} flexShrink={0}>
              <Text color="#F85149">-</Text>
            </Box>
            <Box flexShrink={1}>
              <Text color="#F85149" strikethrough wrap="wrap">
                {line.text}
              </Text>
            </Box>
          </Box>
        ))}

        {event.addedLines.map((line, idx) => (
          <Box key={`add-${idx}`} flexDirection="row" width="100%">
            <Box width={4} flexShrink={0}>
              <Text color="#6E7681">{event.removedLines.length + idx + 1}</Text>
            </Box>
            <Box width={2} flexShrink={0}>
              <Text color="#3FB950">+</Text>
            </Box>
            <Box flexShrink={1}>
              <Text wrap="wrap">
                {highlightCode(line.text, ext)}
              </Text>
            </Box>
          </Box>
        ))}

        {truncated && (
          <Box flexDirection="row" marginTop={1}>
            <Text color="#8B949E">  ... {totalLines - MAX_VISIBLE_LINES} more lines</Text>
          </Box>
        )}
      </Box>
    </Box>
  );
});
