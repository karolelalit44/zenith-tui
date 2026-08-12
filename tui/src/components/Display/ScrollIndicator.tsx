import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../theme/ThemeContext';

interface ScrollIndicatorProps {
  visible: boolean;
  scrollOffset: number;
  totalLines: number;
}

export const ScrollIndicator: React.FC<ScrollIndicatorProps> = ({ visible, scrollOffset, totalLines }) => {
  const { theme } = useTheme();

  if (!visible) return null;

  const percentage = totalLines > 0 ? Math.round((scrollOffset / totalLines) * 100) : 0;

  return (
    <Box
      flexDirection="row"
      paddingX={2}
      paddingY={0}
      marginBottom={1}
      justifyContent="center"
      borderStyle="round"
      borderColor={theme.colors.status.warning}
    >
      <Text color={theme.colors.status.warning}>⬆ Scrolled up ({percentage}%)</Text>
      <Text color={theme.colors.text.muted}> · Press </Text>
      <Text color={theme.colors.text.bright} backgroundColor={theme.colors.bg.modal}>
        End
      </Text>
      <Text color={theme.colors.text.muted}> to follow</Text>
    </Box>
  );
};
