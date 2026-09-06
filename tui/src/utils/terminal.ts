/**
 * Terminal screen and scrollback manipulation utilities.
 */

/**
 * Completely clears the terminal screen and scrollback buffer across all platforms
 * (Windows, macOS, Linux) and terminal emulators (Windows Terminal, conhost, iTerm2,
 * Terminal.app, Alacritty, Kitty, VS Code terminal, GNOME Terminal, xterm).
 *
 * Sequence breakdown:
 * - \x1B[H   : Moves cursor to home position (row 1, column 1)
 * - \x1B[2J  : Clears the entire visible screen viewport
 * - \x1B[3J  : Clears the entire scrollback buffer history
 * - \x1B[H   : Re-asserts cursor at home position (row 1, column 1)
 */
export function clearTerminalScreen(): void {
  try {
    if (process.stdout.isTTY) {
      console.clear();
    }
  } catch {
    // Ignore environments where console.clear is unavailable
  }

  try {
    process.stdout.write('\x1B[H\x1B[2J\x1B[3J\x1B[H');
  } catch {
    // Best-effort write
  }
}
