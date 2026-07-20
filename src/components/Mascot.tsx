import React from 'react';
import { Text, Box } from 'ink';

interface MascotProps {
  color?: string;
}

const MASCOT_ART = `
   ✧   
 ⟐ ✦ ⟐ 
   ✧   
`.trim();

export const Mascot: React.FC<MascotProps> = ({ color = '#D97757' }) => {
  return (
    <Box>
      <Text color={color}>{MASCOT_ART}</Text>
    </Box>
  );
};
