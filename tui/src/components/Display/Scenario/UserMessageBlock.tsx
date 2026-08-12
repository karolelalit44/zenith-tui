import { Box, Text } from 'ink';
import React from 'react';
import { useTerminalDimensions } from '../../../hooks/useTerminalDimensions';
import { modelStore } from '../../../services/providers/ModelStore';
import { useTheme } from '../../../theme/ThemeContext';

interface UserMessageBlockProps {
  prompt: string;
  model?: string;
  /**
   * Short timestamp frozen at turn creation: "HH:MM" (e.g. "12:08").
   * Used when terminal width < 80 columns.
   */
  timestamp?: string;
  /**
   * Long timestamp frozen at turn creation: "HH:MM, DD Mon" (e.g. "12:08, 12 Aug").
   * Used when terminal width >= 80 columns.
   */
  timestampLong?: string;
}

/**
 * Renders a user message block with:
 *   - A full-width highlighted prompt bar (background colour + ❯ prefix)
 *   - A metadata row: model indicator (left) + timestamp (right)
 *
 * Spacing contract: this component owns NO external vertical margins.
 * All top/bottom spacing is controlled by the parent (App.tsx) so that
 * both the live render and the <Static> render look identical.
 *
 * Layout rules that prevent terminal-edge wrapping:
 *   1. No `justifyContent="space-between"` — a flex-grow spacer is used instead.
 *   2. paddingRight={2} on the metadata row guarantees the rightmost character
 *      is always at least 2 columns from the terminal edge.
 *   3. Timestamps are consumed from frozen props only — no new Date() in render.
 */
export const UserMessageBlock: React.FC<UserMessageBlockProps> = React.memo(
  ({ prompt, model, timestamp, timestampLong }) => {
    const { theme } = useTheme();
    const { columns } = useTerminalDimensions();

    // Pick the frozen display string based on current terminal width.
    // Both values were computed once at turn-creation time and are immutable.
    const displayTime = columns >= 80 ? (timestampLong ?? timestamp ?? '') : (timestamp ?? '');

    // Resolve the model label from props or the live model store.
    const modelLabel =
      model ?? (modelStore.current ? modelStore.toDisplayString(modelStore.current) : '');

    return (
      <Box flexDirection="column" width="100%" marginTop={1} marginBottom={1}>
        {/* ── Prompt bar ──────────────────────────────────────────────── */}
        {/* Full-width background highlight + ❯ prefix + prompt text.     */}
        {/* paddingX={2}: extra horizontal inset inside the highlight bar  */}
        {/* paddingY={0}: keep it a single-line highlight, not a fat block */}
        <Box
          flexDirection="row"
          width="100%"
          backgroundColor={theme.colors.code.background}
          paddingX={2}
          paddingY={0}
        >
          <Box marginRight={1} flexShrink={0}>
            <Text color={theme.colors.text.emerald} bold>❯</Text>
          </Box>
          <Box flexGrow={1} flexShrink={1}>
            <Text color={theme.colors.text.bright} wrap="wrap" bold>
              {prompt}
            </Text>
          </Box>
        </Box>

        {/* ── Metadata row ─────────────────────────────────────────────── */}
        {/* Layout: [model label] [flex spacer] [timestamp]                 */}
        {/*                                                                  */}
        {/* paddingRight={2} — rightmost char is guaranteed ≥2 cols from   */}
        {/* terminal edge, which prevents orphan char wrap on resize.        */}
        {/*                                                                  */}
        {/* No justifyContent="space-between" — a flexGrow={1} spacer Box  */}
        {/* pushes the timestamp right without risking terminal edge bleed.  */}
        <Box
          flexDirection="row"
          width="100%"
          paddingLeft={3}
          paddingRight={2}
          flexWrap="nowrap"
        >
          {/* Model indicator — shrinks and truncates when space is tight */}
          <Box flexShrink={1} flexGrow={0} overflow="hidden">
            {modelLabel ? (
              <Text color={theme.colors.text.muted} wrap="truncate-end">
                {'◇ '}
                <Text color={theme.colors.text.dim}>{modelLabel}</Text>
              </Text>
            ) : null}
          </Box>

          {/* Spacer — absorbs remaining space between model and timestamp */}
          <Box flexGrow={1} flexShrink={1} />

          {/* Timestamp — never shrinks; stays right of the spacer */}
          {displayTime ? (
            <Box flexShrink={0}>
              <Text color={theme.colors.text.dim}>{displayTime}</Text>
            </Box>
          ) : null}
        </Box>
      </Box>
    );
  },
);
