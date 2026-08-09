import React, { useMemo } from 'react';
import { FieldForm, type FormField } from './FieldForm';

interface CustomProviderPromptProps {
  onBack: () => void;
  onSubmit: (values: Record<string, string>) => void;
}

export const CustomProviderPrompt: React.FC<CustomProviderPromptProps> = ({ onBack, onSubmit }) => {
  const fields = useMemo<FormField[]>(
    () => [
      {
        key: 'baseUrl',
        label: 'Provider URL',
        type: 'text',
        required: true,
        placeholder: 'https://api.example.com/v1',
        description: 'OpenAI-compatible endpoint base URL.',
      },
      {
        key: 'apiKey',
        label: 'API Key',
        type: 'password',
        placeholder: 'Optional if no auth required',
      },
      {
        key: 'model',
        label: 'Model ID',
        type: 'text',
        required: true,
        placeholder: 'my-model-name',
        description: 'Model identifier this endpoint exposes.',
      },
    ],
    [],
  );

  return (
    <FieldForm
      title="Custom Provider"
      fields={fields}
      onSubmit={onSubmit}
      onCancel={onBack}
      hint="Validation runs /models + a smoke test against the endpoint."
    />
  );
};
