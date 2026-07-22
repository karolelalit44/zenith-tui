import { Box } from 'ink';
import React from 'react';
import type { ProviderState } from '../types';
import { ProviderCard } from './ProviderCard';

interface ProviderListProps {
  providers: ProviderState[];
  selectedIndex: number;
}

export const ProviderList: React.FC<ProviderListProps> = ({ providers, selectedIndex }) => {
  return (
    <Box flexDirection="column" width="100%">
      {providers.map((p, idx) => (
        <ProviderCard key={p.id} provider={p} isSelected={idx === selectedIndex} />
      ))}
    </Box>
  );
};
