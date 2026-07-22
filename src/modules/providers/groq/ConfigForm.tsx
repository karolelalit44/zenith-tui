import React from 'react';
import { GenericProviderConfigForm } from '../components/GenericProviderConfigForm';

export const GroqConfigForm: React.FC<{ onSaved?: () => void }> = (props) => (
  <GenericProviderConfigForm providerId="groq" {...props} />
);
