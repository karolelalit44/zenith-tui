import { Box, Text, useInput } from 'ink';
import TextInput from 'ink-text-input';
import React, { useState } from 'react';
import { modelService } from '../../services/providers/ModelService';
import { providerRepository } from '../../services/providers/ProviderRepository';
import { providerService } from '../../services/providers/ProviderService';
import type { ProviderConfig, ProviderId } from '../../services/providers/types';
import { useTheme } from '../../theme/ThemeContext';

interface GenericProviderConfigFormProps {
  providerId: ProviderId;
  onSaved?: () => void;
  onBack?: () => void;
}

export const GenericProviderConfigForm: React.FC<GenericProviderConfigFormProps> = ({
  providerId,
  onSaved,
  onBack,
}) => {
  const { theme } = useTheme();
  const meta = providerRepository.getProviderMeta(providerId);
  const initialConfig = providerService.getProviderState(providerId).config;

  const catalogModels = modelService.getModels(providerId);
  const modelsLabel = modelService.getTotalModelsLabel(providerId);

  const [formState, setFormState] = useState<ProviderConfig>(initialConfig);
  const [fieldCursor, setFieldCursor] = useState(0);
  const [isEditing, setIsEditing] = useState(false);
  const [activeSection, setActiveSection] = useState<'fields' | 'models'>('fields');

  const initialModelIdx = catalogModels.findIndex((m) => m.id === initialConfig.model);
  const [catalogCursor, setCatalogCursor] = useState(initialModelIdx >= 0 ? initialModelIdx : 0);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  // Non-select form fields
  const fields = (meta.fields || []).filter((f) => f.key !== 'model');

  const selectedCatalogModel = catalogModels[catalogCursor] || catalogModels[0];

  useInput((char, key) => {
    setSaveMessage(null);

    // Escape navigates back
    if (key.escape && !isEditing && onBack) {
      onBack();
      return;
    }

    // Text editing mode: let TextInput handle all input
    if (isEditing && activeSection === 'fields') {
      if (key.return || key.escape) {
        setIsEditing(false);
      }
      return;
    }

    // Tab toggles section focus
    if (key.tab) {
      setActiveSection((prev) => (prev === 'fields' ? 'models' : 'fields'));
      return;
    }

    if (activeSection === 'fields') {
      if (key.upArrow) {
        setFieldCursor((prev) => Math.max(0, prev - 1));
      }

      if (key.downArrow) {
        if (fieldCursor >= fields.length - 1) {
          setActiveSection('models');
        } else {
          setFieldCursor((prev) => prev + 1);
        }
      }

      const currentField = fields[fieldCursor];
      if (currentField && (key.return || char === ' ')) {
        setIsEditing(true);
      }
    } else {
      // Model Catalog Scrolling Navigation Mode
      if (key.upArrow) {
        if (catalogCursor === 0) {
          setActiveSection('fields');
        } else {
          setCatalogCursor((prev) => Math.max(0, prev - 1));
        }
      }

      if (key.downArrow) {
        setCatalogCursor((prev) => Math.min(catalogModels.length - 1, prev + 1));
      }

      if (key.pageDown) {
        setCatalogCursor((prev) => Math.min(catalogModels.length - 1, prev + 3));
      }

      if (key.pageUp) {
        setCatalogCursor((prev) => Math.max(0, prev - 3));
      }

      if (key.return || char === ' ') {
        const chosen = catalogModels[catalogCursor];
        if (chosen) {
          const updated = { ...formState, model: chosen.id };
          setFormState(updated);
          providerService.updateConfig(providerId, updated);
          setSaveMessage(`✓ Selected Model: ${chosen.name} (${chosen.id})`);
          if (onSaved) onSaved();
        }
      }
    }

    // Save shortcut: Ctrl+S
    if (key.ctrl && (char === 's' || char === 'S')) {
      const chosenModel = catalogModels[catalogCursor]?.id || formState.model;
      const updated = { ...formState, model: chosenModel };
      setFormState(updated);
      providerService.updateConfig(providerId, updated);
      setSaveMessage('✓ Configuration & active model saved cleanly');
      if (onSaved) onSaved();
    }
  });

  // Calculate scroll viewport window (5 items max)
  const VISIBLE_COUNT = 5;
  const half = Math.floor(VISIBLE_COUNT / 2);
  let startIndex = Math.max(0, catalogCursor - half);
  if (startIndex + VISIBLE_COUNT > catalogModels.length) {
    startIndex = Math.max(0, catalogModels.length - VISIBLE_COUNT);
  }
  const visibleModels = catalogModels.slice(startIndex, startIndex + VISIBLE_COUNT);

  return (
    <Box flexDirection="column" width="100%" paddingX={2} paddingY={1}>
      {/* Header */}
      <Box flexDirection="row" alignItems="center" marginBottom={1}>
        <Text color={theme.colors.text.emerald} bold>
          {meta.name} Configuration
        </Text>
        <Text color={theme.colors.text.muted}> ({meta.description})</Text>
      </Box>

      {/* Configuration Form Fields */}
      <Box flexDirection="column" marginBottom={1}>
        <Box marginBottom={0}>
          <Text color={theme.colors.text.warning} bold underline>
            [1] Provider Settings & Keys
          </Text>
        </Box>

        {fields.map((field, idx) => {
          const isSelected = activeSection === 'fields' && idx === fieldCursor;
          const rawValue = formState[field.key];
          const valStr = rawValue !== undefined && rawValue !== null ? String(rawValue) : '';

          return (
            <Box key={field.key} flexDirection="row" alignItems="center" marginY={0}>
              <Box width={3}>
                <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.dim}>
                  {isSelected ? '▸ ' : '  '}
                </Text>
              </Box>
              <Box width={22}>
                <Text color={isSelected ? theme.colors.text.bright : theme.colors.text.muted} bold={isSelected}>
                  {field.label}:
                </Text>
              </Box>

              <Box flexDirection="row" alignItems="center">
                {isSelected && isEditing ? (
                  <TextInput
                    value={valStr}
                    onChange={(v: string) => setFormState((prev) => ({ ...prev, [field.key]: v }))}
                    onSubmit={() => setIsEditing(false)}
                    placeholder={field.placeholder}
                  />
                ) : (
                  <Text
                    color={valStr ? theme.colors.text.ethereal : theme.colors.text.dim}
                    bold={isSelected && isEditing}
                  >
                    {field.type === 'password' && valStr
                      ? '•'.repeat(Math.min(16, valStr.length))
                      : valStr || field.placeholder || '(Empty)'}
                  </Text>
                )}
              </Box>
            </Box>
          );
        })}
      </Box>

      {/* Interactive Scrollable Model Catalog Section */}
      <Box flexDirection="column" marginTop={0}>
        <Box flexDirection="row" justifyContent="space-between" alignItems="center" marginBottom={0}>
          <Text color={theme.colors.text.warning} bold underline>
            [2] Model Catalog ({modelsLabel})
          </Text>

          <Text color={theme.colors.text.muted}>
            Selected:{' '}
            <Text color={theme.colors.status.success} bold>
              {formState.model || selectedCatalogModel?.id}
            </Text>
          </Text>
        </Box>

        {startIndex > 0 && (
          <Text color={theme.colors.text.dim} italic>
            ▲ {startIndex} more model(s) above...
          </Text>
        )}

        {visibleModels.map((m, idx) => {
          const actualIdx = startIndex + idx;
          const isCursor = activeSection === 'models' && actualIdx === catalogCursor;
          const isCurrentlyActive = m.id === formState.model;

          return (
            <Box key={m.id} flexDirection="row" alignItems="center" width="100%">
              <Box width={3}>
                <Text color={isCursor ? theme.colors.text.emerald : theme.colors.text.dim}>
                  {isCursor ? '▸ ' : '  '}
                </Text>
              </Box>

              <Box width={3}>
                <Text color={isCurrentlyActive ? theme.colors.status.success : theme.colors.text.muted} bold>
                  {isCurrentlyActive ? '✓ ' : '○ '}
                </Text>
              </Box>

              <Box width={28} flexShrink={0}>
                <Text color={isCursor ? theme.colors.text.bright : theme.colors.text.muted} bold={isCursor}>
                  {m.name}
                </Text>
              </Box>

              <Box width={32} flexShrink={0}>
                <Text color={theme.colors.text.ethereal} italic>
                  {m.id}
                </Text>
              </Box>

              <Box flexShrink={0}>
                <Text color={theme.colors.text.dim}>({(m.contextWindow / 1000).toFixed(0)}k context)</Text>
              </Box>
            </Box>
          );
        })}

        {startIndex + VISIBLE_COUNT < catalogModels.length && (
          <Text color={theme.colors.text.dim} italic>
            ▼ {catalogModels.length - (startIndex + VISIBLE_COUNT)} more model(s) below...
          </Text>
        )}
      </Box>

      {/* Footer Navigation Bar */}
      <Box marginTop={1} paddingTop={1} borderStyle="single" borderTop={true} borderColor={theme.colors.border.muted}>
        {saveMessage ? (
          <Text color={theme.colors.status.success} bold>
            {saveMessage}
          </Text>
        ) : (
          <Text color={theme.colors.text.muted}>
            <Text color={theme.colors.text.emerald}>[Tab]</Text> Switch Section ·{' '}
            <Text color={theme.colors.text.emerald}>[↑/↓]</Text> Scroll Models / Fields ·{' '}
            <Text color={theme.colors.text.emerald}>[Enter/Space]</Text> Select Model / Edit ·{' '}
            <Text color={theme.colors.text.emerald}>[Ctrl+S]</Text> Save
          </Text>
        )}
      </Box>
    </Box>
  );
};
