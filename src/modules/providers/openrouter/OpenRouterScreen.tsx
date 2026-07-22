import React from 'react';
import { GenericProviderConfigForm } from '../components/GenericProviderConfigForm';

interface OpenRouterScreenProps {
  onBack?: () => void;
  onSaved?: () => void;
}

export const OpenRouterScreen: React.FC<OpenRouterScreenProps> = ({ onSaved }) => {
  return <GenericProviderConfigForm providerId="openrouter" onSaved={onSaved} />;
};
