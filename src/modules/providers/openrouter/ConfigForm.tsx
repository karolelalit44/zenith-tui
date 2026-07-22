import React from 'react';
import { GenericProviderConfigForm } from '../components/GenericProviderConfigForm';

export const OpenRouterConfigForm: React.FC<{ onSaved?: () => void }> = (props) => (
  <GenericProviderConfigForm providerId="openrouter" {...props} />
);
