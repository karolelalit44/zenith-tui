import React from 'react';
import { GenericProviderConfigForm } from '../components/GenericProviderConfigForm';

export const GeminiConfigForm: React.FC<{ onSaved?: () => void }> = (props) => (
  <GenericProviderConfigForm providerId="gemini" {...props} />
);
