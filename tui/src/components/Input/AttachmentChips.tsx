import { Box, Text, useInput } from 'ink';
import React, { useCallback, useState } from 'react';
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
  const [selectedIndex, setSelectedIndex] = useState(-1);

  const removeSelected = useCallback(() => {
    if (onRemove && selectedIndex >= 0 && selectedIndex < attachments.length) {
      onRemove(selectedIndex);
      setSelectedIndex((prev) => Math.min(prev, attachments.length - 2));
    }
  }, [onRemove, selectedIndex, attachments.length]);

  useInput(
    (_input, key) => {
      if (!onRemove || attachments.length === 0) return;
      if (key.leftArrow) {
        setSelectedIndex((prev) => (prev <= 0 ? attachments.length - 1 : prev - 1));
      } else if (key.rightArrow) {
        setSelectedIndex((prev) => (prev >= attachments.length - 1 ? 0 : prev + 1));
      } else if (key.backspace || key.delete) {
        removeSelected();
      }
    },
    { isActive: onRemove != null && attachments.length > 0 },
  );

  if (attachments.length === 0) return null;

  return (
    <Box flexDirection="row" flexWrap="wrap" marginBottom={1} paddingX={1}>
      {attachments.map((att, idx) => (
        <Box key={`${att.path}-${idx}`} flexDirection="row" marginRight={1} marginBottom={0}>
          <Box
            flexDirection="row"
            borderStyle="round"
            borderColor={selectedIndex === idx ? theme.colors.status.info : theme.colors.border.muted}
            paddingX={1}
          >
            <Text color={theme.colors.status.info}>@</Text>
            <Text color={theme.colors.text.ethereal}> {att.name}</Text>
            <Text color={theme.colors.text.muted}> · {formatBytes(att.size)}</Text>
            {onRemove && (
              <Text color={selectedIndex === idx ? theme.colors.status.error : theme.colors.text.dim}>
                {selectedIndex === idx ? ' ×' : ' ·'}
              </Text>
            )}
          </Box>
        </Box>
      ))}
    </Box>
  );
});

AttachmentChips.displayName = 'AttachmentChips';
