import React from 'react';
import { GenericProviderConfigForm } from '../components/GenericProviderConfigForm';

interface GroqScreenProps {
  onBack?: () => void;
  onSaved?: () => void;
}

export const GroqScreen: React.FC<GroqScreenProps> = ({ onSaved }) => {
  return <GenericProviderConfigForm providerId="groq" onSaved={onSaved} />;
};
