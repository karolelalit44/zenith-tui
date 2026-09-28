/**
 * Shared todo-board limits.
 *
 * Lives in `constants/` rather than next to a component because both the
 * presentation components and the event-folding utility read these. Putting
 * them in a component module made `utils/todoBoard` import from
 * `components/`, inverting the dependency direction.
 */

/**
 * How many todo rows a single card shows, and how many lifecycle transitions the
 * activity log keeps.
 *
 * One definition, read by both the pinned card and the in-stream board. They
 * previously carried separate limits (5 vs 10), so a 6-item board showed item 6
 * in the stream but not in the pinned card — two surfaces rendering the same
 * state differently. Both already print a "+N more" line when they truncate, so
 * unifying the limit is enough; the wording is left to each surface.
 */
export const MAX_TODO_ROWS = 8;
export const MAX_TODO_ACTIVITY_ENTRIES = 6;
