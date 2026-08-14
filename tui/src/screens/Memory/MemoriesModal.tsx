import { Box, Text, useInput } from 'ink';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTextBuffer } from '../../components/ui/textBuffer';
import type { MemoryEntry, MemoryScope } from '../../services/transport/WebSocketClient';
import { wsClient } from '../../services/transport/WebSocketClient';
import { useTheme } from '../../theme/ThemeContext';

interface MemoriesModalProps {
  onClose: () => void;
}

export type MemoryScopeFilter = MemoryScope | 'all';

const UNTITLED = 'Untitled memory';

export function deriveMemoryTitle(m: MemoryEntry): string {
  const raw = m.title?.trim();
  if (raw) return raw;
  return UNTITLED;
}

export function memoryPreview(m: MemoryEntry, maxChars = 140): string {
  const text = (m.content || '').replace(/\s+/g, ' ').trim();
  if (text.length <= maxChars) return text;
  return `${text.slice(0, maxChars - 1).trimEnd()}…`;
}

export function formatMemoryTime(iso?: string): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' });
  } catch {
    return '';
  }
}

export function filterMemories(memories: MemoryEntry[], scope: MemoryScopeFilter, query: string): MemoryEntry[] {
  const needle = query.trim().toLowerCase();
  let scoped = scope === 'all' ? memories : memories.filter((m) => m.scope === scope);
  if (needle) {
    scoped = scoped.filter((m) => {
      const haystack = [m.title, m.content, m.source, ...(m.tags ?? [])].filter(Boolean).join(' ').toLowerCase();
      return haystack.includes(needle);
    });
  }
  return [...scoped].sort((a, b) => {
    const ap = a.pinned ? 1 : 0;
    const bp = b.pinned ? 1 : 0;
    if (ap !== bp) return bp - ap;
    const ta = new Date(a.updated_at || a.created_at || '').getTime();
    const tb = new Date(b.updated_at || b.created_at || '').getTime();
    const av = Number.isNaN(ta) ? -Infinity : ta;
    const bv = Number.isNaN(tb) ? -Infinity : tb;
    return bv - av;
  });
}

function computeVisibleCount(): number {
  return Math.max(3, (process.stdout.rows ?? 24) - 12);
}

export const MemoriesModal: React.FC<MemoriesModalProps> = ({ onClose }) => {
  const { theme } = useTheme();
  const [memories, setMemories] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState(0);
  const [scope, setScope] = useState<MemoryScopeFilter>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(computeVisibleCount);
  const filter = useTextBuffer('');
  const mounted = useRef(true);
  const fetching = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    const onResize = () => setVisibleCount(computeVisibleCount());
    process.stdout.on('resize', onResize);
    return () => {
      process.stdout.off('resize', onResize);
    };
  }, []);

  const load = useCallback(() => {
    if (fetching.current) return;
    fetching.current = true;
    setLoading(true);
    setError(null);
    wsClient
      .listMemories()
      .then((res) => {
        if (!mounted.current) return;
        const list = Array.isArray(res?.memories) ? res.memories : [];
        setMemories(list);
        setSelected(0);
        setExpandedId(null);
        setLoading(false);
      })
      .catch(() => {
        if (!mounted.current) return;
        setError('Failed to load memories.');
        setLoading(false);
      })
      .finally(() => {
        fetching.current = false;
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = useMemo(() => filterMemories(memories, scope, filter.value), [memories, scope, filter.value]);

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

  const cycleScope = useCallback(() => {
    setScope((s) => (s === 'all' ? 'project' : s === 'project' ? 'session' : 'all'));
    setSelected(0);
  }, []);

  useInput((char, key) => {
    if (key.escape) {
      onClose();
      return;
    }
    if (key.tab) {
      cycleScope();
      return;
    }
    if (key.ctrl && char === String.fromCharCode('r'.charCodeAt(0) - 96)) {
      load();
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
    if (key.home) {
      setSelected(0);
      return;
    }
    if (key.end) {
      setSelected(Math.max(0, filtered.length - 1));
      return;
    }
    if (key.return) {
      if (error) {
        load();
        return;
      }
      const m = filtered[selected];
      if (m) setExpandedId((id) => (id === m.id ? null : m.id));
      return;
    }
    if (key.leftArrow || key.rightArrow || key.delete || key.backspace || char) {
      filter.handleKey(char, key);
      setSelected(0);
    }
  });

  const renderMeta = (m: MemoryEntry): string => {
    const parts: string[] = [];
    if (m.tags && m.tags.length > 0) parts.push(m.tags.map((t) => `#${t}`).join(' '));
    if (typeof m.size_chars === 'number') parts.push(`${m.size_chars} chars`);
    if (typeof m.sessions === 'number' && m.sessions > 1) parts.push(`${m.sessions} sessions`);
    return parts.join(' · ');
  };

  const renderRow = (m: MemoryEntry, idx: number) => {
    const isSelected = idx === selected;
    const isExpanded = expandedId === m.id;
    const title = deriveMemoryTitle(m);
    const timeStr = formatMemoryTime(m.updated_at || m.created_at);
    const scopeLabel = m.scope === 'project' ? 'PROJECT' : 'SESSION';
    const meta = renderMeta(m);

    return (
      <Box key={m.id} flexDirection="column" paddingLeft={2} paddingRight={1}>
        <Box flexDirection="row" alignItems="center">
          <Box width={2} flexShrink={0}>
            <Text color={theme.colors.status.accent}>{isSelected ? '▸' : ' '}</Text>
          </Box>
          <Text color={theme.colors.status.warning}>{m.pinned ? '★' : ' '}</Text>
          <Text color={m.scope === 'project' ? theme.colors.status.info : theme.colors.status.success}>
            {' '}
            {scopeLabel}{' '}
          </Text>
          <Text
            color={isSelected ? theme.colors.text.bright : theme.colors.text.ethereal}
            bold={isSelected}
            wrap="truncate-end"
          >
            {title}
          </Text>
          {timeStr ? (
            <Text color={isSelected ? theme.colors.text.dim : theme.colors.text.muted}>
              {'  '}
              {timeStr}
            </Text>
          ) : null}
        </Box>
        {isSelected && m.content ? (
          <Box paddingLeft={2} flexDirection="column">
            <Text color={theme.colors.text.muted} wrap={isExpanded ? 'wrap' : 'truncate-end'}>
              {isExpanded ? m.content.trim() : memoryPreview(m)}
            </Text>
            {meta ? (
              <Text color={theme.colors.text.dim} wrap="truncate-end">
                {meta}
              </Text>
            ) : null}
          </Box>
        ) : null}
      </Box>
    );
  };

  const visibleRows = filtered.slice(visibleWindow.start, visibleWindow.end);

  return (
    <Box flexDirection="column" width="100%">
      <Box flexDirection="row" justifyContent="space-between" paddingLeft={2} paddingRight={2}>
        <Text color={theme.colors.text.ethereal} bold>
          Memories
        </Text>
        <Text color={theme.colors.text.muted}>esc to close</Text>
      </Box>

      <Box flexDirection="row" paddingLeft={2} paddingRight={2} marginTop={1}>
        <Text color={theme.colors.text.muted}>scope: </Text>
        <Text color={scope === 'all' ? theme.colors.status.accent : theme.colors.text.dim} bold={scope === 'all'}>
          [All]
        </Text>
        <Text color={theme.colors.text.dim}> </Text>
        <Text color={scope === 'project' ? theme.colors.status.info : theme.colors.text.dim} bold={scope === 'project'}>
          [Project]
        </Text>
        <Text color={theme.colors.text.dim}> </Text>
        <Text
          color={scope === 'session' ? theme.colors.status.success : theme.colors.text.dim}
          bold={scope === 'session'}
        >
          [Session]
        </Text>
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
        <Text color={theme.colors.text.dim}>{filter.value ? '' : ' Search memories'}</Text>
      </Box>

      <Box paddingLeft={2} paddingRight={2} marginTop={1}>
        <Text color={theme.colors.border.muted}>{'─'.repeat(Math.min(process.stdout.columns ?? 80, 76))}</Text>
      </Box>

      <Box flexDirection="column" marginTop={0} minHeight={3}>
        {loading && (
          <Box paddingLeft={4}>
            <Text color={theme.colors.text.muted}>Loading memories…</Text>
          </Box>
        )}
        {!loading && error && (
          <Box paddingLeft={4} flexDirection="column">
            <Text color={theme.colors.status.error}>{error}</Text>
            <Box marginTop={1}>
              <Text color={theme.colors.text.dim}>Press Enter to retry · esc to close</Text>
            </Box>
          </Box>
        )}
        {!loading && !error && memories.length === 0 && (
          <Box paddingLeft={4} flexDirection="column">
            <Text color={theme.colors.text.muted}>No memories found yet.</Text>
            <Box marginTop={1}>
              <Text color={theme.colors.text.dim}>
                Memory is written as you work — nothing durable to show right now.
              </Text>
            </Box>
          </Box>
        )}
        {!loading && !error && memories.length > 0 && filtered.length === 0 && (
          <Box paddingLeft={4} flexDirection="column">
            <Text color={theme.colors.text.muted}>No memories match the current filters.</Text>
            <Box marginTop={1}>
              <Text color={theme.colors.text.dim}>Clear the search or press Tab to change scope.</Text>
            </Box>
          </Box>
        )}
        {!loading && !error && visibleRows.map((m, i) => renderRow(m, visibleWindow.start + i))}
      </Box>

      {memories.length > 0 && (
        <Box paddingLeft={2} paddingRight={2} marginTop={1}>
          <Text color={theme.colors.text.dim}>
            ↑↓ navigate · ⏎ expand · type to search · Tab scope · ^R refresh · {filtered.length} of {memories.length}{' '}
            memories
          </Text>
        </Box>
      )}
    </Box>
  );
};
