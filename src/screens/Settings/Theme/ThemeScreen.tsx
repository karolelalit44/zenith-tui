import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { RoundedBox } from '../../../components/ui/RoundedBox';
import { useTheme } from '../../../theme/ThemeContext';
import { THEME_OPTIONS, THEME_META } from './data/themeData';

export const ThemeScreen: React.FC<{
  onClose: () => void;
  onSelect?: (themeId: string) => void;
}> = ({ onClose, onSelect }) => {
  const { theme, activeThemeId, setTheme } = useTheme();
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [activeTheme, setActiveTheme] = useState(activeThemeId);

  useInput((char, key) => {
    if (key.escape) {
      onClose();
      return;
    }

    if (key.upArrow) {
      setSelectedIndex(prev => Math.max(0, prev - 1));
    }

    if (key.downArrow) {
      setSelectedIndex(prev => Math.min(THEME_OPTIONS.length - 1, prev + 1));
    }

    if (key.return) {
      const selected = THEME_OPTIONS[selectedIndex].id;
      setActiveTheme(selected);
      setTheme(selected);
      if (onSelect) onSelect(selected);
      onClose();
    }
  });

  return (
    <RoundedBox title={THEME_META.title} borderColor={theme.colors.border.muted} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        <Box marginBottom={1} paddingBottom={1} borderStyle="single" borderTop={false} borderLeft={false} borderRight={false} borderColor={theme.colors.border.muted}>
          <Text color={theme.colors.text.emerald}>❯ </Text>
          <Text color={theme.colors.text.ethereal} bold>{THEME_META.headerLabel}</Text>
        </Box>

        {THEME_OPTIONS.map((t, idx) => {
          const isSelected = idx === selectedIndex;
          const isActive = t.id === activeTheme;

          return (
            <Box key={t.id} flexDirection="row" marginY={1} width="100%">
              <Box width={3}>
                <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.muted}>
                  {isSelected ? '▸ ' : '  '}
                </Text>
              </Box>

              <Box flexDirection="column" flexGrow={1}>
                <Box flexDirection="row" justifyContent="space-between" width="100%">
                  <Box flexDirection="row">
                    <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.muted}>{t.icon} </Text>
                    <Text color={isSelected ? theme.colors.text.ethereal : theme.colors.text.muted} bold={isSelected}>
                      {t.label}
                    </Text>
                  </Box>
                  {isActive && (
                    <Text color={theme.colors.text.warning} bold>
                      {THEME_META.activeBadge}
                    </Text>
                  )}
                </Box>
                <Box marginTop={0} paddingLeft={4}>
                  <Text color={theme.colors.text.muted} dimColor={!isSelected} italic={isSelected}>
                    {t.desc}
                  </Text>
                </Box>
              </Box>
            </Box>
          );
        })}

        <Box marginTop={1} paddingTop={1} borderStyle="single" borderTop={true} borderLeft={false} borderRight={false} borderBottom={false} borderColor={theme.colors.border.muted} justifyContent="center">
          <Text color={theme.colors.text.muted}>
            <Text color={theme.colors.text.emerald}>{THEME_META.hotkeys.navigate}</Text>   <Text color={theme.colors.text.emerald}>{THEME_META.hotkeys.apply}</Text>   <Text color={theme.colors.text.emerald}>{THEME_META.hotkeys.close}</Text>
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
