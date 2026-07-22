import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { FileCreateEvent } from '../../../types/scenario';
import { highlightCode } from '../../../utils/syntaxHighlight';

interface FileDiffCardProps {
  event: FileCreateEvent;
  isHistorical?: boolean;
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
      {/* File Header Line - No emojis */}
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color="#3FB950" bold>[CREATE] New File</Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color="#E6EDF3" bold>{event.filePath}</Text>
        <Text color="#8B949E"> ({event.lines.length} lines)</Text>
      </Box>

      {/* Code Container */}
      <Box flexDirection="column" width="100%" borderStyle="round" borderColor="#30363D" paddingX={1}>
        <Box flexDirection="row" marginBottom={1}>
          <Text color="#8B949E">@@ 0, {event.lines.length} @@ </Text>
          <Text color="#58A6FF">+{ext}</Text>
        </Box>

        {displayLines.map((line, idx) => (
          <Box key={idx} flexDirection="row" width="100%">
            <Box width={4} flexShrink={0}>
              <Text color="#6E7681">{idx + 1}</Text>
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
            <Text color="#8B949E">  ... {event.lines.length - MAX_VISIBLE_LINES} more lines</Text>
          </Box>
        )}
      </Box>
    </Box>
  );
});
