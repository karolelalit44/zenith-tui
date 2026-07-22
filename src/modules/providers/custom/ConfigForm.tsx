import React from 'react';
import { GenericProviderConfigForm } from '../components/GenericProviderConfigForm';

export const CustomConfigForm: React.FC<{ onSaved?: () => void }> = (props) => (
  <GenericProviderConfigForm providerId="custom" {...props} />
);
