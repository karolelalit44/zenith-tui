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
    const list: FormField[] = [];
    const keyField = provider.meta.fields.find((field) => field.key === 'apiKey');
    list.push({
      key: 'apiKey',
      label: keyField?.label ?? 'API Key',
      type: 'password',
      required: true,
      placeholder: keyField?.placeholder ?? 'sk-...',
    });
    const baseUrlField = provider.meta.fields.find((field) => field.key === 'baseUrl' && field.required);
    if (baseUrlField) {
      list.push({
        key: 'baseUrl',
        label: baseUrlField.label ?? 'Base URL',
        type: 'text',
        required: true,
        defaultValue: provider.config.baseUrl ?? baseUrlField.defaultValue,
        placeholder: baseUrlField.placeholder,
        description: baseUrlField.description,
      });
    }
    return list;
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
