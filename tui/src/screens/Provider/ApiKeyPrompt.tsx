import React, { useMemo } from 'react';
import type { ProviderState } from '../../services/providers/types';
import { FieldForm, type FormField } from './FieldForm';

interface ApiKeyPromptProps {
  provider: ProviderState;
  onBack: () => void;
  onSubmit: (values: Record<string, string>) => void;
}

export const ApiKeyPrompt: React.FC<ApiKeyPromptProps> = ({ provider, onBack, onSubmit }) => {
  const fields = useMemo<FormField[]>(() => {
    const keyField = provider.meta.fields.find((field) => field.key === 'apiKey');
    return [
      {
        key: 'apiKey',
        label: keyField?.label ?? 'API Key',
        type: 'password',
        required: true,
        placeholder: keyField?.placeholder ?? 'sk-...',
      },
    ];
  }, [provider]);

  return (
    <FieldForm
      title={`Enter API key · ${provider.meta.name}`}
      fields={fields}
      onSubmit={onSubmit}
      onCancel={onBack}
      hint="The key is sent only to the backend for validation and never displayed."
    />
  );
};
