import { Box, Text, useInput } from 'ink';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fuzzyScore, useTextBuffer } from '../../components/ui/textBuffer';
import type { SessionSummary } from '../../services/transport/WebSocketClient';
import { wsClient } from '../../services/transport/WebSocketClient';
import { useTheme } from '../../theme/ThemeContext';

interface SessionBrowserModalProps {
  onClose: () => void;
  onResume: (sessionId: string, summary: SessionSummary, messages?: Record<string, unknown>[]) => void;
}

function formatSessionTime(isoStr: string): string {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
    const date = d.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' });
    return `${time} · ${date}`;
  } catch {
    return isoStr;
  }
}

function formatTokens(n: number): string {
  if (n === 0) return '';
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k tokens`;
  return `${n} tokens`;
}

function deriveTitle(summary: SessionSummary): string {
  const raw = summary.title?.trim();
  if (raw && raw.toLowerCase() !== 'untitled') return raw;
  return 'Untitled Session';
}

function computeVisibleCount(): number {
  return Math.max(3, (process.stdout.rows ?? 24) - 12);
}

export const SessionBrowserModal: React.FC<SessionBrowserModalProps> = ({ onClose, onResume }) => {
  const { theme } = useTheme();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(0);
  const [resuming, setResuming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const filter = useTextBuffer('');
  const [visibleCount, setVisibleCount] = useState(computeVisibleCount);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Resize handler
  useEffect(() => {
    const onResize = () => setVisibleCount(computeVisibleCount());
    process.stdout.on('resize', onResize);
    return () => {
      process.stdout.off('resize', onResize);
    };
  }, []);

  // Fetch sessions on mount
  useEffect(() => {
    setLoading(true);
    wsClient
      .listAllSessions({ limit: 5, include_archived: false })
      .then((list) => {
        if (!mounted.current) return;
        // Sort by updated_at descending (most recent first)
        const sorted = [...list].sort((a, b) => {
          const ta = new Date(a.updated_at || a.created_at || '').getTime();
          const tb = new Date(b.updated_at || b.created_at || '').getTime();
          return tb - ta;
        });
        setSessions(sorted);
        setLoading(false);
      })
      .catch(() => {
        if (!mounted.current) return;
        setError('Failed to load sessions.');
        setLoading(false);
      });
  }, []);

  const filtered = useMemo(() => {
    const needle = filter.value.trim().toLowerCase();
    if (!needle) return sessions;
    return sessions
      .map((s) => ({
        s,
        score: fuzzyScore(needle, deriveTitle(s), s.mode),
      }))
      .filter((item): item is { s: SessionSummary; score: number } => item.score !== null)
      .sort((a, b) => b.score - a.score)
      .map((item) => item.s);
  }, [sessions, filter.value]);

  const clampSelected = useCallback(
    (idx: number) => Math.max(0, Math.min(idx, Math.max(0, filtered.length - 1))),
    [filtered.length],
  );

  const visibleWindow = useMemo(() => {
    const count = Math.min(visibleCount, filtered.length);
    if (filtered.length === 0) return { start: 0, end: 0 };
    const start = Math.max(0, Math.min(selected - Math.floor(count / 2), filtered.length - count));
    return { start, end: start + count };
  }, [filtered.length, selected, visibleCount]);

  const handleResume = useCallback(
    async (s: SessionSummary) => {
      if (resuming) return;
      setResuming(true);
      try {
        const result = await wsClient.resumeSession(s.id);
        onResume(s.id, s, result.messages);
      } catch (err) {
        if (mounted.current) {
          setResuming(false);
          setError('Failed to resume session.');
        }
      }
    },
    [onResume, resuming],
  );

  useInput((char, key) => {
    if (resuming) return;

    if (key.escape) {
      onClose();
      return;
    }
    if (key.upArrow) {
      setSelected((s) => clampSelected(s - 1));
      return;
    }
    if (key.downArrow) {
      setSelected((s) => clampSelected(s + 1));
      return;
    }
    if (key.pageUp) {
      setSelected((s) => clampSelected(s - 10));
      return;
    }
    if (key.pageDown) {
      setSelected((s) => clampSelected(s + 10));
      return;
    }
    if (key.return) {
      const s = filtered[selected];
      if (s) handleResume(s);
      return;
    }
    // Text input for search
    if (key.leftArrow || key.rightArrow || key.delete || key.backspace || char) {
      filter.handleKey(char, key);
      setSelected(0);
    }
  });

  const renderRow = (s: SessionSummary, idx: number) => {
    const isSelected = idx === selected;
    const title = deriveTitle(s);
    const timeStr = formatSessionTime(s.updated_at || s.created_at || '');
    const tokStr = formatTokens(s.total_tokens);
    const modeLabel = s.mode ? s.mode.toUpperCase() : '';

    return (
      <Box key={s.id} flexDirection="row" alignItems="center" paddingLeft={2} paddingRight={1}>
        <Box width={2} flexShrink={0}>
          <Text color={theme.colors.status.accent}>{isSelected ? '▸' : ' '}</Text>
        </Box>

        <Text color={theme.colors.text.dim}>{timeStr}</Text>

        {modeLabel ? (
          <Text color={isSelected ? theme.colors.status.info : theme.colors.text.dim}>
            {'  '}
            {modeLabel}
            {'  '}
          </Text>
        ) : (
          <Text>{'  '}</Text>
        )}

        <Text
          color={isSelected ? theme.colors.text.bright : theme.colors.text.ethereal}
          bold={isSelected}
          wrap="truncate-end"
        >
          {title}
        </Text>

        {tokStr ? (
          <Text color={isSelected ? theme.colors.status.warning : theme.colors.text.dim}>
            {'  '}
            {tokStr}
          </Text>
        ) : null}
      </Box>
    );
  };

  const visibleRows = filtered.slice(visibleWindow.start, visibleWindow.end);

  return (
    <Box flexDirection="column" width="100%">
      <Box flexDirection="row" justifyContent="space-between" paddingLeft={2} paddingRight={2}>
        <Text color={theme.colors.text.ethereal} bold>
          Sessions
        </Text>
        <Text color={theme.colors.text.muted}>esc to close</Text>
      </Box>

      <Box paddingLeft={2} paddingRight={2} marginTop={1}>
        <Text color={theme.colors.text.muted}>▸ </Text>
        <Text color={theme.colors.text.ethereal}>
          {filter.value.slice(0, filter.cursor)}
          <Text color={theme.colors.status.accent} inverse>
            {filter.value[filter.cursor] ?? ' '}
          </Text>
          {filter.value.slice(filter.cursor + 1)}
        </Text>
        <Text color={theme.colors.text.dim}>{filter.value ? '' : ' Search sessions'}</Text>
      </Box>

      <Box paddingLeft={2} paddingRight={2} marginTop={1}>
        <Text color={theme.colors.border.muted}>{'─'.repeat(Math.min(process.stdout.columns ?? 80, 76))}</Text>
      </Box>

      <Box flexDirection="column" marginTop={0} minHeight={3}>
        {loading && (
          <Box paddingLeft={4}>
            <Text color={theme.colors.text.muted}>Loading sessions…</Text>
          </Box>
        )}
        {!loading && error && (
          <Box paddingLeft={4}>
            <Text color={theme.colors.status.error}>{error}</Text>
          </Box>
        )}
        {!loading && !error && filtered.length === 0 && (
          <Box paddingLeft={4} flexDirection="column">
            <Text color={theme.colors.text.muted}>No previous sessions found.</Text>
            <Box marginTop={1}>
              <Text color={theme.colors.text.dim}>Start a new conversation to begin.</Text>
            </Box>
          </Box>
        )}
        {!loading && !error && visibleRows.map((s, i) => renderRow(s, visibleWindow.start + i))}
        {resuming && (
          <Box paddingLeft={4} marginTop={1}>
            <Text color={theme.colors.status.info}>Resuming session…</Text>
          </Box>
        )}
      </Box>

      {filtered.length > 0 && (
        <Box paddingLeft={2} paddingRight={2} marginTop={1}>
          <Text color={theme.colors.text.dim}>
            ↑↓ navigate · ⏎ open · type to search · {filtered.length} session{filtered.length !== 1 ? 's' : ''}
            {filtered.length < sessions.length ? ` (${sessions.length} total)` : ''}
          </Text>
        </Box>
      )}
    </Box>
  );
};
