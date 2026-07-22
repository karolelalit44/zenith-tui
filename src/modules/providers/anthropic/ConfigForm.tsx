import React from 'react';
import { GenericProviderConfigForm } from '../components/GenericProviderConfigForm';

export const AnthropicConfigForm: React.FC<{ onSaved?: () => void }> = (props) => (
  <GenericProviderConfigForm providerId="anthropic" {...props} />
);
