import { LogItem } from '../../types';

export interface MockEngineState {
  history: LogItem[];
  isExecuting: boolean;
  loadingText: string;
}

export type MockEngineAction =
  | { type: 'SET_HISTORY'; payload: LogItem[] }
  | { type: 'ADD_HISTORY_ITEM'; payload: LogItem }
  | { type: 'SET_EXECUTING'; payload: boolean }
  | { type: 'SET_LOADING_TEXT'; payload: string }
  | { type: 'RESET' };
