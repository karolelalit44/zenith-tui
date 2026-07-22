import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { RoundedBox } from '../../../components/ui/RoundedBox';
import { useTheme } from '../../../theme/ThemeContext';
import { Persona } from '../../../types';
import { PERSONA_OPTIONS, ACCOUNT_META } from './data/accountData';

export const AccountScreen: React.FC<{
  currentPersona: Persona;
  onSelect: (persona: Persona) => void;
  onClose: () => void;
}> = ({ currentPersona, onSelect, onClose }) => {
  const { theme } = useTheme();
  const [selectedIndex, setSelectedIndex] = useState(
    Math.max(0, PERSONA_OPTIONS.findIndex(p => p.id === currentPersona))
  );

  useInput((char, key) => {
    if (key.escape) {
      onClose();
      return;
    }

    if (key.upArrow) {
      setSelectedIndex(prev => Math.max(0, prev - 1));
    }

    if (key.downArrow) {
      setSelectedIndex(prev => Math.min(PERSONA_OPTIONS.length - 1, prev + 1));
    }

    if (key.return) {
      onSelect(PERSONA_OPTIONS[selectedIndex].id);
      onClose();
    }
  });

  return (
    <RoundedBox title={ACCOUNT_META.title} borderColor={theme.colors.border.muted} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        <Box marginBottom={1} paddingBottom={1} borderStyle="single" borderTop={false} borderLeft={false} borderRight={false} borderColor={theme.colors.border.muted}>
          <Text color={theme.colors.text.emerald}>❯ </Text>
          <Text color={theme.colors.text.ethereal} bold>{ACCOUNT_META.headerLabel}</Text>
        </Box>

        {PERSONA_OPTIONS.map((persona, idx) => {
          const isSelected = idx === selectedIndex;
          const isActive = persona.id === currentPersona;

          return (
            <Box key={persona.id} flexDirection="row" marginY={1} width="100%">
              <Box width={3}>
                <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.muted}>
                  {isSelected ? '▸ ' : '  '}
                </Text>
              </Box>

              <Box flexDirection="column" flexGrow={1}>
                <Box flexDirection="row" justifyContent="space-between" width="100%">
                  <Box flexDirection="row">
                    <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.muted}>{persona.icon} </Text>
                    <Text color={isSelected ? theme.colors.text.ethereal : theme.colors.text.muted} bold={isSelected}>
                      {persona.label}
                    </Text>
                  </Box>
                  {isActive && (
                    <Text color={theme.colors.text.warning} bold>
                      {ACCOUNT_META.activeBadge}
                    </Text>
                  )}
                </Box>
                <Box marginTop={0} paddingLeft={3}>
                  <Text color={theme.colors.text.muted} dimColor={!isSelected} italic={isSelected}>
                    {persona.desc}
                  </Text>
                </Box>
              </Box>
            </Box>
          );
        })}

        <Box marginTop={1} paddingTop={1} borderStyle="single" borderTop={true} borderLeft={false} borderRight={false} borderBottom={false} borderColor={theme.colors.border.muted} justifyContent="center">
          <Text color={theme.colors.text.muted}>
            <Text color={theme.colors.text.emerald}>{ACCOUNT_META.hotkeys.navigate}</Text>   <Text color={theme.colors.text.emerald}>{ACCOUNT_META.hotkeys.select}</Text>   <Text color={theme.colors.text.emerald}>{ACCOUNT_META.hotkeys.close}</Text>
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
