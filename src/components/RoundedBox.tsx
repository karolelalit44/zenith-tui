import React from 'react';
import { Box, Text } from 'ink';
import { theme } from '../theme/theme';

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
  return (
    <Box flexDirection="column" width="100%">
      <Box flexDirection="row" width="100%">
      {/* Modern HUD Box with Heavy Block Borders */}
      <Box
        borderStyle={{
          topLeft: '▛', topRight: '▜', top: '▀', bottom: '▄', bottomLeft: '▙', bottomRight: '▟', left: '▌', right: '▐'
        }}
        borderColor={borderColor}
        paddingX={paddingX}
        paddingY={paddingY}
        flexDirection="column"
        flexGrow={1}
      >
        {/* Inline HUD Title */}
        {title && (
          <Box marginBottom={1} paddingX={1} alignSelf="flex-start">
            <Text color={theme.colors.bg.app} backgroundColor={borderColor} bold> {title} </Text>
          </Box>
        )}
        <Box flexDirection="column" width="100%">
          {children}
        </Box>
      </Box>


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
