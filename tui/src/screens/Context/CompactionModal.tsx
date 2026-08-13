import { Box, Text, useInput } from 'ink';
import React, { useMemo } from 'react';
import { ModalFooter } from '../../components/ui/ModalFooter';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { formatTokenCount } from '../../services/api/tokenEstimationService';
import { useTheme } from '../../theme/ThemeContext';
import type { ContextCompactionEndedEvent, ContextCompactionStartedEvent, ScenarioEvent } from '../../types/scenario';
import { consolidateCompactionEvents } from '../../utils/compaction';

interface CompactionModalProps {
  events: ScenarioEvent[];
  totalTokens?: number;
  onCompactNow: () => void;
  onClose: () => void;
}

const PRESERVED_LABELS: [key: string, label: string, key2?: string][] = [
  ['requirements', 'Requirements'],
  ['decisions', 'Decisions'],
  ['openTasks', 'Open tasks'],
  ['findings', 'Important findings'],
  ['artifacts', 'Artifacts'],
  ['agents', 'Active agents'],
];

const COMPRESSED_LABELS: [key: string, label: string][] = [
  ['compressedDiscussions', 'Completed discussion segments'],
  ['redundantExchanges', 'Redundant exchanges'],
  ['obsoleteStates', 'Obsolete intermediate states'],
];

export const CompactionModal: React.FC<CompactionModalProps> = ({ events, totalTokens, onCompactNow, onClose }) => {
  const { theme } = useTheme();

  const snapshot = useMemo(() => {
    const started = events.find((e): e is ContextCompactionStartedEvent => e.kind === 'context_compaction_started');
    const ended = events.find((e): e is ContextCompactionEndedEvent => e.kind === 'context_compaction_ended');
    const flow = consolidateCompactionEvents(events);
    return { started, ended, flow };
  }, [events]);

  const { started, ended, flow } = snapshot;
  const before = started?.used ?? totalTokens;
  const after = ended?.used ?? flow?.afterTokens;
  const saved = ended?.tokensSaved ?? flow?.tokensSaved;
  // Cast for indexed access — ContextPreservation fields are optional, so we
  // only ever read keys that are present at runtime.
  const preserved = (ended?.preserved ?? flow?.preserved) as Record<string, number | undefined> | undefined;
  const failed = ended?.failed ?? flow?.failed;

  useInput((char, key) => {
    if (key.escape) {
      onClose();
    } else if ((key.return || char === '\r') && onCompactNow) {
      onCompactNow();
      onClose();
    }
  });

  const hasAnyPreserved = preserved && PRESERVED_LABELS.some(([k]) => typeof preserved[k] === 'number');
  const hasAnyCompressed = preserved && COMPRESSED_LABELS.some(([k]) => typeof preserved[k] === 'number');

  return (
    <RoundedBox title="CONTEXT COMPACTION" borderColor={theme.colors.border.active} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        {failed ? (
          <Box marginBottom={1}>
            <Text color={theme.colors.status.warning}>Unable to safely compact context. Conversation unchanged.</Text>
          </Box>
        ) : (
          <>
            <Box flexDirection="row" alignItems="center" marginBottom={1}>
              <Text color={theme.colors.text.emerald} bold>
                [BEFORE / AFTER / RECOVERED]
              </Text>
            </Box>

            <Box flexDirection="row" width="100%" marginBottom={1}>
              <Box width={14}>
                <Text color={theme.colors.text.dim}>Before</Text>
              </Box>
              <Text color={theme.colors.text.bright} bold>
                {before !== undefined ? formatTokenCount(before) : '—'}
              </Text>
              <Text color={theme.colors.text.muted}> → </Text>
              <Box width={14}>
                <Text color={theme.colors.text.dim}>After</Text>
              </Box>
              <Text color={theme.colors.text.bright} bold>
                {after !== undefined ? formatTokenCount(after) : '—'}
              </Text>
              <Text color={theme.colors.text.muted}> → </Text>
              <Box width={14}>
                <Text color={theme.colors.text.dim}>Recovered</Text>
              </Box>
              <Text color={theme.colors.status.success} bold>
                {saved !== undefined && saved > 0 ? formatTokenCount(saved) : '—'}
              </Text>
            </Box>

            {hasAnyPreserved ? (
              <Box flexDirection="column" marginTop={1} marginBottom={1}>
                <Text color={theme.colors.text.muted} bold>
                  Preserved
                </Text>
                {PRESERVED_LABELS.map(([k, label]) => {
                  const val = preserved ? preserved[k] : undefined;
                  if (typeof val !== 'number') return null;
                  return (
                    <Text key={k} color={theme.colors.status.success}>
                      {'\u2713'} {label}: {val}
                    </Text>
                  );
                })}
              </Box>
            ) : null}

            {hasAnyCompressed ? (
              <Box flexDirection="column" marginTop={1} marginBottom={1}>
                <Text color={theme.colors.text.muted} bold>
                  Compressed
                </Text>
                {COMPRESSED_LABELS.map(([k, label]) => {
                  const val = preserved ? preserved[k] : undefined;
                  if (typeof val !== 'number') return null;
                  return (
                    <Text key={k} color={theme.colors.text.dim}>
                      {val} {label}
                    </Text>
                  );
                })}
              </Box>
            ) : null}
          </>
        )}

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
          <Text color={theme.colors.text.muted}>
            <ModalFooter
              shortcuts={[
                { key: '[Esc]', label: 'to close' },
                { key: '[Enter]', label: 'to compact now' },
              ]}
            />
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
