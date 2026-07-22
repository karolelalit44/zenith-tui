import { Box, Text, useInput } from 'ink';
import TextInput from 'ink-text-input';
import React, { useState } from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { useTheme } from '../../theme/ThemeContext';

interface AddDirModalProps {
  currentWorkspace: string;
  onSelectDir: (dirPath: string) => void;
  onClose: () => void;
}

export const AddDirModal: React.FC<AddDirModalProps> = ({ currentWorkspace, onSelectDir, onClose }) => {
  const { theme } = useTheme();
  const [inputVal, setInputVal] = useState('');

  useInput((_char, key) => {
    if (key.escape) {
      onClose();
    }
  });

  const handleSubmit = (val: string) => {
    const trimmed = val.trim();
    if (trimmed) {
      onSelectDir(trimmed);
    }
    onClose();
  };

  return (
    <RoundedBox title="ADD WORKING DIRECTORY" borderColor={theme.colors.border.active} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        <Box marginBottom={1}>
          <Text color={theme.colors.text.muted}>Current Active Workspace: </Text>
          <Text color={theme.colors.status.success} bold>
            {currentWorkspace}
          </Text>
        </Box>

        <Box flexDirection="row" alignItems="center" marginBottom={1}>
          <Text color={theme.colors.text.emerald}>New Directory Path: </Text>
          <TextInput
            value={inputVal}
            onChange={setInputVal}
            onSubmit={handleSubmit}
            placeholder="./src or absolute path"
          />
        </Box>

        <Box marginTop={1} paddingTop={1} borderStyle="single" borderTop={true} borderColor={theme.colors.border.muted}>
          <Text color={theme.colors.text.muted}>
            Press <Text color={theme.colors.text.emerald}>[Enter]</Text> to set directory ·{' '}
            <Text color={theme.colors.text.emerald}>[Esc]</Text> Cancel
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
