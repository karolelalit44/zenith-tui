import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import TextInput from 'ink-text-input';
import { RoundedBox } from '../../../components/ui/RoundedBox';
import { useTheme } from '../../../theme/ThemeContext';
import { PLUGIN_TABS, PLUGIN_LIST, PLUGINS_META } from './data/pluginsData';

export const PluginsScreen: React.FC<{
  onClose: () => void;
  onTriggerMock: (cmd: string) => void;
}> = ({ onClose, onTriggerMock }) => {
  const { theme } = useTheme();
  const [activeTab, setActiveTab] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');

  useInput((char, key) => {
    if (key.escape) {
      onClose();
    }

    if (key.rightArrow && searchQuery === '') {
      setActiveTab(t => (t + 1) % PLUGIN_TABS.length);
    } else if (key.leftArrow && searchQuery === '') {
      setActiveTab(t => (t - 1 + PLUGIN_TABS.length) % PLUGIN_TABS.length);
    }

    if (key.return) {
      onTriggerMock('/plugin');
    }
  });

  return (
    <RoundedBox title={PLUGINS_META.title} borderColor={theme.colors.border.muted} hasShadow={true}>
      <Box flexDirection="row" justifyContent="space-between" marginBottom={1}>
        <Box flexDirection="row" gap={2}>
          {PLUGIN_TABS.map((t, i) => (
            <Text key={t.id} backgroundColor={i === activeTab ? theme.colors.text.emerald : undefined} color={i === activeTab ? '#000' : theme.colors.text.ethereal}>
              {i === activeTab ? ` ${t.label} ` : t.label}
            </Text>
          ))}
        </Box>
        <Text color={theme.colors.text.muted}>({PLUGINS_META.hotkeys.cycle}, {PLUGINS_META.hotkeys.run}, {PLUGINS_META.hotkeys.close})</Text>
      </Box>

      <Box marginBottom={1}>
        <Text color={theme.colors.text.ethereal}>{PLUGIN_TABS[activeTab].label} {PLUGINS_META.headerLabel} </Text>
        <Text color={theme.colors.text.muted}>(1/44)</Text>
      </Box>

      <Box borderStyle="round" borderColor={theme.colors.border.muted} paddingX={1} marginBottom={1} flexDirection="row">
        <Text color={theme.colors.text.muted}>{PLUGINS_META.searchLabel}</Text>
        <TextInput value={searchQuery} onChange={setSearchQuery} />
      </Box>

      <Box flexDirection="column" gap={1}>
        {PLUGIN_LIST.map((plugin, idx) => (
          <Box key={idx} flexDirection="column">
            <Box flexDirection="row">
              <Text color={theme.colors.text.ethereal} bold>{'> o '}</Text>
              <Text color={theme.colors.text.ethereal}>{plugin.name} </Text>
              <Text color={theme.colors.text.muted}>· {plugin.source} · {plugin.installs} installs</Text>
            </Box>
            <Box paddingLeft={4}>
              <Text color={theme.colors.text.muted}>{plugin.description}</Text>
            </Box>
          </Box>
        ))}
      </Box>
    </RoundedBox>
  );
};
