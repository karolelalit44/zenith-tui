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
        key: 'name',
        label: 'Provider Name',
        type: 'text',
        required: true,
        defaultValue: 'Custom Provider',
        placeholder: 'e.g. TokenRouter',
      },
      {
        key: 'baseUrl',
        label: 'Base URL',
        type: 'text',
        required: true,
        placeholder: 'https://api.example.com/v1',
        description: 'Endpoint that is OpenAI-compatible.',
      },
      {
        key: 'apiKey',
        label: 'API Key',
        type: 'password',
        placeholder: 'Optional if no auth required',
      },
      {
        key: 'model',
        label: 'Default model',
        type: 'text',
        placeholder: 'llama3',
        description: 'Leave blank to auto-pick from the endpoint on validation.',
      },
    ],
    [],
  );

  return (
    <FieldForm
      title="Custom OpenAI-Compatible endpoint"
      fields={fields}
      onSubmit={onSubmit}
      onCancel={onBack}
      hint="Validation runs /models + a smoke test against the endpoint."
    />
  );
};
