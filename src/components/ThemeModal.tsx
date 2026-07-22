import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { RoundedBox } from './RoundedBox';
import { useTheme } from '../theme/ThemeContext';

const THEMES = [
  { id: 'deep_forest', label: 'Deep Forest', icon: '🌲', desc: 'Default dark green and ethereal hues.' },
  { id: 'synthwave', label: 'Synthwave', icon: '🌆', desc: 'Neon pinks, purples, and retrowave styling.' },
  { id: 'monokai', label: 'Monokai Pro', icon: '🎨', desc: 'Vibrant, high-contrast editor colors.' },
  { id: 'dracula', label: 'Dracula', icon: '🧛', desc: 'A dark theme for vampires.' },
  { id: 'graphite', label: 'Graphite Monochrome', icon: '⚙️', desc: 'Sleek, low-profile, grayscale aesthetic.' }
];

export const ThemeModal: React.FC<{ 
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
      setSelectedIndex(prev => Math.min(THEMES.length - 1, prev + 1));
    }
    
    if (key.return) {
      const selected = THEMES[selectedIndex].id;
      setActiveTheme(selected);
      setTheme(selected);
      if (onSelect) onSelect(selected);
      onClose();
    }
  });

  return (
    <RoundedBox title="Theme Engine" borderColor={theme.colors.border.muted} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        
        {/* Header / Vibe */}
        <Box marginBottom={1} paddingBottom={1} borderStyle="single" borderTop={false} borderLeft={false} borderRight={false} borderColor={theme.colors.border.muted}>
           <Text color={theme.colors.text.emerald}>❯ </Text>
           <Text color={theme.colors.text.ethereal} bold>SELECT UI THEME</Text>
        </Box>
        
        {/* Theme List */}
        {THEMES.map((t, idx) => {
          const isSelected = idx === selectedIndex;
          const isActive = t.id === activeTheme;
          
          return (
            <Box key={t.id} flexDirection="row" marginY={1} width="100%">
              {/* Active Indicator Bar (Left Edge) */}
              <Box width={3}>
                 <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.muted}>
                    {isSelected ? '▎ ' : '  '}
                 </Text>
              </Box>
              
              {/* Content */}
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
                         ● ACTIVE
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

        {/* Hotkey Footer */}
        <Box marginTop={1} paddingTop={1} borderStyle="single" borderTop={true} borderLeft={false} borderRight={false} borderBottom={false} borderColor={theme.colors.border.muted} justifyContent="center">
           <Text color={theme.colors.text.muted}>
             <Text color={theme.colors.text.emerald}>[↑↓]</Text> Navigate   <Text color={theme.colors.text.emerald}>[↵]</Text> Apply Theme   <Text color={theme.colors.text.emerald}>[Esc]</Text> Close
           </Text>
        </Box>
        
      </Box>
    </RoundedBox>
  );
};
