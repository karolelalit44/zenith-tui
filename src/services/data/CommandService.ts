import type { OverlayType } from '../../hooks/useOverlayManager';
import type { ScenarioMode } from '../../types/scenario';
import optionsData from './options.json';

interface CommandOption {
  command: string;
  action: 'overlay' | 'clear' | 'compact' | 'mode' | string;
  target?: string;
  description: string;
}

interface CommandHandlers {
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
