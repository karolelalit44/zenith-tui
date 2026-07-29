import { Box, Text, useInput } from 'ink';
import TextInput from 'ink-text-input';
import React, { useCallback, useState } from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { ASCII_SPINNER_FRAMES } from '../../constants/animation';
import { useTickAnimation } from '../../hooks/useTickAnimation';
import { startupService } from '../../services/data/StartupService';
import { providerService } from '../../services/providers/ProviderService';
import { useTheme } from '../../theme/ThemeContext';
const STEP_LABELS = {
    intro: 'Welcome',
    select_provider: 'Choose Provider',
    enter_key: 'API Key',
    select_model: 'Select Model',
    validating: 'Validating...',
    done: 'Complete',
    error: 'Error',
};
export const SetupWizard = ({ startupState, onComplete, mode = 'setup' }) => {
    const { theme } = useTheme();
    const isReconfigure = mode === 'reconfigure';
    const [step, setStep] = useState(isReconfigure ? 'select_provider' : 'intro');
    const [providers, setProviders] = useState(() => providerService.getAllProviders());
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
    const defaultModelIndex = Math.max(0, models.findIndex((m) => m.id === selectedProvider.meta.defaultModel));
    const [modelIdx, setModelIdx] = useState(0);
    // Re-sync modelIdx when selectedProvider changes
    React.useEffect(() => {
        setModelIdx(defaultModelIndex);
    }, [defaultModelIndex]);
    const handleValidateAndSave = useCallback(async () => {
        setStep('validating');
        const userSelectedModel = models[modelIdx]?.id || selectedProvider.meta.defaultModel;
        const validationRequest = {
            provider: selectedProvider.id,
            api_key: apiKeyInput,
            model: userSelectedModel,
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
        const saveRequest = {
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
            if (key.return || char === ' ')
                setStep('select_provider');
            return;
        }
        if (step === 'select_provider') {
            if (key.escape) {
                setStep('intro');
                return;
            }
            if (key.upArrow)
                setSelectedIdx((p) => Math.max(0, p - 1));
            if (key.downArrow)
                setSelectedIdx((p) => Math.min(providers.length - 1, p + 1));
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
            if (key.upArrow)
                setModelIdx((p) => Math.max(0, p - 1));
            if (key.downArrow)
                setModelIdx((p) => Math.min(models.length - 1, p + 1));
            if (key.return)
                handleValidateAndSave();
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
        if (isReconfigure || !startupState.result)
            return null;
        const labels = {
            provider: 'AI Provider',
            model: 'Model Selection',
            apiKey: 'API Key',
            configFile: 'Configuration File',
            workspace: 'Workspace Directory',
            dbPath: 'Database Path',
        };
        return (React.createElement(Box, { flexDirection: "column", marginBottom: 1 },
            React.createElement(Text, { color: theme.colors.status.warning, bold: true }, "Missing Configuration:"),
            startupState.result.missing.map((item) => (React.createElement(Box, { key: item, marginLeft: 2 },
                React.createElement(Text, { color: theme.colors.status.error }, "\u2717 "),
                React.createElement(Text, { color: theme.colors.text.ethereal }, labels[item] || item))))));
    };
    const renderStepIndicator = () => {
        const steps = ['select_provider', 'enter_key', 'select_model', 'validating'];
        const currentIdx = steps.indexOf(step);
        return (React.createElement(Box, { flexDirection: "row", marginBottom: 1, gap: 1 }, steps.map((s, i) => {
            const isActive = s === step;
            const isPast = i < currentIdx;
            const color = isActive
                ? theme.colors.status.success
                : isPast
                    ? theme.colors.text.dim
                    : theme.colors.text.muted;
            return (React.createElement(Box, { key: s },
                React.createElement(Text, { color: color },
                    isActive ? '▸' : isPast ? '✓' : '○',
                    " ",
                    STEP_LABELS[s],
                    i < steps.length - 1 ? ' → ' : '')));
        })));
    };
    const renderProviderList = () => (React.createElement(Box, { flexDirection: "column" },
        React.createElement(Text, { color: theme.colors.text.ethereal, bold: true }, "Select an AI Provider:"),
        React.createElement(Box, { flexDirection: "column", marginTop: 1 }, providers.map((p, idx) => {
            const isSelected = idx === selectedIdx;
            return (React.createElement(Box, { key: p.id, flexDirection: "row", alignItems: "center" },
                React.createElement(Box, { width: 3 },
                    React.createElement(Text, { color: isSelected ? theme.colors.status.success : theme.colors.text.dim }, isSelected ? '▸' : ' ')),
                React.createElement(Box, { width: 16 },
                    React.createElement(Text, { color: isSelected ? theme.colors.text.bright : theme.colors.text.ethereal, bold: isSelected }, p.meta.name)),
                React.createElement(Box, { flexDirection: "row", marginRight: 1 }, p.meta.swatch.map((c, i) => (React.createElement(Text, { key: i, color: c }, "\u2588")))),
                React.createElement(Box, { marginLeft: 1 },
                    React.createElement(Text, { color: theme.colors.text.dim }, p.meta.description))));
        }))));
    const renderApiKeyInput = () => (React.createElement(Box, { flexDirection: "column" },
        React.createElement(Text, { color: theme.colors.text.ethereal, bold: true },
            "Enter API Key for ",
            selectedProvider.meta.name,
            ":"),
        React.createElement(Box, { marginTop: 1, flexDirection: "row" },
            React.createElement(Text, { color: theme.colors.text.muted }, "Key: "),
            editingField ? (React.createElement(TextInput, { value: apiKeyInput, onChange: setApiKeyInput, onSubmit: () => {
                    setEditingField(false);
                    if (!apiKeyInput.trim()) {
                        setErrorMsg('API key is required.');
                        setStep('error');
                    }
                }, placeholder: "sk-or-v1-..." })) : (React.createElement(Text, { color: theme.colors.text.ethereal }, apiKeyInput
                ? '•'.repeat(Math.min(apiKeyInput.length, 40)) + (apiKeyInput.length > 40 ? '…' : '')
                : '(press space to type)'))),
        !editingField && (React.createElement(Box, { marginTop: 1 },
            React.createElement(Text, { color: theme.colors.text.dim, italic: true }, "Press Space to edit, Enter to continue, Esc to go back"))),
        editingField && (React.createElement(Box, { marginTop: 1 },
            React.createElement(Text, { color: theme.colors.text.dim, italic: true }, "Type or paste the key, Enter to confirm, Esc to cancel")))));
    const renderModelList = () => (React.createElement(Box, { flexDirection: "column" },
        React.createElement(Text, { color: theme.colors.text.ethereal, bold: true },
            "Select Model for ",
            selectedProvider.meta.name,
            ":"),
        React.createElement(Box, { flexDirection: "column", marginTop: 1 },
            models.length === 0 && (React.createElement(Box, null,
                React.createElement(Text, { color: theme.colors.text.muted },
                    "Using default: ",
                    selectedProvider.meta.defaultModel),
                React.createElement(Box, { marginTop: 1 },
                    React.createElement(Text, { color: theme.colors.text.dim, italic: true }, "Press Enter to continue")))),
            models.map((m, idx) => {
                const isSelected = idx === modelIdx;
                return (React.createElement(Box, { key: m.id, flexDirection: "row" },
                    React.createElement(Box, { width: 3 },
                        React.createElement(Text, { color: isSelected ? theme.colors.status.success : theme.colors.text.dim }, isSelected ? '▸' : ' ')),
                    React.createElement(Box, { flexDirection: "column", width: "95%" },
                        React.createElement(Box, { flexDirection: "row" },
                            React.createElement(Text, { color: isSelected ? theme.colors.text.bright : theme.colors.text.ethereal, bold: isSelected }, m.name || m.id),
                            m.parameters && React.createElement(Text, { color: theme.colors.text.dim },
                                " (",
                                m.parameters,
                                ")"),
                            m.speed_tier && (React.createElement(Text, { color: m.speed_tier === 'fast'
                                    ? theme.colors.status.success
                                    : m.speed_tier === 'moderate'
                                        ? theme.colors.status.warning
                                        : theme.colors.status.error },
                                ' ',
                                m.speed_tier === 'fast' ? '⚡' : m.speed_tier === 'moderate' ? '⏱' : '🐢'))),
                        isSelected && m.description && (React.createElement(Box, { marginTop: 1, marginLeft: 2 },
                            React.createElement(Text, { color: theme.colors.text.dim, italic: true }, m.description))),
                        isSelected && (React.createElement(Box, { flexDirection: "row", flexWrap: "wrap", marginTop: 1, marginLeft: 2, gap: 1 },
                            m.context_window && (React.createElement(Box, { flexDirection: "row", marginRight: 1 },
                                React.createElement(Text, { color: theme.colors.text.muted }, "Context: "),
                                React.createElement(Text, { color: theme.colors.text.ethereal }, m.context_window >= 1048576
                                    ? `${(m.context_window / 1048576).toFixed(0)}M`
                                    : m.context_window >= 1024
                                        ? `${(m.context_window / 1024).toFixed(0)}K`
                                        : m.context_window))),
                            m.architecture && (React.createElement(Box, { flexDirection: "row", marginRight: 1 },
                                React.createElement(Text, { color: theme.colors.text.muted }, "Arch: "),
                                React.createElement(Text, { color: theme.colors.text.ethereal }, m.architecture))),
                            m.input_modalities && m.input_modalities.length > 0 && (React.createElement(Box, { flexDirection: "row", marginRight: 1 },
                                React.createElement(Text, { color: theme.colors.text.muted }, "Input: "),
                                React.createElement(Text, { color: theme.colors.text.ethereal }, m.input_modalities.join(', ')))))),
                        isSelected && m.tags && m.tags.length > 0 && (React.createElement(Box, { flexDirection: "row", flexWrap: "wrap", marginTop: 1, marginLeft: 2, gap: 1 }, m.tags.map((tag) => (React.createElement(Box, { key: tag, flexDirection: "row", marginRight: 1 },
                            React.createElement(Text, { color: theme.colors.status.info },
                                "#",
                                tag)))))),
                        isSelected && m.model_capabilities && (React.createElement(Box, { flexDirection: "row", flexWrap: "wrap", marginTop: 1, marginLeft: 2, gap: 1 },
                            m.model_capabilities.function_calling && (React.createElement(Box, { flexDirection: "row", marginRight: 1 },
                                React.createElement(Text, { color: theme.colors.status.success }, "\u2713"),
                                React.createElement(Text, { color: theme.colors.text.dim }, " Tools"))),
                            m.model_capabilities.structured_output && (React.createElement(Box, { flexDirection: "row", marginRight: 1 },
                                React.createElement(Text, { color: theme.colors.status.success }, "\u2713"),
                                React.createElement(Text, { color: theme.colors.text.dim }, " JSON"))),
                            m.model_capabilities.reasoning && (React.createElement(Box, { flexDirection: "row", marginRight: 1 },
                                React.createElement(Text, { color: theme.colors.status.success }, "\u2713"),
                                React.createElement(Text, { color: theme.colors.text.dim }, " Reasoning"))),
                            m.model_capabilities.thinking && (React.createElement(Box, { flexDirection: "row", marginRight: 1 },
                                React.createElement(Text, { color: theme.colors.status.success }, "\u2713"),
                                React.createElement(Text, { color: theme.colors.text.dim }, " Thinking"))))),
                        isSelected && m.best_for && m.best_for.length > 0 && (React.createElement(Box, { marginTop: 1, marginLeft: 2 },
                            React.createElement(Text, { color: theme.colors.text.muted }, "Best for: "),
                            React.createElement(Text, { color: theme.colors.text.ethereal }, m.best_for.join(', ')))))));
            }))));
    const renderIntro = () => (React.createElement(Box, { flexDirection: "column" },
        React.createElement(Box, { marginBottom: 1 },
            React.createElement(Text, { color: theme.colors.status.warning, bold: true },
                "\u2699 ",
                isReconfigure ? 'Provider Configuration' : 'Setup Required')),
        React.createElement(Text, { color: theme.colors.text.ethereal }, isReconfigure
            ? 'Select and configure an AI provider.'
            : 'Before you can start using Zenith, some configuration is needed.'),
        renderMissingSummary(),
        React.createElement(Box, { marginTop: 1 },
            React.createElement(Text, { color: theme.colors.text.dim, italic: true }, "Press Enter to begin setup"))));
    const renderValidating = () => (React.createElement(Box, { flexDirection: "column" },
        React.createElement(Text, { color: theme.colors.status.info },
            ASCII_SPINNER_FRAMES[tick % ASCII_SPINNER_FRAMES.length],
            " Validating configuration..."),
        React.createElement(Box, { marginTop: 1 },
            React.createElement(Text, { color: theme.colors.text.dim },
                "Provider: ",
                selectedProvider.meta.name)),
        React.createElement(Box, null,
            React.createElement(Text, { color: theme.colors.text.dim },
                "Model: ",
                models[modelIdx]?.name || selectedProvider.meta.defaultModel))));
    const renderError = () => (React.createElement(Box, { flexDirection: "column" },
        React.createElement(Text, { color: theme.colors.status.error, bold: true }, "Configuration Error"),
        React.createElement(Box, { marginTop: 1 },
            React.createElement(Text, { color: theme.colors.text.ethereal }, errorMsg)),
        React.createElement(Box, { marginTop: 1 },
            React.createElement(Text, { color: theme.colors.text.dim, italic: true }, "Press Enter to retry"))));
    const renderDone = () => (React.createElement(Box, { flexDirection: "column" },
        React.createElement(Text, { color: theme.colors.status.success, bold: true }, "\u2713 Configuration Complete"),
        React.createElement(Box, { marginTop: 1 },
            React.createElement(Text, { color: theme.colors.text.ethereal },
                "Provider: ",
                selectedProvider.meta.name,
                " | Model: ",
                models[modelIdx]?.name || selectedProvider.meta.defaultModel)),
        React.createElement(Box, { marginTop: 1 },
            React.createElement(Text, { color: theme.colors.text.dim }, "Starting Zenith..."))));
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
        if (step === 'intro')
            return 'Enter — Start Setup';
        if (step === 'select_provider')
            return '↑↓ — Navigate  |  Enter — Select  |  Esc — Back';
        if (step === 'enter_key')
            return editingField
                ? 'Type or paste the key  |  Enter — Confirm  |  Esc — Cancel'
                : 'Space — Edit  |  Enter — Continue  |  Esc — Back';
        if (step === 'select_model')
            return '↑↓ — Navigate  |  Enter — Validate & Save  |  Esc — Back';
        if (step === 'error')
            return 'Enter — Retry  |  Esc — Back';
        if (step === 'validating' || step === 'done')
            return '';
        return '';
    };
    return (React.createElement(RoundedBox, { title: "ZENITH SETUP", borderColor: theme.colors.status.warning, hasShadow: true },
        React.createElement(Box, { flexDirection: "column", paddingX: 2, paddingY: 1, width: "100%" },
            React.createElement(Box, { marginBottom: 1, paddingBottom: 1, borderStyle: "single", borderBottom: true, borderTop: false, borderLeft: false, borderRight: false, borderColor: theme.colors.border.muted }, renderStepIndicator()),
            React.createElement(Box, { flexDirection: "column", minHeight: 6 }, renderStepContent()),
            React.createElement(Box, { marginTop: 1, paddingTop: 1, borderStyle: "single", borderTop: true, borderBottom: false, borderLeft: false, borderRight: false, borderColor: theme.colors.border.muted },
                React.createElement(Text, { color: theme.colors.text.muted }, renderHotkeys())))));
};
