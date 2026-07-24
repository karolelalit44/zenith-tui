import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import { wsClient } from '../../../services/backend/WebSocketClient';
import { useTheme } from '../../../theme/ThemeContext';
import type { PermissionRequestEvent } from '../../../types/scenario';
import type { EventComponentProps } from './componentRegistry';

interface PermissionDialogState {
  approved: boolean | null;
  remember: boolean;
}

const TOOL_ICONS: Record<string, string> = {
  file_write: '[W]',
  file_edit: '[E]',
  file_delete: '[D]',
  bash: '[>]',
};

function getToolDescription(tool: string, params: Record<string, unknown>): string {
  switch (tool) {
    case 'file_write':
      return `Write to file: ${String(params.filepath || params.path || 'unknown')}`;
    case 'file_edit':
      return `Edit file: ${String(params.filepath || params.path || 'unknown')}`;
    case 'file_delete':
      return `Delete file: ${String(params.path || 'unknown')}`;
    case 'bash':
      return `Execute command: ${String(params.command || 'unknown').slice(0, 80)}`;
    default:
      return `Execute tool: ${tool}`;
  }
}

function getToolRiskLevel(tool: string): { label: string; color: string } {
  switch (tool) {
    case 'file_delete':
      return { label: 'DESTRUCTIVE', color: 'error' };
    case 'bash':
      return { label: 'HIGH RISK', color: 'warning' };
    case 'file_write':
    case 'file_edit':
      return { label: 'MODIFIES FILES', color: 'info' };
    default:
      return { label: 'REQUIRES APPROVAL', color: 'warning' };
  }
}

export const PermissionDialog: React.FC<EventComponentProps<PermissionRequestEvent>> = React.memo(({ event }) => {
  const { theme } = useTheme();
  const [state, setState] = useState<PermissionDialogState>({
    approved: null,
    remember: false,
  });
  const [cursor, setCursor] = useState<'allow' | 'deny' | 'allow_always'>('allow');

  const sendResponse = (approved: boolean, remember: boolean) => {
    try {
      wsClient
        .send('permission.respond', {
          tool: event.tool,
          approved,
          remember,
          requestId: event.requestId,
        })
        .catch(() => {
          // Connection may have dropped — ignore silently
        });
    } catch {
      // Ignore send errors
    }
    setState({ approved, remember });
  };

  useInput((input, key) => {
    if (state.approved !== null) return;

    if (key.escape) {
      sendResponse(false, false);
    } else if (key.upArrow || input === 'k') {
      setCursor((prev) => {
        if (prev === 'deny') return 'allow';
        if (prev === 'allow_always') return 'deny';
        return prev;
      });
    } else if (key.downArrow || input === 'j') {
      setCursor((prev) => {
        if (prev === 'allow') return 'deny';
        if (prev === 'deny') return 'allow_always';
        return prev;
      });
    } else if (key.return) {
      if (cursor === 'allow') {
        sendResponse(true, false);
      } else if (cursor === 'deny') {
        sendResponse(false, false);
      } else if (cursor === 'allow_always') {
        sendResponse(true, true);
      }
    } else if (input === 'y' || input === 'Y') {
      sendResponse(true, false);
    } else if (input === 'n' || input === 'N') {
      sendResponse(false, false);
    } else if (input === 'a' || input === 'A') {
      sendResponse(true, true);
    }
  });

  if (state.approved !== null) {
    return (
      <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
        <Box flexDirection="row" alignItems="center">
          <Text color={state.approved ? theme.colors.status.success : theme.colors.status.error} bold>
            {state.approved ? '[APPROVED]' : '[DENIED]'}{' '}
          </Text>
          <Text color={theme.colors.text.muted}>{TOOL_ICONS[event.tool] || '[?]'} </Text>
          <Text color={theme.colors.text.bright}>{event.tool}</Text>
          {state.remember && <Text color={theme.colors.status.info}> (saved for future)</Text>}
        </Box>
      </Box>
    );
  }

  const toolDescription = getToolDescription(event.tool, event.params);
  const risk = getToolRiskLevel(event.tool);

  return (
    <Box
      flexDirection="column"
      width="100%"
      marginBottom={1}
      paddingX={1}
      borderStyle="round"
      borderColor={theme.colors.status.warning}
    >
      <Box flexDirection="row" alignItems="center" marginBottom={0}>
        <Text color={theme.colors.status.warning} bold>
          [PERMISSION REQUIRED]
        </Text>
      </Box>

      <Box flexDirection="row" alignItems="center" marginBottom={0} paddingLeft={0}>
        <Text color={theme.colors.text.muted}>{TOOL_ICONS[event.tool] || '[?]'} </Text>
        <Text color={theme.colors.text.bright} bold>
          {event.tool}
        </Text>
        <Text color={theme.colors.text.muted}> </Text>
        <Text color={theme.colors.status[risk.color as keyof typeof theme.colors.status]} bold>
          [{risk.label}]
        </Text>
      </Box>

      <Box flexDirection="column" marginBottom={0} paddingLeft={2}>
        <Text color={theme.colors.text.bright}>{toolDescription}</Text>
      </Box>

      <Box flexDirection="column" paddingLeft={2} marginTop={0}>
        <Box flexDirection="row" alignItems="center">
          <Text color={cursor === 'allow' ? theme.colors.status.success : theme.colors.text.muted}>
            {cursor === 'allow' ? '> ' : '  '}
          </Text>
          <Text color={cursor === 'allow' ? theme.colors.status.success : theme.colors.text.bright}>Allow [y]</Text>
        </Box>

        <Box flexDirection="row" alignItems="center">
          <Text color={cursor === 'deny' ? theme.colors.status.error : theme.colors.text.muted}>
            {cursor === 'deny' ? '> ' : '  '}
          </Text>
          <Text color={cursor === 'deny' ? theme.colors.status.error : theme.colors.text.bright}>Deny [n]</Text>
        </Box>

        <Box flexDirection="row" alignItems="center">
          <Text color={cursor === 'allow_always' ? theme.colors.status.info : theme.colors.text.muted}>
            {cursor === 'allow_always' ? '> ' : '  '}
          </Text>
          <Text color={cursor === 'allow_always' ? theme.colors.status.info : theme.colors.text.bright}>
            Always Allow [a]
          </Text>
        </Box>
      </Box>

      <Box flexDirection="row" marginTop={0}>
        <Text color={theme.colors.text.dim}>ESC to deny</Text>
      </Box>
    </Box>
  );
});
