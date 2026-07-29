import optionsData from './options.json';
export class CommandService {
    commands;
    constructor() {
        this.commands = (optionsData.commands || []);
    }
    dispatchCommand(rawInput, handlers) {
        const trimmed = rawInput.trim().toLowerCase();
        const match = this.commands.find((c) => c.command.toLowerCase() === trimmed);
        if (!match) {
            return false;
        }
        switch (match.action) {
            case 'overlay':
                if (match.target) {
                    handlers.openOverlay(match.target);
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
                    handlers.setMode(match.target);
                }
                return true;
            default:
                return false;
        }
    }
}
export const commandService = new CommandService();
