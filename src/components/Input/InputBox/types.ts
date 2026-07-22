import { Persona } from '../../../types';
import { Screen } from '../../../types';

export type OverlayState = 'none' | 'autocomplete' | 'plugin' | 'settings' | 'theme' | 'context' | 'persona';

export interface InputBoxProps {
  input: string;
  setInput: (value: string) => void;
  overlay: OverlayState;
  setOverlay: (state: OverlayState) => void;
  isExecuting: boolean;
  executeCommand: (input: string) => void;
  persona: Persona;
  setPersona: (persona: Persona) => void;
  autoApprove: boolean;
  setAutoApprove: React.Dispatch<React.SetStateAction<boolean>>;
}
