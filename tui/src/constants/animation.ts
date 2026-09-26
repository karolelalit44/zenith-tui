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
 * 4-frame loop with no consecutive duplicates so the breath reads evenly.
 * Each frame holds for ZENITH_PULSE_TICKS_PER_FRAME animation ticks (100ms
 * each): 200ms per frame → 800ms per breath. One raw tick per frame flickers
 * too fast for the eye to register the ✣→✳→⨳ transformation.
 *
 * Font note: ⨳ (U+2A33) needs a Nerdfont-patched or recent
 * Windows Terminal / Ghostty / Alacritty font. If the glyph is missing the
 * terminal shows tofu — completed states still hold static ⨳ by design, so
 * verify on targets before swapping the core glyph.
 */
export const ZENITH_PULSE_FRAMES = ['✣', '✳', '⨳', '✳'];

/** Raw 100ms animation ticks each pulse frame stays on screen. */
export const ZENITH_PULSE_TICKS_PER_FRAME = 2;

/** Glyph for a raw animation tick — the visible transformation step. */
export function zenithPulseGlyphForTick(tick: number): string {
  const frame = Math.floor(tick / ZENITH_PULSE_TICKS_PER_FRAME) % ZENITH_PULSE_FRAMES.length;
  return ZENITH_PULSE_FRAMES[frame];
}

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
