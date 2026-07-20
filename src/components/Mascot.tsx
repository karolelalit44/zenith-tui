import React from 'react';
import { Text } from 'ink';

export const Mascot: React.FC<{ color?: string; persona?: 'architect' | 'debugger' | 'creative' }> = ({ 
  color = '#8FBC8F', 
  persona = 'architect' 
}) => {
  let ascii = '';
  if (persona === 'architect') {
    ascii = `
   ✧   
 ⟐ ✦ ⟐ 
   ✧   
    `;
  } else if (persona === 'debugger') {
    ascii = `
  [■]  
  >_<  
  [■]  
    `;
  } else if (persona === 'creative') {
    ascii = `
  ~o~  
 ( ✿ ) 
  ~o~  
    `;
  }

  return <Text color={color}>{ascii}</Text>;
};
