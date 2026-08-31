export interface MentionToken {
  /** The '@' plus the token text, e.g. `@src/auth`. */
  raw: string;
  /** The text after '@' (may be empty for a freshly typed '@'). */
  text: string;
  /** Character index of the '@' in the input. */
  start: number;
  /** Character index just past the token. */
  end: number;
}

/** Character set allowed inside a mention token (path-ish characters). */
const TOKEN_CHARS = /[^\s@]/;

/**
 * Parse all `@mention` tokens in an input string. Stops a token at whitespace
 * or at another '@'. A trailing '@' with nothing after it yields an empty token.
 */
export function parseMentions(input: string): MentionToken[] {
  const tokens: MentionToken[] = [];
  let i = 0;
  while (i < input.length) {
    if (input[i] === '@') {
      let j = i + 1;
      while (j < input.length && TOKEN_CHARS.test(input[j])) {
        j += 1;
      }
      tokens.push({
        raw: input.slice(i, j),
        text: input.slice(i + 1, j),
        start: i,
        end: j,
      });
      i = j;
    } else {
      i += 1;
    }
  }
  return tokens;
}

/** Find the mention token whose '@' is at `position`, or the token containing it. */
export function tokenAtOffset(input: string, position: number): MentionToken | undefined {
  return parseMentions(input).find((t) => position >= t.start && position < t.end + 1);
}

/**
 * The mention token that serves as the active `@` completion trigger, given a
 * cursor position. Returns a token when the cursor sits at or just after an
 * `@` (including an empty trailing `@` with only the partial text).
 */
export function activeMentionAtOffset(input: string, position: number): MentionToken | undefined {
  const before = input.slice(0, position);
  const tokens = parseMentions(before);
  const last = tokens[tokens.length - 1];
  if (!last) return undefined;
  // Cursor must be at or inside the token ('@' included), so a trailing
  // whitespace that closed the token does not keep the completion active.
  if (position >= last.start && position <= last.end) return last;
  return undefined;
}

/**
 * Replace the mention token at `start..end` with a new token text.
 * Returns the new input and the updated end cursor position.
 */
export function replaceMention(input: string, token: MentionToken, newText: string): { value: string; end: number } {
  const value = `${input.slice(0, token.start)}@${newText}${input.slice(token.end)}`;
  return { value, end: token.start + 1 + newText.length };
}

/** Insert a fresh mention at a cursor position. */
export function insertMentionAt(input: string, position: number, text: string): { value: string; end: number } {
  const value = `${input.slice(0, position)}@${text}${input.slice(position)}`;
  return { value, end: position + 1 + text.length };
}

/** Remove a mention token entirely from the input. */
export function removeMention(input: string, token: MentionToken): { value: string; end: number } {
  const value = `${input.slice(0, token.start)}${input.slice(token.end)}`;
  return { value, end: token.start };
}
