import React, { useState } from 'react';
import { Box, Text, useInput } from 'ink';
import { RoundedBox } from './RoundedBox';
import { useTheme } from '../theme/ThemeContext';

export const SettingsModal: React.FC<{ 
  onClose: () => void;
  onOpenTheme?: () => void;
  autoApprove: boolean;
  setAutoApprove: React.Dispatch<React.SetStateAction<boolean>>;
}> = ({ onClose, onOpenTheme, autoApprove, setAutoApprove }) => {
  const { theme } = useTheme();
  const [selectedIndex, setSelectedIndex] = useState(0);
  
  const SETTINGS = [
    { 
      id: 'theme', 
      label: 'Theme Configuration', 
      icon: '◨', 
      desc: 'Open theme editor to customize UI colors and appearance.', 
      actionType: 'navigate',
      badge: 'Deep Forest' 
    },
    { 
      id: 'autoApprove', 
      label: 'Auto-Approve Edits', 
      icon: '⚡', 
      desc: 'Automatically execute AI-suggested code changes without prompting.', 
      actionType: 'toggle', 
      badge: autoApprove ? 'ON' : 'OFF' 
    },
  ];

  useInput((char, key) => {
    if (key.escape) {
      onClose();
      return;
    }
    
    if (key.upArrow) {
      setSelectedIndex(prev => Math.max(0, prev - 1));
    }
    
    if (key.downArrow) {
      setSelectedIndex(prev => Math.min(SETTINGS.length - 1, prev + 1));
    }
    
    if (key.return) {
      const activeSetting = SETTINGS[selectedIndex];
      if (activeSetting.id === 'autoApprove') {
        setAutoApprove(prev => !prev);
      } else if (activeSetting.id === 'theme' && onOpenTheme) {
        onOpenTheme();
      }
    }
  });

  return (
    <RoundedBox title="System Settings" borderColor={theme.colors.border.muted} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        
        {/* Header / Vibe */}
        <Box marginBottom={1} paddingBottom={1} borderStyle="single" borderTop={false} borderLeft={false} borderRight={false} borderColor={theme.colors.border.muted}>
           <Text color={theme.colors.text.emerald}>❯ </Text>
           <Text color={theme.colors.text.ethereal} bold>CONFIGURE SYSTEM SETTINGS</Text>
        </Box>
        
        {/* Settings List */}
        {SETTINGS.map((setting, idx) => {
          const isSelected = idx === selectedIndex;
          
          let badgeColor = theme.colors.text.muted;
          if (setting.actionType === 'toggle') {
            badgeColor = autoApprove ? theme.colors.text.emerald : theme.colors.text.muted;
          } else {
            badgeColor = theme.colors.text.warning;
          }
          
          return (
            <Box key={setting.id} flexDirection="row" marginY={1} width="100%">
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
                     <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.muted}>{setting.icon} </Text>
                     <Text color={isSelected ? theme.colors.text.ethereal : theme.colors.text.muted} bold={isSelected}>
                        {setting.label}
                     </Text>
                   </Box>
                   <Box>
                      {setting.actionType === 'navigate' ? (
                        <Text color={isSelected ? theme.colors.text.warning : theme.colors.text.muted} bold={isSelected}>
                           {setting.badge} ↗
                        </Text>
                      ) : (
                        <Text color={badgeColor} bold={isSelected}>
                           {setting.badge === 'ON' ? '● ON' : '○ OFF'}
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

        {/* Hotkey Footer */}
        <Box marginTop={1} paddingTop={1} borderStyle="single" borderTop={true} borderLeft={false} borderRight={false} borderBottom={false} borderColor={theme.colors.border.muted} justifyContent="center">
           <Text color={theme.colors.text.muted}>
             <Text color={theme.colors.text.emerald}>[↑↓]</Text> Navigate   <Text color={theme.colors.text.emerald}>[↵]</Text> Toggle/Select   <Text color={theme.colors.text.emerald}>[Esc]</Text> Close
           </Text>
        </Box>
        
      </Box>
    </RoundedBox>
  );
};
