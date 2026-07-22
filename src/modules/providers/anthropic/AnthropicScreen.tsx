import React from 'react';
import { GenericProviderConfigForm } from '../components/GenericProviderConfigForm';

interface AnthropicScreenProps {
  onBack?: () => void;
  onSaved?: () => void;
}

export const AnthropicScreen: React.FC<AnthropicScreenProps> = ({ onSaved }) => {
  return <GenericProviderConfigForm providerId="anthropic" onSaved={onSaved} />;
};
