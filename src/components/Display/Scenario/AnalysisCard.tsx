import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { AnalysisEvent } from '../../../types/scenario';

interface AnalysisCardProps {
  event: AnalysisEvent;
}

export const AnalysisCard: React.FC<AnalysisCardProps> = ({ event }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
      {/* Header */}
      <Box flexDirection="row" alignItems="center" marginBottom={1} flexWrap="wrap">
        <Text color={theme.colors.status.accent} bold>
          [ANALYSIS]
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.text.bright} bold>
          {event.title}
        </Text>
      </Box>

      {/* Blueprint Container Box */}
      <Box
        flexDirection="column"
        width="100%"
        borderStyle="round"
        borderColor={theme.colors.border.default}
        paddingX={2}
        paddingY={1}
      >
        {event.sections.map((section, sIdx) => (
          <Box key={sIdx} flexDirection="column" marginBottom={sIdx === event.sections.length - 1 ? 0 : 1}>
            <Box flexDirection="row" alignItems="center" marginBottom={0}>
              <Text color={theme.colors.status.accent} bold>
                {section.title}
              </Text>
            </Box>
            <Box flexDirection="column" paddingLeft={2} marginTop={0}>
              {section.items.map((item, iIdx) => (
                <Box key={iIdx} flexDirection="row" alignItems="center">
                  <Text color={theme.colors.text.emerald}>▸ </Text>
                  <Text color={theme.colors.text.ethereal}> {item}</Text>
                </Box>
              ))}
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
};
