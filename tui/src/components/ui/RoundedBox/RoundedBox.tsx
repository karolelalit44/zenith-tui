import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../../theme/ThemeContext';
import type { RoundedBoxProps } from './types';
export const RoundedBox: React.FC<RoundedBoxProps> = ({
  title,
  borderColor,
  children,
  paddingX = 1,
  paddingY = 0,
  hasShadow = false,
}) => {
  const { theme } = useTheme();
  const currentBorderColor = borderColor || theme.colors.border.default;

  return (
    <Box flexDirection="column" width="100%">
      <Box flexDirection="row" width="100%" position="relative">
        <Box
          borderStyle={{
            topLeft: '╭',
            topRight: '╮',
            top: '═',
            bottom: '═',
            bottomLeft: '╰',
            bottomRight: '╯',
            left: '║',
            right: '║',
          }}
          borderColor={currentBorderColor}
          paddingX={paddingX}
          paddingY={paddingY}
          flexDirection="column"
          flexGrow={1}
        >
          <Box flexDirection="column" width="100%" flexGrow={1} justifyContent="center">
            {children}
          </Box>
        </Box>

        {title && (
          // @ts-expect-error - Ink Box supports position absolute but types may not include it
          <Box position="absolute" top={0} left={0} width="100%" justifyContent="flex-end" paddingRight={4}>
            <Box flexDirection="row">
              <Text color={currentBorderColor}>╣ </Text>
              <Text color={theme.colors.bg.app} backgroundColor={currentBorderColor} bold>
                {' '}
                {title}{' '}
              </Text>
              <Text color={currentBorderColor}> ╠</Text>
            </Box>
          </Box>
        )}

        {hasShadow && (
          <Box flexDirection="column" width={1} paddingTop={1}>
            <Text color={theme.colors.shadow.ascii}>█</Text>
            <Text color={theme.colors.shadow.ascii}>█</Text>
            <Text color={theme.colors.shadow.ascii}>█</Text>
            <Text color={theme.colors.shadow.ascii}>▀</Text>
          </Box>
        )}
      </Box>
    </Box>
  );
};
