import React from 'react';
import { GenericProviderConfigForm } from '../components/GenericProviderConfigForm';

interface CustomScreenProps {
  onBack?: () => void;
  onSaved?: () => void;
}

export const CustomScreen: React.FC<CustomScreenProps> = ({ onSaved }) => {
  return <GenericProviderConfigForm providerId="custom" onSaved={onSaved} />;
};
