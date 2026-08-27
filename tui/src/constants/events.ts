/**
 * Stable id for the single live progress card of the active turn.
 *
 * Backend progress snapshots arrive with unique rpc ids; collapsing them
 * onto one stable id lets the standard upsert path replace the card in
 * place instead of stacking a new card per snapshot.
 */
export const LIVE_PROGRESS_EVENT_ID = 'evt_progress_live';

/**
 * Latency placeholder: if no backend event has arrived this many ms into a
 * turn, surface a live progress row so the silence feels intentional. It is
 * a progress event, so it vanishes from scrollback on completion.
 */
export const BACKEND_RESPONSE_PLACEHOLDER_DELAY_MS = 2000;
export const BACKEND_RESPONSE_PLACEHOLDER_LABEL = 'Waiting for backend response';
