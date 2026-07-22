import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { useTheme } from '../../theme/ThemeContext';
import type { Persona } from '../../types';

interface PersonaSelectModalProps {
  currentPersona: Persona;
  onSelect: (persona: Persona) => void;
  onClose: () => void;
}

interface PersonaOption {
  id: Persona;
  label: string;
  icon: string;
  desc: string;
}

const PERSONA_OPTIONS: PersonaOption[] = [
  {
    id: 'architect',
    label: 'Architect',
    icon: '◆',
    desc: 'Focuses on high-level system architecture, modular design, and long-term scalability.',
  },
  {
    id: 'debugger',
    label: 'Debugger',
    icon: '⚡',
    desc: 'Focuses on tracebacks, root-cause diagnosis, error handling, and unit test verification.',
  },
  {
    id: 'creative',
    label: 'Creative',
    icon: '✦',
    desc: 'Focuses on UI/UX design, visual hierarchy, modern color palettes, and micro-animations.',
  },
];

export const PersonaSelectModal: React.FC<PersonaSelectModalProps> = ({ currentPersona, onSelect, onClose }) => {
  const { theme } = useTheme();
  const initialIdx = PERSONA_OPTIONS.findIndex((p) => p.id === currentPersona);
  const [selectedIndex, setSelectedIndex] = useState(initialIdx >= 0 ? initialIdx : 0);

  useInput((_char, key) => {
    if (key.upArrow) {
      setSelectedIndex((prev) => Math.max(0, prev - 1));
    }
    if (key.downArrow) {
      setSelectedIndex((prev) => Math.min(PERSONA_OPTIONS.length - 1, prev + 1));
    }
    if (key.return) {
      onSelect(PERSONA_OPTIONS[selectedIndex].id);
    }
    if (key.escape) {
      onClose();
    }
  });

  return (
    <RoundedBox title="CHOOSE AGENT PERSONA" borderColor={theme.colors.border.active} hasShadow={true}>
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
            Select active AI persona specialization
          </Text>
        </Box>

        {PERSONA_OPTIONS.map((opt, idx) => {
          const isSelected = idx === selectedIndex;
          const isCurrent = opt.id === currentPersona;

          return (
            <Box key={opt.id} flexDirection="row" marginY={1} width="100%">
              <Box width={3}>
                <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.dim}>
                  {isSelected ? '▸ ' : '  '}
                </Text>
              </Box>

              <Box flexDirection="column" flexGrow={1}>
                <Box flexDirection="row" alignItems="center">
                  <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.dim}>{opt.icon} </Text>
                  <Text color={isSelected ? theme.colors.text.ethereal : theme.colors.text.dim} bold={isSelected}>
                    {opt.label}
                  </Text>
                  {isCurrent && (
                    <Text color={isSelected ? theme.colors.text.muted : theme.colors.text.dim}> (active)</Text>
                  )}
                </Box>
                <Box marginTop={0} paddingLeft={3}>
                  <Text color={isSelected ? theme.colors.text.muted : theme.colors.text.dim} italic={isSelected}>
                    {opt.desc}
                  </Text>
                </Box>
              </Box>
            </Box>
          );
        })}

        <Box marginTop={1} paddingTop={1} borderStyle="single" borderTop={true} borderColor={theme.colors.border.muted}>
          <Text color={theme.colors.text.muted}>
            <Text color={theme.colors.text.emerald}>[↑/↓]</Text> Navigate ·{' '}
            <Text color={theme.colors.text.emerald}>[↵]</Text> Select Persona ·{' '}
            <Text color={theme.colors.text.emerald}>[Esc]</Text> Close
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
