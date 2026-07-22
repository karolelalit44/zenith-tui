import React from 'react';
import { Box, Text } from 'ink';
import { RoundedBox } from '../../ui/RoundedBox';
import { useTheme } from '../../../theme/ThemeContext';
import { CONTEXT_DATA, CONTEXT_META } from '../data/contextData';

const FileTree: React.FC<{ files: typeof CONTEXT_DATA; depth?: number }> = ({ files, depth = 0 }) => {
  const { theme } = useTheme();
  return (
    <>
      {files.map((file, idx) => {
        const isLast = idx === files.length - 1;
        const connector = isLast ? '└─ ' : '├─ ';

        return (
          <React.Fragment key={idx}>
            <Box flexDirection="row" paddingLeft={depth * 2}>
              <Text color={theme.colors.border.muted}>{connector}</Text>
              {file.isDirectory ? (
                <>
                  <Text color={theme.colors.text.emerald}>▼ </Text>
                  <Text color={theme.colors.text.ethereal} bold>{file.name}</Text>
                </>
              ) : (
                <>
                  <Text color={theme.colors.text.emerald}>📄 </Text>
                  <Box width={20 - depth * 2}><Text color={theme.colors.text.ethereal}>{file.name}</Text></Box>
                  <Text color={theme.colors.text.muted}>{file.size}</Text>
                </>
              )}
            </Box>
            {file.children && <FileTree files={file.children} depth={depth + 1} />}
          </React.Fragment>
        );
      })}
    </>
  );
};

export const ContextModal: React.FC<{ onClose: () => void }> = () => {
  const { theme } = useTheme();

  return (
    <RoundedBox title={CONTEXT_META.title} borderColor={theme.colors.border.muted} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1}>
        <Box marginBottom={1}>
          <Text color={theme.colors.text.muted}>{CONTEXT_META.loadedHint}</Text>
        </Box>

        <Box flexDirection="column">
          <FileTree files={CONTEXT_DATA} />
        </Box>

        <Box marginTop={1}>
          <Text color={theme.colors.text.muted}>{CONTEXT_META.totalContextLabel}</Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
