import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../../../theme/ThemeContext';
import { WordDiffViewerProps } from './types';
import { UI_CONSTANTS } from '../../../constants';

export const WordDiffViewer: React.FC<WordDiffViewerProps> = ({ lines }) => {
  const { theme } = useTheme();

  return (
    <Box flexDirection="column" marginTop={1}>
      {lines.map((line, index) => {
        let bgColor = undefined;
        let prefix = '  ';
        let wordHighlightBg = undefined;

        if (line.type === 'add') {
          bgColor = theme.colors.diff.addBg;
          wordHighlightBg = theme.colors.diff.addWordBg;
          prefix = '+ ';
        } else if (line.type === 'remove') {
          bgColor = theme.colors.diff.removeBg;
          wordHighlightBg = theme.colors.diff.removeWordBg;
          prefix = '- ';
        }

        return (
          <Box key={index} flexDirection="row">
            <Box width={UI_CONSTANTS.LINE_NUMBER_WIDTH} justifyContent="flex-end" paddingRight={1}>
              <Text color={theme.colors.text.muted}>{line.number}</Text>
            </Box>

            <Box flexGrow={1} flexShrink={0} flexDirection="row">
              <Box backgroundColor={bgColor} width="100%" flexDirection="row">
                <Box width={2}>
                  <Text color={line.type === 'remove' ? theme.colors.text.emerald : theme.colors.text.ethereal}>
                    {prefix}
                  </Text>
                </Box>
                <Box>
                  {line.segments.map((seg, i) => (
                    <Text key={i} backgroundColor={seg.isHighlightedWord ? wordHighlightBg : undefined} color={theme.colors.text.ethereal}>
                      {seg.text}
                    </Text>
                  ))}
                </Box>
              </Box>
            </Box>
          </Box>
        );
      })}
    </Box>
  );
};
