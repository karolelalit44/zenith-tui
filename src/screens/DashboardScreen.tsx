import React from 'react';
import { Box, Text } from 'ink';
import { RoundedBox } from '../components/RoundedBox';
import { useTheme } from '../theme/ThemeContext';
import { Persona } from '../components/PersonaModal';

export const DashboardScreen: React.FC<{ persona: Persona }> = React.memo(({ persona }) => {
  const { theme } = useTheme();
  return (
    <RoundedBox title="v1.0.0" borderColor={theme.colors.border.active}>
      {/* Container takes full width/height, horizontally spaced between, vertically centered */}
      <Box flexGrow={1} width="100%" flexDirection="row" justifyContent="space-evenly" alignItems="center" paddingX={4} paddingY={2}>
        
        {/* Left Side */}
        <Box flexDirection="column" width={56} flexShrink={0}>
          <Box marginBottom={1} flexDirection="column">
            <Text color={theme.colors.logo[0]} bold>███████╗ ███████╗ ███╗   ██╗ ██╗ ████████╗ ██╗  ██╗</Text>
            <Text color={theme.colors.logo[1]} bold>╚══███╔╝ ██╔════╝ ████╗  ██║ ██║ ╚══██╔══╝ ██║  ██║</Text>
            <Text color={theme.colors.logo[2]} bold>  ███╔╝  █████╗   ██╔██╗ ██║ ██║    ██║    ███████║</Text>
            <Text color={theme.colors.logo[3]} bold> ███╔╝   ██╔══╝   ██║╚██╗██║ ██║    ██║    ██╔══██║</Text>
            <Text color={theme.colors.logo[4]} bold>███████╗ ███████╗ ██║ ╚████║ ██║    ██║    ██║  ██║</Text>
            <Text color={theme.colors.logo[5]} bold>╚══════╝ ╚══════╝ ╚═╝  ╚═══╝ ╚═╝    ╚═╝    ╚═╝  ╚═╝</Text>
          </Box>
          
          <Box flexDirection="column" marginTop={1}>
            <Text color={theme.colors.text.ethereal} bold>SYSTEM STATUS</Text>
            
            <Box flexDirection="row" marginTop={1}>
              <Box flexDirection="row" marginRight={4}>
                <Text color={theme.colors.text.muted}>Engine: </Text>
                <Text color={theme.colors.text.emerald}>Online (Sonnet 4.5)</Text>
              </Box>
              <Box flexDirection="row">
                <Text color={theme.colors.text.muted}>Persona: </Text>
                <Text color={theme.colors.text.warning}>{persona.charAt(0).toUpperCase() + persona.slice(1)} Mode</Text>
              </Box>
            </Box>

            <Box flexDirection="row" marginTop={1}>
              <Text color={theme.colors.text.muted}>Workspace: </Text>
              <Text color={theme.colors.text.emerald}>~/BCApps</Text>
            </Box>
          </Box>
        </Box>

        {/* Divider */}
        <Box width={1} justifyContent="center" alignItems="center">
          <Text color={theme.colors.border.muted}>║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║</Text>
        </Box>

        {/* Right Side */}
        <Box flexDirection="column" width={56} justifyContent="center">
          
          <Box marginBottom={2} flexDirection="row" flexWrap="wrap">
            <Text color={theme.colors.text.emerald} bold>
              {(() => {
                const hour = new Date().getHours();
                if (hour >= 5 && hour < 12) return <Text>Compiling coffee...</Text>;
                if (hour >= 12 && hour < 17) return <Text>Midday grind.</Text>;
                if (hour >= 17 && hour < 22) return <Text>Sun is down, screens are bright.</Text>;
                return <Text>Burning the midnight oil, John Doe?</Text>;
              })()}
            </Text>
          </Box>

          <Text color={theme.colors.text.warning} bold>● Recent Sessions</Text>
          <Box marginTop={1} flexDirection="column">
            <Box flexDirection="row" marginBottom={1}>
              <Box width={21}><Text color={theme.colors.text.muted}>[ 21:03, 20 July ] </Text></Box>
              <Box flexGrow={1} paddingRight={2}><Text color={theme.colors.text.ethereal} wrap="truncate-end">Refactored authentication flow</Text></Box>
              <Box width={12} flexDirection="row" justifyContent="flex-end">
                <Text color={theme.colors.text.muted}>│ </Text>
                <Text color={theme.colors.text.warning}>Architect</Text>
              </Box>
            </Box>
          </Box>
        </Box>

      </Box>
    </RoundedBox>
  );
});
