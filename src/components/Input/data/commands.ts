import { commandService } from '../../../services/data/CommandService';
import type { CommandHint } from '../../../types';

export const COMMAND_LIST: CommandHint[] = commandService.getCommandHints();
