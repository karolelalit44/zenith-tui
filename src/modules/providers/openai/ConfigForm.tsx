import React from 'react';
import { GenericProviderConfigForm } from '../components/GenericProviderConfigForm';

export const OpenAIConfigForm: React.FC<{ onSaved?: () => void }> = (props) => (
  <GenericProviderConfigForm providerId="openai" {...props} />
);
