import React from 'react';
import { GenericProviderConfigForm } from '../components/GenericProviderConfigForm';

interface OpenAIScreenProps {
  onBack?: () => void;
  onSaved?: () => void;
}

export const OpenAIScreen: React.FC<OpenAIScreenProps> = ({ onSaved }) => {
  return <GenericProviderConfigForm providerId="openai" onSaved={onSaved} />;
};
