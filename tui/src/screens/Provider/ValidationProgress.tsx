import { Box, Text, useInput } from 'ink';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { providerRepository } from '../../services/providers/ProviderRepository';
import type {
  ProviderModelInfo,
  ValidateProviderOptions,
  ValidationResult,
  ValidationStep,
  ValidationStepStatus,
} from '../../services/providers/types';
import { useTheme } from '../../theme/ThemeContext';

interface ValidationProgressProps {
  providerID: string;
  providerName: string;
  options: ValidateProviderOptions;
  onResult: (result: ValidationResult) => void;
  onClose: () => void;
}

const STATUS_GLYPH: Record<ValidationStepStatus, string> = {
  pending: '◌',
  running: '◉',
  success: '',
  failed: '✕',
};

function errorHint(code: string | null, message: string, providerName: string): string {
  switch (code) {
    case 'MISSING_API_KEY':
      return `Enter your API key for ${providerName}.`;
    case 'AUTH_FAILED':
      return 'The API key was rejected. Double-check the key and try again.';
    case 'CONNECTION_TIMEOUT':
      return 'Connection timed out. Check your network and the base URL.';
    case 'CONNECTION_FAILED':
      return 'Could not reach the endpoint. Verify the base URL.';
    case 'INVALID_BASE_URL':
      return 'The base URL looks invalid. Check it and try again.';
    case 'MISSING_BASE_URL':
      return 'A base URL is required for this provider.';
    case 'NO_MODELS_FOUND':
      return 'No models were discovered at this endpoint. Enter a model manually.';
    case 'SMOKE_TEST_FAILED':
      return 'The model failed the connectivity test. Try another model.';
    case 'SAVE_FAILED':
      return 'Could not save the configuration on the backend.';
    default:
      return message || 'Validation failed.';
  }
}

export const ValidationProgress: React.FC<ValidationProgressProps> = ({
  providerID,
  providerName,
  options,
  onResult,
  onClose,
}) => {
  const { theme } = useTheme();
  const [steps, setSteps] = useState<ValidationStep[]>([]);
  const [models, setModels] = useState<ProviderModelInfo[]>([]);
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const [runId, setRunId] = useState(0);
  const onResultRef = useRef(onResult);

  useEffect(() => {
    onResultRef.current = onResult;
  }, [onResult]);

  useEffect(() => {
    void runId;
    let cancelled = false;
    let discovered: ProviderModelInfo[] = [];

    (async () => {
      try {
        for await (const event of providerRepository.validateProviderStream(providerID, options)) {
          if (cancelled) return;
          if (event.type === 'step' && event.key) {
            setSteps((prev) => {
              const idx = prev.findIndex((step) => step.key === event.key);
              const next: ValidationStep = {
                key: event.key!,
                label: event.label ?? '',
                status: (event.status as ValidationStepStatus) ?? 'pending',
                message: event.message ?? '',
              };
              if (idx < 0) return [...prev, next];
              return prev.map((step, i) => (i === idx ? next : step));
            });
          } else if (event.type === 'model' && event.model) {
            const model = event.model;
            discovered = [...discovered, model];
            setModels((prev) => [...prev, model]);
          } else if (event.type === 'result') {
            const res: ValidationResult = {
              valid: event.valid ?? false,
              provider: event.provider ?? providerID,
              steps: event.steps ?? [],
              models: event.models ?? discovered,
              error: event.error ?? null,
            };
            setResult(res);
            setSteps(res.steps);
            if (res.valid) {
              onResultRef.current(res);
            }
          }
        }
      } catch {
        if (!cancelled) {
          setFatal('Could not reach the backend. Check that the server is running.');
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [providerID, options, runId]);

  const retry = useCallback(() => {
    setSteps([]);
    setModels([]);
    setResult(null);
    setFatal(null);
    setRunId((r) => r + 1);
  }, []);

  useInput((_char, key) => {
    if (key.escape) {
      onClose();
      return;
    }
    if (key.return && result && !result.valid) {
      retry();
    }
  });

  const failed = result && !result.valid;
  const running = !result && !fatal;

  const glyphColor: Record<ValidationStepStatus, string | undefined> = {
    pending: theme.colors.text.dim,
    running: theme.colors.status.accent,
    success: theme.colors.status.success,
    failed: theme.colors.status.error,
  };

  return (
    <Box flexDirection="column" width="100%" paddingLeft={2} paddingRight={2} paddingTop={1} paddingBottom={1}>
      <Box flexDirection="row" justifyContent="space-between">
        <Text color={theme.colors.text.ethereal} bold>
          Validating {providerName}
        </Text>
        <Text color={theme.colors.text.muted}>esc</Text>
      </Box>

      <Box flexDirection="column" marginTop={1} gap={0}>
        {steps.length === 0 && (
          <Text color={theme.colors.text.dim}>{running ? 'Connecting to backend…' : (fatal ?? 'Waiting…')}</Text>
        )}
        {steps.map((step) => {
          const active = step.status === 'running';
          const done = step.status === 'success';
          const bad = step.status === 'failed';
          return (
            <Box key={step.key} flexDirection="row">
              <Box width={2} flexShrink={0}>
                <Text color={glyphColor[step.status]}>{STATUS_GLYPH[step.status]}</Text>
              </Box>
              <Text
                color={bad ? theme.colors.status.error : done ? theme.colors.text.ethereal : theme.colors.text.ethereal}
                bold={active || bad}
              >
                {step.label}
              </Text>
              {step.message && (
                <Text color={theme.colors.text.dim}>
                  {' '}
                  <Text italic>{step.message}</Text>
                </Text>
              )}
            </Box>
          );
        })}
      </Box>

      {models.length > 0 && !result && (
        <Box flexDirection="row" marginTop={1}>
          <Text color={theme.colors.text.muted}>{models.length} model(s) discovered…</Text>
        </Box>
      )}

      {failed && result?.error && (
        <Box flexDirection="column" marginTop={1}>
          <Text color={theme.colors.status.error} bold>
            Validation failed
          </Text>
          <Text color={theme.colors.text.ethereal}>
            {errorHint(result.error.code, result.error.message, providerName)}
          </Text>
        </Box>
      )}

      {fatal && (
        <Box flexDirection="column" marginTop={1}>
          <Text color={theme.colors.status.error} bold>
            Connection error
          </Text>
          <Text color={theme.colors.text.ethereal}>{fatal}</Text>
        </Box>
      )}

      {(failed || fatal) && (
        <Box flexDirection="row" justifyContent="space-between" marginTop={1}>
          <Text color={theme.colors.text.muted}>Enter to retry</Text>
          <Text color={theme.colors.text.muted}>esc to go back</Text>
        </Box>
      )}
    </Box>
  );
};
