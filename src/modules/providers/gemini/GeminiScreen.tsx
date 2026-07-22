import React from 'react';
import { GenericProviderConfigForm } from '../components/GenericProviderConfigForm';

interface GeminiScreenProps {
  onBack?: () => void;
  onSaved?: () => void;
}

export const GeminiScreen: React.FC<GeminiScreenProps> = ({ onSaved }) => {
  return <GenericProviderConfigForm providerId="gemini" onSaved={onSaved} />;
};
