import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { useTheme } from '../../theme/ThemeContext';

interface SettingsModalProps {
  onClose: () => void;
}

interface ThemeOption {
  id: string;
  name: string;
  swatch: string[];
}

const THEME_OPTIONS: ThemeOption[] = [
  { id: 'deep_forest', name: 'Deep Forest (Default)', swatch: ['#50C878', '#8FBC8F', '#DAA520', '#FF6B6B'] },
  { id: 'dracula', name: 'Dracula', swatch: ['#BD93F9', '#50FA7B', '#8BE9FD', '#FF79C6'] },
  { id: 'monokai', name: 'Monokai Pro', swatch: ['#A6E22E', '#66D9EF', '#FD971F', '#F92672'] },
  { id: 'synthwave', name: 'Synthwave 84', swatch: ['#F92A82', '#00F2FE', '#F39C12', '#BC7FD4'] },
  { id: 'aura', name: 'Aura Dark', swatch: ['#61FFCA', '#82E2FF', '#A277FF', '#FF6767'] },
  { id: 'graphite', name: 'Graphite Monochrome', swatch: ['#E0E0E0', '#A0A0A0', '#707070', '#444444'] },
];

export const SettingsModal: React.FC<SettingsModalProps> = ({ onClose }) => {
  const { theme, activeThemeId, setTheme } = useTheme();
  const currentIdx = THEME_OPTIONS.findIndex((t) => t.id === activeThemeId);
  const [selectedIndex, setSelectedIndex] = useState(currentIdx >= 0 ? currentIdx : 0);

  useInput((_char, key) => {
    if (key.upArrow) {
      const nextIdx = Math.max(0, selectedIndex - 1);
      setSelectedIndex(nextIdx);
      setTheme(THEME_OPTIONS[nextIdx].id);
    }

    if (key.downArrow) {
      const nextIdx = Math.min(THEME_OPTIONS.length - 1, selectedIndex + 1);
      setSelectedIndex(nextIdx);
      setTheme(THEME_OPTIONS[nextIdx].id);
    }

    if (key.return || key.escape) {
      onClose();
    }
  });

  return (
    <RoundedBox title="SETTINGS & THEME MANAGER" borderColor={theme.colors.border.active} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        <Box
          marginBottom={1}
          paddingBottom={1}
          borderStyle="single"
          borderTop={false}
          borderColor={theme.colors.border.muted}
        >
          <Text color={theme.colors.text.emerald}>❯ </Text>
          <Text color={theme.colors.text.ethereal} bold>
            Select theme to apply live visual styles
          </Text>
        </Box>

        {THEME_OPTIONS.map((t, idx) => {
          const isSelected = idx === selectedIndex;
          const isActive = t.id === activeThemeId;

          return (
            <Box key={t.id} flexDirection="row" alignItems="center" marginY={1} width="100%">
              <Box width={3}>
                <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.dim}>
                  {isSelected ? '▸ ' : '  '}
                </Text>
              </Box>

              <Box width={26} flexShrink={0}>
                <Text color={isSelected ? theme.colors.text.ethereal : theme.colors.text.dim} bold={isSelected}>
                  {t.name}
                </Text>
              </Box>

              <Box flexDirection="row" marginRight={2}>
                {t.swatch.map((c, i) => (
                  <Text key={i} color={c}>
                    █
                  </Text>
                ))}
              </Box>

              {isActive && (
                <Text color={theme.colors.status.success} bold>
                  [ACTIVE]
                </Text>
              )}
            </Box>
          );
        })}

        <Box marginTop={1} paddingTop={1} borderStyle="single" borderTop={true} borderColor={theme.colors.border.muted}>
          <Text color={theme.colors.text.muted}>
            <Text color={theme.colors.text.emerald}>[↑/↓]</Text> Live Preview Theme ·{' '}
            <Text color={theme.colors.text.emerald}>[Enter/Esc]</Text> Apply & Exit
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
