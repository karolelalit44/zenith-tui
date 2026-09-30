import { Box, Text } from 'ink';
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { SearchList, type SearchListAction, type SearchListOption } from '../components/ui/SearchList';
import { wsClient } from '../services/transport/WebSocketClient';
import { useTheme } from '../theme/ThemeContext';

interface ChangeRow {
  seq: number;
  tool: string;
  path: string;
  action: 'create' | 'modify' | 'delete';
  bytesBefore: number;
  bytesAfter: number;
  revertible: boolean;
  contentOmitted: boolean;
  directory: boolean;
}

const ACTION_GLYPH: Record<ChangeRow['action'], string> = {
  create: '+',
  modify: '~',
  delete: '-',
};

function workspaceRelative(path: string): string {
  const normalized = path.replace(/\\/g, '/');
  return normalized;
}

interface ChangesOverlayProps {
  onClose: () => void;
}

/**
 * Lists the file mutations this session made and offers to undo them.
 *
 * There was previously no way to see or reverse an agent's file changes other
 * than a shell `git checkout`, which is both slower and wrong for files that
 * were never committed. The server keeps an in-memory journal of every
 * mutation with its pre-image, so undoing a change here is exact rather than
 * inferred.
 */
export const ChangesOverlay: React.FC<ChangesOverlayProps> = ({ onClose }) => {
  const { theme } = useTheme();
  const [rows, setRows] = useState<ChangeRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    wsClient
      .send<{ changes: ChangeRow[]; count: number }>('workspace.changes', { limit: 100 })
      .then((result: { changes: ChangeRow[]; count: number } | null) => {
        if (!cancelled) setRows(result?.changes ?? []);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const options = useMemo<SearchListOption<ChangeRow>[]>(
    () =>
      (rows ?? []).map((row) => ({
        title: `${ACTION_GLYPH[row.action] ?? '?'} ${workspaceRelative(row.path)}`,
        value: row,
        category: row.tool,
        description: row.directory
          ? 'directory (contents were not retained, so this cannot be restored)'
          : row.contentOmitted
            ? `too large to retain — ${row.bytesBefore} -> ${row.bytesAfter} bytes`
            : `${row.bytesBefore} -> ${row.bytesAfter} bytes`,
        disabled: !row.revertible,
      })),
    [rows],
  );

  const revertTo = useCallback(async (since: number) => {
    setBusy(true);
    setStatus('Reverting…');
    try {
      const result = await wsClient.send<{
        restored: number;
        failed: string[];
        complete: boolean;
        warning?: string;
      }>('workspace.revert', { since });
      if (result?.complete) {
        setStatus(`Reverted ${result.restored} change(s).`);
        setRows([]);
      } else {
        setStatus(result?.warning ?? `Reverted ${result?.restored ?? 0} change(s), with failures.`);
        setRows([]);
      }
    } catch (e: unknown) {
      setStatus(e instanceof Error ? `Revert failed: ${e.message}` : 'Revert failed');
    } finally {
      setBusy(false);
    }
  }, []);

  const actions = useMemo<SearchListAction<ChangeRow>[]>(
    () => [
      {
        label: 'Revert this and everything after it',
        onTrigger: (option: SearchListOption<ChangeRow>) => {
          // Entries are returned newest-first, so reverting "everything after"
          // a given entry means reverting from the sequence *below* it.
          const idx = options.findIndex((o) => o.value.seq === option.value.seq);
          const older = idx >= 0 && idx + 1 < options.length ? options[idx + 1].value.seq : 0;
          void revertTo(older);
        },
      },
      {
        label: 'Revert everything in this session',
        onTrigger: () => void revertTo(0),
      },
    ],
    [options, revertTo],
  );

  if (error) {
    return (
      <Box flexDirection="column" width="100%">
        <Text color={theme.colors.status.error}>Could not load changes: {error}</Text>
        <Text color={theme.colors.text.dim}>Press Esc to close.</Text>
      </Box>
    );
  }

  if (rows === null) {
    return (
      <Box flexDirection="column" width="100%">
        <Text color={theme.colors.text.muted}>Loading changes…</Text>
      </Box>
    );
  }

  if (options.length === 0) {
    return (
      <Box flexDirection="column" width="100%">
        <Text color={theme.colors.text.muted}>This session has not changed any files yet.</Text>
        <Text color={theme.colors.text.dim}>Press Esc to close.</Text>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" width="100%">
      <SearchList<ChangeRow>
        title="Session changes"
        options={options}
        actions={actions}
        onSelect={(option: SearchListOption<ChangeRow>) => {
          const idx = options.findIndex((o) => o.value.seq === option.value.seq);
          const older = idx >= 0 && idx + 1 < options.length ? options[idx + 1].value.seq : 0;
          void revertTo(older);
        }}
        onClose={onClose}
        filterPlaceholder="Filter by path"
        placeholder="Changes"
      />
      <Box width="100%" paddingX={1}>
        <Text color={theme.colors.text.dim} wrap="truncate-end">
          {status ??
            (busy ? 'Working…' : 'Tab cycles actions · Enter reverts the selected change and everything after it')}
        </Text>
      </Box>
    </Box>
  );
};

ChangesOverlay.displayName = 'ChangesOverlay';
