import React from 'react';
import { Box, Text } from 'ink';
import { RoundedBox } from './RoundedBox';
import { theme } from '../theme/theme';

export const ContextModal: React.FC<{ onClose: () => void }> = () => {
  return (
    <RoundedBox title="Workspace Context" borderColor={theme.colors.border.muted} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1}>
        <Box marginBottom={1}>
          <Text color={theme.colors.text.muted}>(Loaded files available to Zenith)</Text>
        </Box>

        <Box flexDirection="column">
          {/* Root Directory */}
          <Box flexDirection="row">
            <Text color={theme.colors.text.emerald}>▼ </Text>
            <Text color={theme.colors.text.ethereal} bold>src/</Text>
          </Box>
          
          {/* Sub files */}
          <Box flexDirection="row" paddingLeft={2}>
            <Text color={theme.colors.border.muted}>├─ </Text>
            <Text color={theme.colors.text.emerald}>📄 </Text>
            <Box width={20}><Text color={theme.colors.text.ethereal}>App.tsx</Text></Box>
            <Text color={theme.colors.text.muted}>5.1 KB</Text>
          </Box>
          <Box flexDirection="row" paddingLeft={2}>
            <Text color={theme.colors.border.muted}>├─ </Text>
            <Text color={theme.colors.text.emerald}>📄 </Text>
            <Box width={20}><Text color={theme.colors.text.ethereal}>index.tsx</Text></Box>
            <Text color={theme.colors.text.muted}>104 B</Text>
          </Box>
          <Box flexDirection="row" paddingLeft={2}>
            <Text color={theme.colors.border.muted}>└─ </Text>
            <Text color={theme.colors.text.emerald}>▼ </Text>
            <Text color={theme.colors.text.ethereal} bold>components/</Text>
          </Box>
          <Box flexDirection="row" paddingLeft={5}>
            <Text color={theme.colors.border.muted}>├─ </Text>
            <Text color={theme.colors.text.emerald}>📄 </Text>
            <Box width={17}><Text color={theme.colors.text.ethereal}>RoundedBox.tsx</Text></Box>
            <Text color={theme.colors.text.muted}>1.8 KB</Text>
          </Box>
          <Box flexDirection="row" paddingLeft={5}>
            <Text color={theme.colors.border.muted}>└─ </Text>
            <Text color={theme.colors.text.emerald}>📄 </Text>
            <Box width={17}><Text color={theme.colors.text.ethereal}>Mascot.tsx</Text></Box>
            <Text color={theme.colors.text.muted}>332 B</Text>
          </Box>
        </Box>

        <Box marginTop={1}>
          <Text color={theme.colors.text.muted}>Total Context Size: 7.3 KB / 128 KB</Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
