import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { useTheme } from '../../theme/ThemeContext';
import type { ScenarioMode } from '../../types/scenario';
import { MODE_META, MODE_OPTIONS } from './data/modeData';

interface ModeSelectScreenProps {
  currentMode: ScenarioMode;
  onSelect: (mode: ScenarioMode) => void;
  onClose: () => void;
}

export const ModeSelectScreen: React.FC<ModeSelectScreenProps> = ({ currentMode, onSelect, onClose }) => {
  const { theme } = useTheme();
  const currentIdx = MODE_OPTIONS.findIndex((m) => m.id === currentMode);
  const [selectedIndex, setSelectedIndex] = useState(currentIdx >= 0 ? currentIdx : 1);

  useInput((_char, key) => {
    if (key.upArrow) {
      setSelectedIndex((prev) => Math.max(0, prev - 1));
    }

    if (key.downArrow) {
      setSelectedIndex((prev) => Math.min(MODE_OPTIONS.length - 1, prev + 1));
    }

    if (key.return) {
      onSelect(MODE_OPTIONS[selectedIndex].id as ScenarioMode);
    }

    if (key.escape) {
      onClose();
    }
  });

  return (
    <RoundedBox title={MODE_META.title} borderColor={theme.colors.border.active} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        <Box
          marginBottom={1}
          paddingBottom={1}
          borderStyle="single"
          borderTop={false}
          borderLeft={false}
          borderRight={false}
          borderColor={theme.colors.border.muted}
        >
          <Text color={theme.colors.text.emerald}>❯ </Text>
          <Text color={theme.colors.text.ethereal} bold>
            {MODE_META.headerLabel}
          </Text>
        </Box>

        {MODE_OPTIONS.map((mode, idx) => {
          const isSelected = idx === selectedIndex;
          const isCurrent = mode.id === currentMode;

          return (
            <Box key={mode.id} flexDirection="row" marginY={1} width="100%">
              <Box width={3}>
                <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.dim}>
                  {isSelected ? '▸ ' : '  '}
                </Text>
              </Box>

              <Box flexDirection="column" flexGrow={1}>
                <Box flexDirection="row" alignItems="center">
                  <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.dim}>{mode.icon} </Text>
                  <Text color={isSelected ? theme.colors.text.ethereal : theme.colors.text.dim} bold={isSelected}>
                    {mode.label}
                  </Text>
                  {isCurrent && (
                    <Text color={isSelected ? theme.colors.text.muted : theme.colors.text.dim}> (current)</Text>
                  )}
                </Box>
                <Box marginTop={0} paddingLeft={3}>
                  <Text color={isSelected ? theme.colors.text.muted : theme.colors.text.dim} italic={isSelected}>
                    {mode.desc}
                  </Text>
                </Box>
              </Box>
            </Box>
          );
        })}

        <Box
          marginTop={1}
          paddingTop={1}
          borderStyle="single"
          borderTop={true}
          borderLeft={false}
          borderRight={false}
          borderBottom={false}
          borderColor={theme.colors.border.muted}
          justifyContent="center"
        >
          <Text color={theme.colors.text.muted}>
            <Text color={theme.colors.text.emerald}>{MODE_META.hotkeys.navigate}</Text>{' '}
            <Text color={theme.colors.text.emerald}>{MODE_META.hotkeys.select}</Text>{' '}
            <Text color={theme.colors.text.emerald}>{MODE_META.hotkeys.close}</Text>
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
