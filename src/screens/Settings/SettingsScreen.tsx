import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { useTheme } from '../../theme/ThemeContext';
import { SETTINGS_DATA, SETTINGS_META } from './data/settingsData';

export const SettingsScreen: React.FC<{
  onClose: () => void;
  onOpenTheme?: () => void;
  autoApprove: boolean;
  setAutoApprove: React.Dispatch<React.SetStateAction<boolean>>;
}> = ({ onClose, onOpenTheme, autoApprove, setAutoApprove }) => {
  const { theme } = useTheme();
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
      setSelectedIndex(prev => Math.min(SETTINGS_DATA.length - 1, prev + 1));
    }

    if (key.return) {
      const activeSetting = SETTINGS_DATA[selectedIndex];
      if (activeSetting.id === 'autoApprove') {
        setAutoApprove(prev => !prev);
      } else if (activeSetting.id === 'theme' && onOpenTheme) {
        onOpenTheme();
      }
    }
  });

  return (
    <RoundedBox title={SETTINGS_META.title} borderColor={theme.colors.border.muted} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        <Box marginBottom={1} paddingBottom={1} borderStyle="single" borderTop={false} borderLeft={false} borderRight={false} borderColor={theme.colors.border.muted}>
          <Text color={theme.colors.text.emerald}>❯ </Text>
          <Text color={theme.colors.text.ethereal} bold>{SETTINGS_META.headerLabel}</Text>
        </Box>

        {SETTINGS_DATA.map((setting, idx) => {
          const isSelected = idx === selectedIndex;

          let badgeColor = theme.colors.text.muted;
          if (setting.actionType === 'toggle') {
            badgeColor = autoApprove ? theme.colors.text.emerald : theme.colors.text.muted;
          } else {
            badgeColor = theme.colors.text.warning;
          }

          const badgeText = setting.actionType === 'toggle'
            ? (autoApprove ? '● ON' : '○ OFF')
            : undefined;
          const navigateBadge = setting.actionType === 'navigate' ? 'Deep Forest ↗' : undefined;

          return (
            <Box key={setting.id} flexDirection="row" marginY={1} width="100%">
              <Box width={3}>
                <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.muted}>
                  {isSelected ? '▎ ' : '  '}
                </Text>
              </Box>

              <Box flexDirection="column" flexGrow={1}>
                <Box flexDirection="row" justifyContent="space-between" width="100%">
                  <Box flexDirection="row">
                    <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.muted}>{setting.icon} </Text>
                    <Text color={isSelected ? theme.colors.text.ethereal : theme.colors.text.muted} bold={isSelected}>
                      {setting.label}
                    </Text>
                  </Box>
                  <Box>
                    {setting.actionType === 'navigate' ? (
                      <Text color={isSelected ? theme.colors.text.warning : theme.colors.text.muted} bold={isSelected}>
                        {navigateBadge}
                      </Text>
                    ) : (
                      <Text color={badgeColor} bold={isSelected}>
                        {badgeText}
                      </Text>
                    )}
                  </Box>
                </Box>
                <Box marginTop={0} paddingLeft={3}>
                  <Text color={theme.colors.text.muted} dimColor={!isSelected} italic={isSelected}>
                    {setting.desc}
                  </Text>
                </Box>
              </Box>
            </Box>
          );
        })}

        <Box marginTop={1} paddingTop={1} borderStyle="single" borderTop={true} borderLeft={false} borderRight={false} borderBottom={false} borderColor={theme.colors.border.muted} justifyContent="center">
          <Text color={theme.colors.text.muted}>
            <Text color={theme.colors.text.emerald}>{SETTINGS_META.hotkeys.navigate}</Text>   <Text color={theme.colors.text.emerald}>{SETTINGS_META.hotkeys.toggle}</Text>   <Text color={theme.colors.text.emerald}>{SETTINGS_META.hotkeys.close}</Text>
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
