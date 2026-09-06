import React, { useMemo } from 'react';
import { FieldForm, type FormField } from './FieldForm';

interface LocalLLMPromptProps {
  baseUrl: string;
  onBack: () => void;
  onSubmit: (values: Record<string, string>) => void;
}

/**
 * Local LLM setup — only the model ID is asked for; the endpoint is fixed to
 * the local server address (e.g. llama.cpp's `llama-server`, LM Studio, Ollama).
 */
export const LocalLLMPrompt: React.FC<LocalLLMPromptProps> = ({ baseUrl, onBack, onSubmit }) => {
  const fields = useMemo<FormField[]>(
    () => [
      {
        key: 'model',
        label: 'Model ID',
        type: 'text',
        required: true,
        placeholder: 'deepseek-r1-distill-qwen-7b-q4_k_m',
        description: 'The model name/path exposed by your local server.',
      },
    ],
    [],
  );

  return (
    <FieldForm
      title="Local LLM"
      fields={fields}
      onSubmit={onSubmit}
      onCancel={onBack}
      hint={`Connects to ${baseUrl} · start your local server first, then validate here.`}
    />
  );
};
