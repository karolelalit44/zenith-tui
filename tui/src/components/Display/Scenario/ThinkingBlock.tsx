import { Box, Text } from 'ink';
import React from 'react';
import { isZenithBright, isZenithDim, ZENITH_PULSE_FRAMES, ZENITH_RETICLE } from '../../../constants/animation';
import { useAnimationTick } from '../../../context/AnimationContext';
import { useTheme } from '../../../theme/ThemeContext';
import type { ThinkingEvent, ThinkingThought } from '../../../types/scenario';
import { formatDuration } from '../../../utils/text';

import type { EventRenderContext } from './componentRegistry';

interface ThinkingBlockProps {
  event: ThinkingEvent;
  context?: EventRenderContext;
}

const getThoughtText = (thought: string | ThinkingThought): string =>
  typeof thought === 'string' ? thought : thought.text;

function isStatusPlaceholder(text: string): boolean {
  const lower = text.trim().toLowerCase();
  return lower === 'processing your request' || lower.startsWith('processing your request');
}

function hasRealReasoning(event: ThinkingEvent): boolean {
  return event.thoughts.some((thought) => {
    const text = getThoughtText(thought);
    return Boolean(text) && text.trim().length > 0 && !isStatusPlaceholder(text);
  });
}

/**
 * Static bright Zenith core for completed telemetry. No animation
 * subscription, so historical/completed blocks never re-render on tick.
 */
const ZenithStaticGlyph: React.FC<{ suffix: string }> = React.memo(({ suffix }) => {
  const { theme } = useTheme();
  return (
    <Text color={theme.colors.status.info} bold>
      {ZENITH_RETICLE}
      {suffix}
    </Text>
  );
});

ZenithStaticGlyph.displayName = 'ZenithStaticGlyph';

/**
 * Breathing pulse reticle for live deliberation only:
 *   ✣ (dim) → ✳ (normal) → ⨳ (BRIGHT core) → ✳ (normal), repeat.
 * Isolating useAnimationTick() here keeps the 100ms re-render storm to the
 * single live block instead of every historical ThinkingBlock.
 */
const ZenithPulseGlyph: React.FC<{ suffix: string }> = ({ suffix }) => {
  const { theme } = useTheme();
  const tick = useAnimationTick();
  const glyph = ZENITH_PULSE_FRAMES[tick % ZENITH_PULSE_FRAMES.length];
  return (
    <Text color={theme.colors.status.info} dimColor={isZenithDim(glyph)} bold={isZenithBright(glyph)}>
      {glyph}
      {suffix}
    </Text>
  );
};

ZenithPulseGlyph.displayName = 'ZenithPulseGlyph';

export const ThinkingBlock: React.FC<ThinkingBlockProps> = React.memo(({ event, context }) => {
  const { theme } = useTheme();
  const isCalm = context?.calmMode === true;

  // In Calm Mode or when explicitly toggled via ctrl+h / /think,
  // reasoning renders as a compact, single-line telemetry chip.
  const isCollapsed = isCalm || context?.thinkingCollapsed === true;

  if (!hasRealReasoning(event)) {
    return null;
  }

  // Historical turns never pulse: a stuck partial:true must render as static
  // completed telemetry instead of Deliberating forever.
  const isStreaming = event.partial === true && context?.isRunning !== false && context?.isHistorical !== true;
  const durationStr = event.duration > 0 ? formatDuration(event.duration) : '';
  const firstRealThought = event.thoughts
    .map((thought) => getThoughtText(thought).trim())
    .find((text) => text.length > 0 && !isStatusPlaceholder(text));
  const firstLine = firstRealThought ? firstRealThought.split('\n')[0].trim() : '';
  const preview = firstLine && firstLine.length >= 72 ? `${firstLine.slice(0, 71)}…` : firstLine;

  return (
    <Box flexDirection="column" width="100%" marginBottom={isCollapsed ? 0 : 1} paddingX={1}>
      {isCollapsed ? (
        <Box flexDirection="row" alignItems="center" width="100%" flexWrap="nowrap">
          {isStreaming ? <ZenithPulseGlyph suffix=" " /> : <ZenithStaticGlyph suffix=" " />}
          {isStreaming ? (
            <>
              <Text color={theme.colors.status.info} bold>
                Deliberating
              </Text>
              {durationStr ? (
                <Text color={theme.colors.text.muted}> · {durationStr}</Text>
              ) : (
                <Text color={theme.colors.text.dim}> …</Text>
              )}
            </>
          ) : durationStr ? (
            <Text color={theme.colors.text.muted}>
              {isCalm ? `Deliberated ${durationStr}` : `Thought for ${durationStr}`}
            </Text>
          ) : (
            <Text color={theme.colors.text.muted}>{isCalm ? 'Deliberated' : 'Thought'}</Text>
          )}
          {preview ? (
            <>
              <Text color={theme.colors.text.dim}> · </Text>
              <Box flexShrink={1}>
                <Text color={theme.colors.text.dim} italic wrap="truncate-end">
                  {preview}
                </Text>
              </Box>
            </>
          ) : null}
        </Box>
      ) : (
        <Box flexDirection="row" alignItems="center" marginBottom={1}>
          {isStreaming ? <ZenithPulseGlyph suffix=" Thinking" /> : <ZenithStaticGlyph suffix=" Thinking" />}
          {isStreaming && !durationStr ? (
            <Text color={theme.colors.text.dim}> …</Text>
          ) : durationStr ? (
            <Text color={theme.colors.text.muted}> · {durationStr}</Text>
          ) : null}
        </Box>
      )}

      {!isCollapsed &&
        (() => {
          const isLive = Boolean(context?.isRunning && !context?.isHistorical);
          const maxThoughts = 5;
          const thoughtsToRender =
            isLive && event.thoughts.length > maxThoughts ? event.thoughts.slice(-maxThoughts) : event.thoughts;
          const hiddenCount = event.thoughts.length - thoughtsToRender.length;

          return (
            <Box flexDirection="column" paddingLeft={2} width="100%">
              {hiddenCount > 0 && (
                <Box flexDirection="row" alignItems="center" marginBottom={0}>
                  <Text color={theme.colors.text.dim} dimColor italic>
                    … ({hiddenCount} earlier thoughts)
                  </Text>
                </Box>
              )}
              {thoughtsToRender.map((thought, idx) => {
                const thoughtText = getThoughtText(thought);
                const lines = thoughtText.split('\n');
                return (
                  <Box key={idx} flexDirection="column" width="100%" marginBottom={0}>
                    {lines.map((line, lineIdx) => (
                      <Box key={lineIdx} flexDirection="row" alignItems="flex-start" width="100%" marginBottom={0}>
                        <Box width={2} flexShrink={0}>
                          <Text color={theme.colors.text.dim}>│</Text>
                        </Box>
                        <Box flexShrink={1}>
                          <Text color={theme.colors.text.muted} italic wrap="wrap">
                            {line || ' '}
                          </Text>
                        </Box>
                      </Box>
                    ))}
                  </Box>
                );
              })}
            </Box>
          );
        })()}
    </Box>
  );
});

ThinkingBlock.displayName = 'ThinkingBlock';
