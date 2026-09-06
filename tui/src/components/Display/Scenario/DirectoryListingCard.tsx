import { Box, Text } from 'ink';
import React from 'react';
import { SPINNER_FRAMES } from '../../../constants/animation';
import { useTheme } from '../../../theme/ThemeContext';
import type { ToolStepEvent } from '../../../types/scenario';
import type { EventRenderContext } from './componentRegistry';
import { formatErrorSummary } from './errorSummary';

export interface DirectoryListingCardProps {
  event: ToolStepEvent;
  isPending: boolean;
  state: 'running' | 'success' | 'failed' | 'cancelled';
  elapsedMs: number;
  context?: EventRenderContext;
  metaPill: React.ReactNode;
  tick: number;
}

interface ParsedEntry {
  name: string;
  isDir: boolean;
  extension?: string;
}

const MAX_DISPLAY_ENTRIES = 18;

function getFileExtension(filename: string): string {
  const dotIndex = filename.lastIndexOf('.');
  if (dotIndex <= 0 || dotIndex === filename.length - 1) return '';
  return filename.slice(dotIndex + 1).toLowerCase();
}

function parseDirectoryEntries(
  output: string,
  metadata?: Record<string, unknown>,
): {
  dirs: ParsedEntry[];
  files: ParsedEntry[];
  totalDirs: number;
  totalFiles: number;
} {
  const entriesArray = metadata && Array.isArray(metadata.entries) ? (metadata.entries as unknown[]) : undefined;
  const metaEntries = entriesArray?.filter((e): e is string => typeof e === 'string');

  const rawLines =
    metaEntries ??
    output
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.length > 0 && !line.startsWith('[Tool:') && !line.startsWith('… '));

  const dirs: ParsedEntry[] = [];
  const files: ParsedEntry[] = [];

  for (const line of rawLines) {
    const isDir = line.endsWith('/') || line.endsWith('\\');
    const cleanName = isDir ? line.replace(/[/\\]+$/, '') : line;
    if (isDir) {
      dirs.push({ name: `${cleanName}/`, isDir: true });
    } else {
      files.push({ name: cleanName, isDir: false, extension: getFileExtension(cleanName) });
    }
  }

  const metaDirs =
    typeof metadata?.dirs === 'number'
      ? metadata.dirs
      : typeof metadata?.subdirs === 'number'
        ? metadata.subdirs
        : undefined;
  const metaFiles = typeof metadata?.files === 'number' ? metadata.files : undefined;

  return {
    dirs,
    files,
    totalDirs: metaDirs ?? dirs.length,
    totalFiles: metaFiles ?? files.length,
  };
}

export const DirectoryListingCard: React.FC<DirectoryListingCardProps> = React.memo(
  ({ event, isPending, state, metaPill, tick }) => {
    const { theme } = useTheme();

    const rawPath =
      (event.params.path as string) ||
      (event.params.DirectoryPath as string) ||
      (event.params.directory as string) ||
      (event.params.filepath as string) ||
      (event.metadata?.path as string) ||
      '.';

    const displayPath = rawPath === '.' ? './' : rawPath.endsWith('/') ? rawPath : `${rawPath}/`;

    const rawOutput = event.output || (typeof event.metadata?.output === 'string' ? event.metadata.output : '') || '';

    const { dirs, files, totalDirs, totalFiles } = parseDirectoryEntries(rawOutput, event.metadata);
    const allEntries = [...dirs, ...files];

    const visibleEntries = allEntries.slice(0, MAX_DISPLAY_ENTRIES);
    const overflowCount = Math.max(0, allEntries.length - MAX_DISPLAY_ENTRIES);

    const ok = state === 'success';
    const borderColor = isPending
      ? theme.colors.status.info
      : state === 'failed'
        ? theme.colors.status.error
        : state === 'cancelled'
          ? theme.colors.status.warning
          : theme.colors.border.muted;

    const getFileColor = (ext?: string): string => {
      switch (ext) {
        case 'ts':
        case 'tsx':
        case 'js':
        case 'jsx':
        case 'py':
        case 'rs':
        case 'go':
          return theme.colors.text.bright;
        case 'json':
        case 'yaml':
        case 'yml':
        case 'toml':
        case 'env':
          return theme.colors.status.warning;
        case 'md':
        case 'txt':
        case 'doc':
          return theme.colors.text.ethereal;
        default:
          return theme.colors.code.output;
      }
    };

    return (
      <Box flexDirection="column" width="100%" marginBottom={1} paddingX={1}>
        <Box
          flexDirection="column"
          backgroundColor={theme.colors.code.background}
          borderStyle="round"
          borderColor={borderColor}
          paddingX={1}
          paddingY={0}
        >
          {/* Card Header Bar */}
          <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap" justifyContent="space-between">
            <Box flexDirection="row" alignItems="center" flexGrow={1} flexShrink={1} overflow="hidden">
              {isPending ? (
                <Text color={theme.colors.status.info} bold>
                  {SPINNER_FRAMES[tick % SPINNER_FRAMES.length]}{' '}
                </Text>
              ) : state === 'cancelled' ? (
                <Text color={theme.colors.status.warning} bold>
                  ⊘{' '}
                </Text>
              ) : (
                <Text color={theme.colors.status.accent} bold>
                  📁{' '}
                </Text>
              )}

              <Text color={theme.colors.status.accent} bold wrap="truncate-end">
                {displayPath}
              </Text>

              {!isPending && ok && (
                <Box marginLeft={1}>
                  <Text color={theme.colors.text.dim}>
                    ({totalDirs} {totalDirs === 1 ? 'folder' : 'folders'} · {totalFiles}{' '}
                    {totalFiles === 1 ? 'file' : 'files'})
                  </Text>
                </Box>
              )}
            </Box>

            {metaPill}
          </Box>

          {/* Pending state */}
          {isPending && (
            <Box paddingLeft={2} marginTop={0}>
              <Text color={theme.colors.text.dim} italic>
                Scanning directory...
              </Text>
            </Box>
          )}

          {/* Error / Cancelled state */}
          {!isPending && !ok && event.error && (
            <Box paddingLeft={2} marginTop={0}>
              <Text
                color={state === 'cancelled' ? theme.colors.status.warning : theme.colors.status.error}
                wrap="truncate-end"
              >
                {formatErrorSummary(event.error)}
              </Text>
            </Box>
          )}

          {/* Directory Content List */}
          {!isPending && ok && (
            <Box flexDirection="column" paddingLeft={1} marginTop={0} marginBottom={0}>
              {visibleEntries.length === 0 ? (
                <Box paddingLeft={1}>
                  <Text color={theme.colors.text.dim} italic>
                    (empty directory)
                  </Text>
                </Box>
              ) : (
                visibleEntries.map((entry, idx) => {
                  const isLast = idx === visibleEntries.length - 1 && overflowCount === 0;
                  const branchGlyph = isLast ? '└── ' : '├── ';

                  return (
                    <Box key={`${entry.name}-${idx}`} flexDirection="row" alignItems="center">
                      <Text color={theme.colors.border.muted}>{branchGlyph}</Text>
                      {entry.isDir ? (
                        <>
                          <Text color={theme.colors.status.info}>📁 </Text>
                          <Text color={theme.colors.status.info} bold wrap="truncate-end">
                            {entry.name}
                          </Text>
                        </>
                      ) : (
                        <>
                          <Text color={theme.colors.text.muted}>📄 </Text>
                          <Text color={getFileColor(entry.extension)} wrap="truncate-end">
                            {entry.name}
                          </Text>
                        </>
                      )}
                    </Box>
                  );
                })
              )}

              {overflowCount > 0 && (
                <Box flexDirection="row" alignItems="center">
                  <Text color={theme.colors.border.muted}>└── </Text>
                  <Text color={theme.colors.text.dim} italic>
                    +{overflowCount} more entries
                  </Text>
                </Box>
              )}
            </Box>
          )}
        </Box>
      </Box>
    );
  },
);

DirectoryListingCard.displayName = 'DirectoryListingCard';
