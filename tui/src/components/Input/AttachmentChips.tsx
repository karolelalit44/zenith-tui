import { Box, Text } from 'ink';
import React from 'react';
import { useTheme } from '../../theme/ThemeContext';
import type { FileAttachment } from '../../types/scenario';

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

interface AttachmentChipsProps {
  attachments: FileAttachment[];
  onRemove?: (index: number) => void;
}

export const AttachmentChips: React.FC<AttachmentChipsProps> = React.memo(({ attachments, onRemove }) => {
  const { theme } = useTheme();

  if (attachments.length === 0) return null;

  return (
    <Box flexDirection="row" flexWrap="wrap" marginBottom={1} paddingX={1}>
      {attachments.map((att, idx) => (
        <Box key={`${att.path}-${idx}`} flexDirection="row" marginRight={1} marginBottom={0}>
          <Box flexDirection="row" borderStyle="round" borderColor={theme.colors.border.muted} paddingX={1}>
            <Text color={theme.colors.status.info}>@</Text>
            <Text color={theme.colors.text.ethereal}> {att.name}</Text>
            <Text color={theme.colors.text.muted}> · {formatBytes(att.size)}</Text>
            {onRemove && <Text color={theme.colors.status.error}> ×</Text>}
          </Box>
        </Box>
      ))}
    </Box>
  );
});

AttachmentChips.displayName = 'AttachmentChips';
