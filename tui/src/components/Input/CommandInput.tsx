import { Box, type Key, Text } from 'ink';
import React, { useCallback } from 'react';
import { SESSION_STATUS_DEFAULTS } from '../../constants/statusDefaults';
import { useProvider } from '../../hooks/useProvider';
import { useTerminalDimensions } from '../../hooks/useTerminalDimensions';
import { getActiveGitBranch } from '../../services/git';
import { useTheme } from '../../theme/ThemeContext';
import type { ScenarioMode } from '../../types';
import type { FileAttachment } from '../../types/scenario';
import { expandPastedMarkers } from '../../utils/pasteTracker';
import { formatBytes } from '../../utils/text';
import { ComposerFooter } from './ComposerFooter';
import { MultiLineTextInput } from './MultiLineTextInput';

const STATIC_PLACEHOLDER = 'Ask anything...';

interface CommandInputProps {
  input: string;
  onInputChange: (value: string, cursor?: number) => void;
  onSubmit: (value: string) => void;
  disabled?: boolean;
  disabledMessage?: string;
  running?: boolean;
  attachments?: FileAttachment[];
  onRemoveAttachment?: (index: number) => void;
  historyUp?: () => string | undefined;
  historyDown?: () => string | undefined;
  mode?: ScenarioMode;
  maxTokens?: number;
  /** Cumulative run/API token usage (telemetry). */
  runTokens?: number;
  /** True when cumulative run usage is estimated, not provider-reported. */
  runEstimated?: boolean;
  /** Composed-context occupancy percent (0–100). */
  contextPercent?: number;
  /** True when the context window is a fallback estimate. */
  windowEstimated?: boolean;
  workspaceName?: string;
  gitBranch?: string;
  onCancel?: () => void;
  onOpenHelp?: () => void;
  onOpenMode?: () => void;
  onClearInput?: () => void;

  slashMenuOpen?: boolean;
}

export const CommandInput: React.FC<CommandInputProps> = React.memo(
  ({
    input,
    onInputChange,
    onSubmit,
    disabled = false,
    disabledMessage = 'Input disabled',
    running = false,
    attachments = [],
    onRemoveAttachment,
    historyUp,
    historyDown,
    mode = 'build',
    maxTokens = SESSION_STATUS_DEFAULTS.maxTokens,
    runTokens,
    runEstimated,
    contextPercent,
    windowEstimated,
    workspaceName = SESSION_STATUS_DEFAULTS.workspaceName,
    gitBranch,
    onCancel,
    onOpenHelp,
    onOpenMode,
    onClearInput,
    slashMenuOpen = false,
  }) => {
    const { theme } = useTheme();
    const { activeProvider } = useProvider();

    const activeBranch = gitBranch || getActiveGitBranch();
    const providerName = activeProvider.meta.name || 'Unknown';
    const modelFallback = activeProvider.config.model || activeProvider.meta.defaultModel || 'unknown';

    const { columns } = useTerminalDimensions();
    const termCols = columns || process.stdout.columns || 80;
    const dividerWidth = Math.max(0, termCols - 6);

    const activeModelId = activeProvider.config.model || activeProvider.meta.defaultModel;
    const activeModelInfo = activeProvider.meta.availableModels?.find((m) => m.id === activeModelId);
    const modelContextWindow = activeModelInfo?.context_window ?? SESSION_STATUS_DEFAULTS.maxTokens;
    const backendMaxTokens = maxTokens > 0 ? maxTokens : SESSION_STATUS_DEFAULTS.maxTokens;
    const effectiveMaxTokens = Math.min(modelContextWindow, backendMaxTokens);

    const handleSpecial = useCallback(
      (char: string, key: Key, value: string): boolean => {
        if (slashMenuOpen) {
          const isEnter = key.return || char === '\n' || char === '\r';

          if (key.upArrow || key.downArrow || isEnter || key.tab || key.escape) return true;
          return false;
        }
        if (!value.trim() && char === '?' && onOpenHelp) {
          onOpenHelp();
          return true;
        }
        if (!value.trim() && key.shift && (char === 'm' || char === 'M') && onOpenMode) {
          onOpenMode();
          return true;
        }
        if (key.ctrl && !running && (char === 'c' || char === 'C' || char === '\x03')) {
          if (value) {
            onInputChange('');
          } else if (onClearInput) {
            onClearInput();
          }
          return true;
        }
        const isEscape = Boolean(key.escape || char === '\x1b' || char === '\x1B');
        if (isEscape && running && onCancel) {
          onCancel();
          return true;
        }
        if (isEscape && !running && value.length > 0) {
          onInputChange('', 0);
          if (onClearInput) {
            onClearInput();
          }
          return true;
        }
        if (isEscape && !running && value.length === 0 && attachments.length > 0 && onRemoveAttachment) {
          onRemoveAttachment(attachments.length - 1);
          return true;
        }
        if (
          (key.backspace || key.delete) &&
          !running &&
          value.length === 0 &&
          attachments.length > 0 &&
          onRemoveAttachment
        ) {
          onRemoveAttachment(attachments.length - 1);
          return true;
        }
        return false;
      },
      [
        slashMenuOpen,
        onOpenHelp,
        onOpenMode,
        onInputChange,
        onClearInput,
        onCancel,
        running,
        attachments,
        onRemoveAttachment,
      ],
    );

    const handleSubmit = useCallback(
      (val: string) => {
        const fullText = expandPastedMarkers(val);
        onSubmit(fullText);
      },
      [onSubmit],
    );

    const focused = !disabled;

    return (
      <Box flexDirection="column" width="100%" marginTop={1}>
        <Box
          flexDirection="column"
          width="100%"
          borderStyle="round"
          borderColor={focused ? theme.colors.border.active : theme.colors.border.muted}
          paddingX={1}
          paddingY={0}
        >
          {/* Attachment Dock */}
          {attachments.length > 0 && (
            <Box flexDirection="row" flexWrap="wrap" marginBottom={1} alignItems="center">
              {attachments.map((att, idx) => {
                const isFolder = att.kind === 'folder' || att.mimeType === 'inode/directory';
                const sizeText = att.size > 0 ? formatBytes(att.size) : '';
                return (
                  <Box
                    key={`${att.path}-${idx}`}
                    flexDirection="row"
                    alignItems="center"
                    marginRight={1}
                    paddingX={1}
                    borderStyle="single"
                    borderColor={theme.colors.border.muted}
                  >
                    <Text color={isFolder ? theme.colors.status.info : theme.colors.text.muted}>
                      {isFolder ? '📁 ' : '📄 '}
                    </Text>
                    <Text italic color={theme.colors.status.accent}>
                      {att.name || att.path}
                    </Text>
                    {sizeText ? (
                      <Box marginLeft={1}>
                        <Text color={theme.colors.text.dim}>{sizeText}</Text>
                      </Box>
                    ) : null}
                    {onRemoveAttachment && (
                      <Box marginLeft={1}>
                        <Text color={theme.colors.status.error}>×</Text>
                      </Box>
                    )}
                  </Box>
                );
              })}
            </Box>
          )}

          <Box flexDirection="row" width="100%" alignItems="flex-start">
            <Box flexShrink={0}>
              <Text color={focused ? theme.colors.text.emerald : theme.colors.text.muted} bold={focused}>
                {focused ? '❯' : '◌'}{' '}
              </Text>
            </Box>
            <Box flexDirection="column" flexGrow={1} flexShrink={1}>
              {disabled ? (
                <Box flexDirection="row" alignItems="center" minHeight={1}>
                  <Text color={theme.colors.text.muted} italic>
                    {disabledMessage}
                  </Text>
                </Box>
              ) : (
                <MultiLineTextInput
                  value={input}
                  onChange={onInputChange}
                  onSubmit={handleSubmit}
                  placeholder={STATIC_PLACEHOLDER}
                  focus={focused}
                  historyUp={historyUp}
                  historyDown={historyDown}
                  onSpecial={handleSpecial}
                />
              )}
            </Box>
          </Box>

          <Box width="100%" marginY={0}>
            <Text color={theme.colors.border.muted} wrap="truncate-end">
              {'─'.repeat(dividerWidth)}
            </Text>
          </Box>

          <ComposerFooter
            mode={mode}
            modelFallback={modelFallback}
            providerName={providerName}
            dir={workspaceName}
            branch={activeBranch}
            effectiveMaxTokens={effectiveMaxTokens}
            runTokens={runTokens}
            runEstimated={runEstimated}
            contextPercent={contextPercent}
            windowEstimated={windowEstimated}
          />
        </Box>
      </Box>
    );
  },
);

CommandInput.displayName = 'CommandInput';
