/** Strip ANSI escape sequences from text to prevent Ink rendering glitches. */
export function stripAnsi(text: string): string {
  return text.replace(/\x1b\[[0-9;?]*[a-zA-Z]/g, '')
    .replace(/\x1b\].*?(?:\x07|\x1b\\)/g, '');
}
