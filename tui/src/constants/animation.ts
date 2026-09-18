export const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];

/**
 * Zenith celestial reticle pulse — breathing cycle for thinking/deliberation.
 *
 * Pulse version (breath, then repeat):
 *   ✣ → dim → ✳ → normal → ⨳ → BRIGHT (Zenith core) → ✳ → normal → ✣ → dim
 *   Then repeat: ✣ → ✳ → ⨳ → ✳ → ✣
 *
 * Glyphs:
 *   ✣ U+2723 (dim outer) · ✳ U+2733 (normal) · ⨳ U+2A33 (bright Zenith core)
 *
 * Color intensity rides the same transformation:
 *   ✣ dim · ✳ cyan (status.info) · ⨳ bright cyan (status.info + bold)
 *
 * 4-frame loop with no consecutive duplicates so `tick % length` breathes
 * evenly at 100ms per frame (400ms per breath). The 5-line spec above shows
 * one breath including the return to dim; the repeat wraps to index 0.
 *
 * Font note: ⨳ (U+2A33) needs a Nerdfont-patched or recent
 * Windows Terminal / Ghostty / Alacritty font. If the glyph is missing the
 * terminal shows tofu — completed states still hold static ⨳ by design, so
 * verify on targets before swapping the core glyph.
 */
export const ZENITH_PULSE_FRAMES = ['✣', '✳', '⨳', '✳'];

/** Static Zenith core for completed states (telemetry chips, banners). */
export const ZENITH_RETICLE = '⨳';

/** Bright core frame — render bold for bright-cyan intensity. */
export function isZenithBright(glyph: string): boolean {
  return glyph === '⨳';
}

/** Dim outer frame — render dimColor for dim intensity. */
export function isZenithDim(glyph: string): boolean {
  return glyph === '✣';
}
