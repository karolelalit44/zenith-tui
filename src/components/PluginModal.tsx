import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import TextInput from 'ink-text-input';
import { RoundedBox } from './RoundedBox';
import { useTheme } from '../theme/ThemeContext';

export const PluginModal: React.FC<{ onClose: () => void; onTriggerMock: (cmd: string) => void }> = ({ onClose, onTriggerMock }) => {
  const { theme } = useTheme();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [activeTab, setActiveTab] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  
  const tabs = ['Discover', 'Installed', 'Marketplaces', 'Errors'];

  useInput((char, key) => {
    if (key.escape) {
      onClose();
    }
    
    // Cycle tabs with shift+tab or something else, wait ink useInput tab catching is hard
    // Let's just catch right arrow for tabs if search is empty, or just ctrl+n
    if (key.rightArrow && searchQuery === '') {
      setActiveTab(t => (t + 1) % tabs.length);
    } else if (key.leftArrow && searchQuery === '') {
      setActiveTab(t => (t - 1 + tabs.length) % tabs.length);
    }

    if (key.return) {
      onTriggerMock();
    }
  });

  return (
    <RoundedBox title="Zenith Plugins" borderColor={theme.colors.border.muted} hasShadow={true}>
      {/* Tabs Row */}
      <Box flexDirection="row" justifyContent="space-between" marginBottom={1}>
        <Box flexDirection="row" gap={2}>
          {tabs.map((t, i) => (
             <Text key={t} backgroundColor={i === activeTab ? theme.colors.text.emerald : undefined} color={i === activeTab ? '#000' : theme.colors.text.ethereal}>
               {i === activeTab ? ` ${t} ` : t}
             </Text>
          ))}
        </Box>
        <Text color={theme.colors.text.muted}>(arrows to cycle, enter to run, esc to close)</Text>
      </Box>

      {/* Subtitle */}
      <Box marginBottom={1}>
        <Text color={theme.colors.text.ethereal}>{tabs[activeTab]} plugins </Text>
        <Text color={theme.colors.text.muted}>(1/44)</Text>
      </Box>

      {/* Search Bar */}
      <Box borderStyle="round" borderColor={theme.colors.border.muted} paddingX={1} marginBottom={1} flexDirection="row">
        <Text color={theme.colors.text.muted}>⌕ Search: </Text>
        <TextInput value={searchQuery} onChange={setSearchQuery} />
      </Box>

      {/* List Items */}
      <Box flexDirection="column" gap={1}>
        {/* Active Item */}
        <Box flexDirection="column">
          <Box flexDirection="row">
            <Text color={theme.colors.text.ethereal} bold>{'> o '}</Text>
            <Text color={theme.colors.text.ethereal}>context7 </Text>
            <Text color={theme.colors.text.muted}>· zenith-plugins-official [Community Managed] · 36.2K installs</Text>
          </Box>
          <Box paddingLeft={4}>
            <Text color={theme.colors.text.muted}>Upstash Context7 MCP server for up-to-date documentation ...</Text>
          </Box>
        </Box>
      </Box>
    </RoundedBox>
  );
};
