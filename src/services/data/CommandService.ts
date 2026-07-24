import type { CommandHint } from '../../types';
import type { OverlayType } from '../../hooks/useOverlayManager';
import type { ScenarioMode } from '../../types/scenario';
import optionsData from './options.json';

export interface CommandOption {
  command: string;
  action: 'overlay' | 'clear' | 'compact' | 'mode' | string;
  target?: string;
  description: string;
}

export interface CommandHandlers {
  openOverlay: (target: OverlayType) => void;
  clearTurns: () => void;
  compactTurns: () => void;
  setMode: (mode: ScenarioMode) => void;
}

export class CommandService {
  private commands: CommandOption[];

  constructor() {
    this.commands = (optionsData.commands || []) as CommandOption[];
  }

  public getCommands(): CommandOption[] {
    return this.commands;
  }

  public getCommandHints(): CommandHint[] {
    const seen = new Set<string>();
    const hints: CommandHint[] = [];

    this.commands.forEach((cmd) => {
      if (!seen.has(cmd.command)) {
        seen.add(cmd.command);
        hints.push({ command: cmd.command, description: cmd.description });
      }
    });

    return hints;
  }

  public dispatchCommand(rawInput: string, handlers: CommandHandlers): boolean {
    const trimmed = rawInput.trim().toLowerCase();
    const match = this.commands.find((c) => c.command.toLowerCase() === trimmed);

    if (!match) {
      return false;
    }

    switch (match.action) {
      case 'overlay':
        if (match.target) {
          handlers.openOverlay(match.target as OverlayType);
        }
        return true;
      case 'clear':
        handlers.clearTurns();
        return true;
      case 'compact':
        handlers.compactTurns();
        return true;
      case 'mode':
        if (match.target) {
          handlers.setMode(match.target as ScenarioMode);
        }
        return true;
      default:
        return false;
    }
  }
}

export const commandService = new CommandService();
