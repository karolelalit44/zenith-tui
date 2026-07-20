import React from 'react';
import { Box, Text } from 'ink';
import { RoundedBox } from '../components/RoundedBox';
import { theme } from '../theme/theme';
import { Persona } from '../components/PersonaModal';

export const DashboardScreen: React.FC<{ persona: Persona }> = React.memo(({ persona }) => {
  return (
    <RoundedBox title="Zenith v1.0.0" borderColor={theme.colors.border.active}>
      <Box flexDirection="row" width="100%">
        {/* Left Side - Rigid width to prevent ASCII wrapping */}
        <Box flexDirection="column" width={56} paddingRight={2} flexShrink={0}>
          <Box marginBottom={1} flexDirection="column">
            <Text color="#F5FFFA" bold>███████╗███████╗███╗   ██╗██╗████████╗██╗  ██╗</Text>
            <Text color="#D1E8D1" bold>╚══███╔╝██╔════╝████╗  ██║██║╚══██╔══╝██║  ██║</Text>
            <Text color="#A3CBA3" bold>  ███╔╝ █████╗  ██╔██╗ ██║██║   ██║   ███████║</Text>
            <Text color="#7CA87C" bold> ███╔╝  ██╔══╝  ██║╚██╗██║██║   ██║   ██╔══██║</Text>
            <Text color="#558055" bold>███████╗███████╗██║ ╚████║██║   ██║   ██║  ██║</Text>
            <Text color="#2E522E" bold>╚══════╝╚══════╝╚═╝  ╚═══╝╚═╝   ╚═╝   ╚═╝  ╚═╝</Text>
          </Box>
          
          <Box flexDirection="column" marginTop={1}>
            <Text color={theme.colors.text.ethereal} bold>SYSTEM STATUS</Text>
            <Box flexDirection="row" marginTop={1}>
              <Box width={15}><Text color={theme.colors.text.muted}>Engine:</Text></Box>
              <Text color={theme.colors.text.emerald}>Online (Sonnet 4.5)</Text>
            </Box>
            <Box flexDirection="row">
              <Box width={15}><Text color={theme.colors.text.muted}>Workspace:</Text></Box>
              <Text color={theme.colors.text.emerald}>~/BCApps</Text>
            </Box>
            <Box flexDirection="row">
              <Box width={15}><Text color={theme.colors.text.muted}>Context:</Text></Box>
              <Text color={theme.colors.text.emerald}>14.2 GB Available</Text>
            </Box>
            <Box flexDirection="row">
              <Box width={15}><Text color={theme.colors.text.muted}>Persona:</Text></Box>
              <Text color={theme.colors.text.warning}>{persona.charAt(0).toUpperCase() + persona.slice(1)} Mode</Text>
            </Box>
          </Box>
        </Box>

        {/* Divider */}
        <Box width={1}>
          <Text color={theme.colors.border.muted}>║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║{"\n"}║</Text>
        </Box>

        {/* Right Side - Fluid width */}
        <Box flexDirection="column" flexGrow={1} paddingLeft={2}>
          <Text color={theme.colors.text.emerald} bold>● Quick Start</Text>
          <Box marginTop={1} flexDirection="column">
            <Text color={theme.colors.text.ethereal}>Type <Text color={theme.colors.text.warning}>/help</Text> for available commands.</Text>
            <Text color={theme.colors.text.ethereal}>Type <Text color={theme.colors.text.warning}>/plugin</Text> to manage integrations.</Text>
          </Box>
          
          <Box marginTop={2} flexDirection="column">
            <Text color={theme.colors.text.emerald} bold>● Recent Activity</Text>
            <Box marginTop={1}>
              <Text color={theme.colors.text.muted}>No recent activity.</Text>
            </Box>
          </Box>
        </Box>
      </Box>
    </RoundedBox>
  );
});
