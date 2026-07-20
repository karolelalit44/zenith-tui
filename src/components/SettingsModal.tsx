import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { RoundedBox } from './RoundedBox';
import { theme } from '../theme/theme';

const MOCK_SETTINGS = [
  { id: 'theme', label: 'Theme', value: 'Deep Forest' },
  { id: 'compact', label: 'Compact Mode', value: 'Off' },
  { id: 'autoApprove', label: 'Auto-Approve Edits', value: 'On' },
];

export const SettingsModal: React.FC<{ onClose: () => void }> = ({ onClose }) => {
  const [selectedIndex, setSelectedIndex] = useState(0);

  useInput((char, key) => {
    if (key.escape) {
      onClose();
      return;
    }
    
    if (key.upArrow) {
      setSelectedIndex(prev => Math.max(0, prev - 1));
    }
    
    if (key.downArrow) {
      setSelectedIndex(prev => Math.min(MOCK_SETTINGS.length - 1, prev + 1));
    }
    
    if (key.return || (char && char.toLowerCase() === 't')) {
      // Toggle logic would go here if this wasn't a mock
      // For now, it just clicks.
    }
  });

  return (
    <RoundedBox title="Zenith Settings" borderColor={theme.colors.border.muted} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1}>
        <Box marginBottom={1}>
          <Text color={theme.colors.text.muted}>(arrows to select, enter to toggle, esc to close)</Text>
        </Box>
        
        {MOCK_SETTINGS.map((setting, idx) => {
          const isSelected = idx === selectedIndex;
          return (
            <Box key={setting.id} flexDirection="row" marginBottom={1}>
              <Box width={3}>
                <Text color={isSelected ? theme.colors.text.emerald : 'transparent'}>{'> '}</Text>
              </Box>
              <Box width={30}>
                <Text color={isSelected ? theme.colors.text.ethereal : theme.colors.text.muted} bold={isSelected}>
                  {setting.label}
                </Text>
              </Box>
              <Box>
                <Text color={isSelected ? theme.colors.text.warning : theme.colors.text.muted}>
                  {setting.value}
                </Text>
              </Box>
            </Box>
          );
        })}
      </Box>
    </RoundedBox>
  );
};
