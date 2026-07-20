import React from 'react';
import { Box, Text } from 'ink';
import { theme } from '../theme/theme';

interface RoundedBoxProps {
  title?: string;
  borderColor?: string;
  children: React.ReactNode;
  paddingX?: number;
  paddingY?: number;
}

export const RoundedBox: React.FC<RoundedBoxProps> = ({
  title,
  borderColor = theme.colors.border.default,
  children,
  paddingX = 1,
  paddingY = 0,
}) => {
  return (
    <Box flexDirection="column" width="100%">
      {/* Custom Top Border with Dynamic Resizing via wrap="truncate" */}
      <Box flexDirection="row" width="100%">
        <Text color={borderColor}>╭─</Text>
        {title ? (
          <>
            <Text color={borderColor}>─ </Text>
            <Box flexShrink={0}>
              <Text color={theme.colors.text.primary} bold wrap="truncate">{title}</Text>
            </Box>
            <Text color={borderColor}> ─</Text>
            <Box flexGrow={1} overflowX="hidden">
               <Text color={borderColor} wrap="truncate-end">{'─'.repeat(300)}</Text>
            </Box>
            <Text color={borderColor}>╮</Text>
          </>
        ) : (
          <>
            <Box flexGrow={1} overflowX="hidden">
               <Text color={borderColor} wrap="truncate-end">{'─'.repeat(300)}</Text>
            </Box>
            <Text color={borderColor}>╮</Text>
          </>
        )}
      </Box>

      {/* Main Content Area */}
      <Box
        borderStyle={{
          topLeft: '', topRight: '', top: '', bottom: '─', bottomLeft: '╰', bottomRight: '╯', left: '│', right: '│'
        }}
        borderColor={borderColor}
        paddingX={paddingX}
        paddingY={paddingY}
        flexDirection="column"
      >
        {children}
      </Box>
    </Box>
  );
};
