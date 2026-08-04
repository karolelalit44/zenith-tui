import { type CommandRunContext, commandRegistry } from './CommandRegistry';

export class CommandService {
  public dispatchCommand(rawInput: string, ctx: CommandRunContext): boolean {
    const trimmed = rawInput.trim().toLowerCase();
    const def = commandRegistry.find((c) => c.slash && c.slash.toLowerCase() === trimmed);
    if (!def) return false;

    def.run(ctx);
    return true;
  }
}

export const commandService = new CommandService();
