import { Box, Text, useInput } from 'ink';
import TextInput from 'ink-text-input';
import React, { useCallback, useState } from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { ASCII_SPINNER_FRAMES } from '../../constants/animation';
import { useTickAnimation } from '../../hooks/useTickAnimation';
import { startupService } from '../../services/data/StartupService';
import { providerService } from '../../services/providers/ProviderService';
import type { ProviderState } from '../../services/providers/types';
import { useTheme } from '../../theme/ThemeContext';
import type { AppStartupState, ProviderSetupRequest } from '../../types/startup';

interface SetupWizardProps {
  startupState: AppStartupState;
  onComplete: () => void;
  /** 'setup' = first-run wizard; 'reconfigure' = invoked from /provider command */
  mode?: 'setup' | 'reconfigure';
}

type WizardStep = 'intro' | 'select_provider' | 'enter_key' | 'select_model' | 'validating' | 'done' | 'error';

const STEP_LABELS: Record<WizardStep, string> = {
  intro: 'Welcome',
  select_provider: 'Choose Provider',
  enter_key: 'API Key',
  select_model: 'Select Model',
  validating: 'Validating...',
  done: 'Complete',
  error: 'Error',
};

export const SetupWizard: React.FC<SetupWizardProps> = ({ startupState, onComplete, mode = 'setup' }) => {
  const { theme } = useTheme();
  const isReconfigure = mode === 'reconfigure';
  const [step, setStep] = useState<WizardStep>(isReconfigure ? 'select_provider' : 'intro');
  const [providers, setProviders] = useState<ProviderState[]>(() => providerService.getAllProviders());

  React.useEffect(() => {
    providerService.refreshFromBackend().then(() => {
      setProviders(providerService.getAllProviders());
    });
  }, []);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [editingField, setEditingField] = useState(false);
  const [typingBuffer, setTypingBuffer] = useState('');
  const tick = useTickAnimation(150, step === 'validating');

  const selectedProvider = providers[selectedIdx] || providers[0];
  const models = selectedProvider.meta.availableModels || [];
  const defaultModelIndex = Math.max(
    0,
    models.findIndex((m) => m.id === selectedProvider.meta.defaultModel),
  );

  const [modelIdx, setModelIdx] = useState(0);
  // Re-sync modelIdx when selectedProvider changes
  React.useEffect(() => {
    setModelIdx(defaultModelIndex);
  }, [selectedProvider.id]);

  const handleValidateAndSave = useCallback(async () => {
    setStep('validating');
    const userSelectedModel = models[modelIdx]?.id || selectedProvider.meta.defaultModel;
    const validationModel = selectedProvider.meta.defaultModel;

    const validationRequest: ProviderSetupRequest = {
      provider: selectedProvider.id,
      api_key: apiKeyInput,
      model: validationModel,
      base_url: selectedProvider.config.baseUrl || '',
      max_tokens: 4096,
      temperature: 0.7,
    };

    const validation = await startupService.validateProvider(validationRequest);
    if (!validation.valid) {
      setErrorMsg(validation.message);
      setStep('error');
      return;
    }

    const saveRequest: ProviderSetupRequest = {
      ...validationRequest,
      model: userSelectedModel,
    };

    const saveResult = await startupService.saveProviderConfig(saveRequest);
    if (!saveResult.valid) {
      setErrorMsg(saveResult.message);
      setStep('error');
      return;
    }

    setStep('done');
    await startupService.revalidateAfterSetup();
    onComplete();
  }, [selectedProvider, apiKeyInput, modelIdx, models, onComplete]);

  useInput((char, key) => {
    if (step === 'intro') {
      if (key.return || char === ' ') setStep('select_provider');
      return;
    }

    if (step === 'select_provider') {
      if (key.escape) {
        setStep('intro');
        return;
      }
      if (key.upArrow) setSelectedIdx((p) => Math.max(0, p - 1));
      if (key.downArrow) setSelectedIdx((p) => Math.min(providers.length - 1, p + 1));
      if (key.return) {
        setApiKeyInput(selectedProvider.config.apiKey || '');
        setStep('enter_key');
      }
      return;
    }

    if (step === 'enter_key') {
      if (editingField) {
        if (key.escape) {
          setEditingField(false);
          setApiKeyInput(typingBuffer);
        }
        return;
      }

      if (key.escape) {
        setStep('select_provider');
        return;
      }
      if (key.return) {
        if (!apiKeyInput.trim()) {
          setErrorMsg('API key is required.');
          setStep('error');
          return;
        }
        setStep('select_model');
      }
      if (char === ' ') {
        setEditingField(true);
        setTypingBuffer(apiKeyInput);
      }
      return;
    }

    if (step === 'select_model') {
      if (key.escape) {
        setStep('enter_key');
        return;
      }
      if (key.upArrow) setModelIdx((p) => Math.max(0, p - 1));
      if (key.downArrow) setModelIdx((p) => Math.min(models.length - 1, p + 1));
      if (key.return) handleValidateAndSave();
      return;
    }

    if (step === 'error') {
      if (key.escape || key.return || char === ' ') {
        setErrorMsg('');
        setStep('select_provider');
      }
      return;
    }

    if (step === 'done') {
      return;
    }
  });

  const renderMissingSummary = () => {
    if (isReconfigure || !startupState.result) return null;
    const labels: Record<string, string> = {
      provider: 'AI Provider',
      model: 'Model Selection',
      apiKey: 'API Key',
      configFile: 'Configuration File',
      workspace: 'Workspace Directory',
      dbPath: 'Database Path',
    };
    return (
      <Box flexDirection="column" marginBottom={1}>
        <Text color={theme.colors.status.warning} bold>
          Missing Configuration:
        </Text>
        {startupState.result.missing.map((item) => (
          <Box key={item} marginLeft={2}>
            <Text color={theme.colors.status.error}>✗ </Text>
            <Text color={theme.colors.text.ethereal}>{labels[item] || item}</Text>
          </Box>
        ))}
      </Box>
    );
  };

  const renderStepIndicator = () => {
    const steps: WizardStep[] = ['select_provider', 'enter_key', 'select_model', 'validating'];
    const currentIdx = steps.indexOf(step);
    return (
      <Box flexDirection="row" marginBottom={1} gap={1}>
        {steps.map((s, i) => {
          const isActive = s === step;
          const isPast = i < currentIdx;
          const color = isActive
            ? theme.colors.status.success
            : isPast
              ? theme.colors.text.dim
              : theme.colors.text.muted;
          return (
            <Box key={s}>
              <Text color={color}>
                {isActive ? '▸' : isPast ? '✓' : '○'} {STEP_LABELS[s]}
                {i < steps.length - 1 ? ' → ' : ''}
              </Text>
            </Box>
          );
        })}
      </Box>
    );
  };

  const renderProviderList = () => (
    <Box flexDirection="column">
      <Text color={theme.colors.text.ethereal} bold>
        Select an AI Provider:
      </Text>
      <Box flexDirection="column" marginTop={1}>
        {providers.map((p, idx) => {
          const isSelected = idx === selectedIdx;
          return (
            <Box key={p.id} flexDirection="row" alignItems="center">
              <Box width={3}>
                <Text color={isSelected ? theme.colors.status.success : theme.colors.text.dim}>
                  {isSelected ? '▸' : ' '}
                </Text>
              </Box>
              <Box width={16}>
                <Text color={isSelected ? theme.colors.text.bright : theme.colors.text.ethereal} bold={isSelected}>
                  {p.meta.name}
                </Text>
              </Box>
              <Box flexDirection="row" marginRight={1}>
                {p.meta.swatch.map((c, i) => (
                  <Text key={i} color={c}>
                    █
                  </Text>
                ))}
              </Box>
              <Box marginLeft={1}>
                <Text color={theme.colors.text.dim}>{p.meta.description}</Text>
              </Box>
            </Box>
          );
        })}
      </Box>
    </Box>
  );

  const renderApiKeyInput = () => (
    <Box flexDirection="column">
      <Text color={theme.colors.text.ethereal} bold>
        Enter API Key for {selectedProvider.meta.name}:
      </Text>
      <Box marginTop={1} flexDirection="row">
        <Text color={theme.colors.text.muted}>Key: </Text>
        {editingField ? (
          <TextInput
            value={apiKeyInput}
            onChange={setApiKeyInput}
            onSubmit={() => {
              setEditingField(false);
              if (!apiKeyInput.trim()) {
                setErrorMsg('API key is required.');
                setStep('error');
              }
            }}
            placeholder="sk-or-v1-..."
          />
        ) : (
          <Text color={theme.colors.text.ethereal}>
            {apiKeyInput
              ? '•'.repeat(Math.min(apiKeyInput.length, 40)) + (apiKeyInput.length > 40 ? '…' : '')
              : '(press space to type)'}
          </Text>
        )}
      </Box>
      {!editingField && (
        <Box marginTop={1}>
          <Text color={theme.colors.text.dim} italic>
            Press Space to edit, Enter to continue, Esc to go back
          </Text>
        </Box>
      )}
      {editingField && (
        <Box marginTop={1}>
          <Text color={theme.colors.text.dim} italic>
            Type or paste the key, Enter to confirm, Esc to cancel
          </Text>
        </Box>
      )}
    </Box>
  );

  const renderModelList = () => (
    <Box flexDirection="column">
      <Text color={theme.colors.text.ethereal} bold>
        Select Model for {selectedProvider.meta.name}:
      </Text>
      <Box flexDirection="column" marginTop={1}>
        {models.length === 0 && (
          <Box>
            <Text color={theme.colors.text.muted}>Using default: {selectedProvider.meta.defaultModel}</Text>
            <Box marginTop={1}>
              <Text color={theme.colors.text.dim} italic>
                Press Enter to continue
              </Text>
            </Box>
          </Box>
        )}
        {models.map((m, idx) => {
          const isSelected = idx === modelIdx;
          return (
            <Box key={m.id} flexDirection="row">
              <Box width={3}>
                <Text color={isSelected ? theme.colors.status.success : theme.colors.text.dim}>
                  {isSelected ? '▸' : ' '}
                </Text>
              </Box>
              <Box flexDirection="column" width="95%">
                <Box flexDirection="row">
                  <Text color={isSelected ? theme.colors.text.bright : theme.colors.text.ethereal} bold={isSelected}>
                    {m.name || m.id}
                  </Text>
                  {m.parameters && <Text color={theme.colors.text.dim}> ({m.parameters})</Text>}
                  {m.speed_tier && (
                    <Text
                      color={
                        m.speed_tier === 'fast'
                          ? theme.colors.status.success
                          : m.speed_tier === 'moderate'
                            ? theme.colors.status.warning
                            : theme.colors.status.error
                      }
                    >
                      {' '}
                      {m.speed_tier === 'fast' ? '⚡' : m.speed_tier === 'moderate' ? '⏱' : '🐢'}
                    </Text>
                  )}
                </Box>
                {isSelected && m.description && (
                  <Box marginTop={1} marginLeft={2}>
                    <Text color={theme.colors.text.dim} italic>
                      {m.description}
                    </Text>
                  </Box>
                )}
                {isSelected && (
                  <Box flexDirection="row" flexWrap="wrap" marginTop={1} marginLeft={2} gap={1}>
                    {m.context_window && (
                      <Box flexDirection="row" marginRight={1}>
                        <Text color={theme.colors.text.muted}>Context: </Text>
                        <Text color={theme.colors.text.ethereal}>
                          {m.context_window >= 1048576
                            ? `${(m.context_window / 1048576).toFixed(0)}M`
                            : m.context_window >= 1024
                              ? `${(m.context_window / 1024).toFixed(0)}K`
                              : m.context_window}
                        </Text>
                      </Box>
                    )}
                    {m.architecture && (
                      <Box flexDirection="row" marginRight={1}>
                        <Text color={theme.colors.text.muted}>Arch: </Text>
                        <Text color={theme.colors.text.ethereal}>{m.architecture}</Text>
                      </Box>
                    )}
                    {m.input_modalities && m.input_modalities.length > 0 && (
                      <Box flexDirection="row" marginRight={1}>
                        <Text color={theme.colors.text.muted}>Input: </Text>
                        <Text color={theme.colors.text.ethereal}>{m.input_modalities.join(', ')}</Text>
                      </Box>
                    )}
                  </Box>
                )}
                {isSelected && m.tags && m.tags.length > 0 && (
                  <Box flexDirection="row" flexWrap="wrap" marginTop={1} marginLeft={2} gap={1}>
                    {m.tags.map((tag) => (
                      <Box key={tag} flexDirection="row" marginRight={1}>
                        <Text color={theme.colors.status.info}>#{tag}</Text>
                      </Box>
                    ))}
                  </Box>
                )}
                {isSelected && m.model_capabilities && (
                  <Box flexDirection="row" flexWrap="wrap" marginTop={1} marginLeft={2} gap={1}>
                    {m.model_capabilities.function_calling && (
                      <Box flexDirection="row" marginRight={1}>
                        <Text color={theme.colors.status.success}>✓</Text>
                        <Text color={theme.colors.text.dim}> Tools</Text>
                      </Box>
                    )}
                    {m.model_capabilities.structured_output && (
                      <Box flexDirection="row" marginRight={1}>
                        <Text color={theme.colors.status.success}>✓</Text>
                        <Text color={theme.colors.text.dim}> JSON</Text>
                      </Box>
                    )}
                    {m.model_capabilities.reasoning && (
                      <Box flexDirection="row" marginRight={1}>
                        <Text color={theme.colors.status.success}>✓</Text>
                        <Text color={theme.colors.text.dim}> Reasoning</Text>
                      </Box>
                    )}
                    {m.model_capabilities.thinking && (
                      <Box flexDirection="row" marginRight={1}>
                        <Text color={theme.colors.status.success}>✓</Text>
                        <Text color={theme.colors.text.dim}> Thinking</Text>
                      </Box>
                    )}
                  </Box>
                )}
                {isSelected && m.best_for && m.best_for.length > 0 && (
                  <Box marginTop={1} marginLeft={2}>
                    <Text color={theme.colors.text.muted}>Best for: </Text>
                    <Text color={theme.colors.text.ethereal}>{m.best_for.join(', ')}</Text>
                  </Box>
                )}
              </Box>
            </Box>
          );
        })}
      </Box>
    </Box>
  );

  const renderIntro = () => (
    <Box flexDirection="column">
      <Box marginBottom={1}>
        <Text color={theme.colors.status.warning} bold>
          ⚙ {isReconfigure ? 'Provider Configuration' : 'Setup Required'}
        </Text>
      </Box>
      <Text color={theme.colors.text.ethereal}>
        {isReconfigure
          ? 'Select and configure an AI provider.'
          : 'Before you can start using Zenith, some configuration is needed.'}
      </Text>
      {renderMissingSummary()}
      <Box marginTop={1}>
        <Text color={theme.colors.text.dim} italic>
          Press Enter to begin setup
        </Text>
      </Box>
    </Box>
  );

  const renderValidating = () => (
    <Box flexDirection="column">
      <Text color={theme.colors.status.info}>
        {ASCII_SPINNER_FRAMES[tick % ASCII_SPINNER_FRAMES.length]} Validating configuration...
      </Text>
      <Box marginTop={1}>
        <Text color={theme.colors.text.dim}>Provider: {selectedProvider.meta.name}</Text>
      </Box>
      <Box>
        <Text color={theme.colors.text.dim}>Model: {models[modelIdx]?.name || selectedProvider.meta.defaultModel}</Text>
      </Box>
    </Box>
  );

  const renderError = () => (
    <Box flexDirection="column">
      <Text color={theme.colors.status.error} bold>
        Configuration Error
      </Text>
      <Box marginTop={1}>
        <Text color={theme.colors.text.ethereal}>{errorMsg}</Text>
      </Box>
      <Box marginTop={1}>
        <Text color={theme.colors.text.dim} italic>
          Press Enter to retry
        </Text>
      </Box>
    </Box>
  );

  const renderDone = () => (
    <Box flexDirection="column">
      <Text color={theme.colors.status.success} bold>
        ✓ Configuration Complete
      </Text>
      <Box marginTop={1}>
        <Text color={theme.colors.text.ethereal}>
          Provider: {selectedProvider.meta.name} | Model: {models[modelIdx]?.name || selectedProvider.meta.defaultModel}
        </Text>
      </Box>
      <Box marginTop={1}>
        <Text color={theme.colors.text.dim}>Starting Zenith...</Text>
      </Box>
    </Box>
  );

  const renderStepContent = () => {
    switch (step) {
      case 'intro':
        return renderIntro();
      case 'select_provider':
        return renderProviderList();
      case 'enter_key':
        return renderApiKeyInput();
      case 'select_model':
        return renderModelList();
      case 'validating':
        return renderValidating();
      case 'done':
        return renderDone();
      case 'error':
        return renderError();
    }
  };

  const renderHotkeys = () => {
    if (step === 'intro') return 'Enter — Start Setup';
    if (step === 'select_provider') return '↑↓ — Navigate  |  Enter — Select  |  Esc — Back';
    if (step === 'enter_key')
      return editingField
        ? 'Type or paste the key  |  Enter — Confirm  |  Esc — Cancel'
        : 'Space — Edit  |  Enter — Continue  |  Esc — Back';
    if (step === 'select_model') return '↑↓ — Navigate  |  Enter — Validate & Save  |  Esc — Back';
    if (step === 'error') return 'Enter — Retry  |  Esc — Back';
    if (step === 'validating' || step === 'done') return '';
    return '';
  };

  return (
    <RoundedBox title="ZENITH SETUP" borderColor={theme.colors.status.warning} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        <Box
          marginBottom={1}
          paddingBottom={1}
          borderStyle="single"
          borderBottom={true}
          borderTop={false}
          borderLeft={false}
          borderRight={false}
          borderColor={theme.colors.border.muted}
        >
          {renderStepIndicator()}
        </Box>
        <Box flexDirection="column" minHeight={6}>
          {renderStepContent()}
        </Box>
        <Box
          marginTop={1}
          paddingTop={1}
          borderStyle="single"
          borderTop={true}
          borderBottom={false}
          borderLeft={false}
          borderRight={false}
          borderColor={theme.colors.border.muted}
        >
          <Text color={theme.colors.text.muted}>{renderHotkeys()}</Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
