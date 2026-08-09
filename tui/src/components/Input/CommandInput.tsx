import { Box, type Key, Text } from 'ink';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { SESSION_STATUS_DEFAULTS } from '../../constants/statusDefaults';
import { useProvider } from '../../hooks/useProvider';
import { getActiveGitBranch } from '../../services/git';
import { useTheme } from '../../theme/ThemeContext';
import type { ScenarioMode } from '../../types';
import type { FileAttachment } from '../../types/scenario';
import { AttachmentChips } from './AttachmentChips';
import { ComposerFooter } from './ComposerFooter';
import { MultiLineTextInput } from './MultiLineTextInput';

const PLACEHOLDERS = ['Ask anything…', 'Describe the change…', '@ file · / cmd · ? help'];
const PLACEHOLDER_INTERVAL_MS = 4000;

interface CommandInputProps {
  input: string;
  onInputChange: (value: string) => void;
  onSubmit: (value: string) => void;
  disabled?: boolean;
  disabledMessage?: string;
  running?: boolean;
  attachments?: FileAttachment[];
  onRemoveAttachment?: (index: number) => void;
  historyUp?: () => string | undefined;
  historyDown?: () => string | undefined;
  mode?: ScenarioMode;
  totalTokens?: number;
  maxTokens?: number;
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
    totalTokens = 0,
    maxTokens = SESSION_STATUS_DEFAULTS.maxTokens,
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
    const [placeholderIndex, setPlaceholderIndex] = useState(0);

    useEffect(() => {
      const timer = setInterval(
        () => setPlaceholderIndex((i) => (i + 1) % PLACEHOLDERS.length),
        PLACEHOLDER_INTERVAL_MS,
      );
      return () => clearInterval(timer);
    }, []);

    const activeBranch = gitBranch || getActiveGitBranch();
    const providerName = activeProvider.meta.name || 'Unknown';
    const modelFallback = activeProvider.config.model || activeProvider.meta.defaultModel || 'unknown';

    const columns = process.stdout.columns ?? 80;
    const shortDir = useMemo(() => {
      const parts = workspaceName.replace(/\\/g, '/').split('/');
      return parts.length > 2 ? `.../${parts.slice(-2).join('/')}` : workspaceName;
    }, [workspaceName]);
    const dividerWidth = Math.max(0, columns - 6);

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
        if (key.escape && running && onCancel) {
          onCancel();
          return true;
        }
        return false;
      },
      [slashMenuOpen, onOpenHelp, onOpenMode, onInputChange, onClearInput, onCancel, running],
    );

    const focused = !disabled;

    return (
      <Box flexDirection="column" width="100%" marginTop={1}>
        <AttachmentChips attachments={attachments} onRemove={onRemoveAttachment} />

        <Box
          flexDirection="column"
          width="100%"
          borderStyle="round"
          borderColor={focused ? theme.colors.border.active : theme.colors.border.muted}
          paddingX={1}
          paddingY={0}
        >
          <Box flexDirection="row" width="100%" alignItems="flex-start">
            <Text color={focused ? theme.colors.text.emerald : theme.colors.text.muted} bold={focused}>
              {focused ? '❯' : '◌'}{' '}
            </Text>
            <Box flexDirection="column" flexGrow={1}>
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
                  onSubmit={onSubmit}
                  placeholder={PLACEHOLDERS[placeholderIndex]}
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
            dir={shortDir}
            branch={activeBranch}
            totalTokens={totalTokens}
            effectiveMaxTokens={effectiveMaxTokens}
            running={running}
            disabled={disabled}
            inputEmpty={!input.trim()}
            tokenScope={running ? 'turn' : 'session'}
          />
        </Box>
      </Box>
    );
  },
);

CommandInput.displayName = 'CommandInput';
