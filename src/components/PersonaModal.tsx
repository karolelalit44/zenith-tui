import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { RoundedBox } from './RoundedBox';
import { theme } from '../theme/theme';

export type Persona = 'architect' | 'debugger' | 'creative';

const PERSONAS: { id: Persona; label: string; desc: string }[] = [
  { id: 'architect', label: 'The Architect', desc: 'Default logic and balanced code generation.' },
  { id: 'debugger', label: 'The Debugger', desc: 'Hyper-focused on stack traces and bug hunting.' },
  { id: 'creative', label: 'The Creative', desc: 'Optimized for UI/UX design and aesthetic styling.' },
];

export const PersonaModal: React.FC<{ 
  currentPersona: Persona; 
  onSelect: (persona: Persona) => void;
  onClose: () => void;
}> = ({ currentPersona, onSelect, onClose }) => {
  const [selectedIndex, setSelectedIndex] = useState(
    Math.max(0, PERSONAS.findIndex(p => p.id === currentPersona))
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
      setSelectedIndex(prev => Math.min(PERSONAS.length - 1, prev + 1));
    }
    
    if (key.return) {
      onSelect(PERSONAS[selectedIndex].id);
      onClose();
    }
  });

  return (
    <RoundedBox title="Select Persona" borderColor={theme.colors.border.muted} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1}>
        <Box marginBottom={1}>
          <Text color={theme.colors.text.muted}>(arrows to select, enter to apply, esc to close)</Text>
        </Box>
        
        {PERSONAS.map((persona, idx) => {
          const isSelected = idx === selectedIndex;
          return (
            <Box key={persona.id} flexDirection="column" marginBottom={1}>
              <Box flexDirection="row">
                <Box width={3}>
                  <Text color={isSelected ? theme.colors.text.emerald : 'transparent'}>{'> '}</Text>
                </Box>
                <Text color={isSelected ? theme.colors.text.ethereal : theme.colors.text.muted} bold={isSelected}>
                  {persona.label}
                </Text>
                {persona.id === currentPersona && (
                  <Text color={theme.colors.text.emerald}> (Active)</Text>
                )}
              </Box>
              <Box paddingLeft={3}>
                <Text color={theme.colors.text.muted}>{persona.desc}</Text>
              </Box>
            </Box>
          );
        })}
      </Box>
    </RoundedBox>
  );
};
