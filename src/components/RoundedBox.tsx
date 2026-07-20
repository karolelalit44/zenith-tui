import React from 'react';
import { Box, Text } from 'ink';
import { useTheme } from '../theme/ThemeContext';

interface RoundedBoxProps {
  title?: string;
  borderColor?: string;
  children: React.ReactNode;
  paddingX?: number;
  paddingY?: number;
  hasShadow?: boolean;
}

export const RoundedBox: React.FC<RoundedBoxProps> = ({
  title,
  borderColor = theme.colors.border.default,
  children,
  paddingX = 1,
  paddingY = 0,
  hasShadow = false,
}) => {
  const { theme } = useTheme();
  
  return (
    <Box flexDirection="column" width="100%">
      <Box flexDirection="row" width="100%" position="relative">
      {/* Modern HUD Box with Rounded Borders */}
      <Box
        borderStyle={{
          topLeft: '╭', topRight: '╮', top: '═', bottom: '═', bottomLeft: '╰', bottomRight: '╯', left: '║', right: '║'
        }}
        borderColor={borderColor}
        paddingX={paddingX}
        paddingY={paddingY}
        flexDirection="column"
        flexGrow={1}
      >
        {/* Children wrapper */}
        <Box flexDirection="column" width="100%" flexGrow={1} justifyContent="center">
          {children}
        </Box>
      </Box>

      {/* Embedded Border Title on Right Hand Side */}
      {title && (
        <Box position="absolute" top={0} left={0} width="100%" justifyContent="flex-end" paddingRight={4}>
          <Box flexDirection="row">
            <Text color={borderColor}>╣ </Text>
            <Text color={theme.colors.bg.app} backgroundColor={borderColor} bold> {title} </Text>
            <Text color={borderColor}> ╠</Text>
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
