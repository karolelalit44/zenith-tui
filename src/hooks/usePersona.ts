import { useCallback, useState } from 'react';
import type { Persona } from '../types';

export interface UsePersonaReturn {
  persona: Persona;
  setPersona: (p: Persona) => void;
}

export function usePersona(initialPersona: Persona = 'architect'): UsePersonaReturn {
  const [persona, setPersonaState] = useState<Persona>(initialPersona);

  const setPersona = useCallback((p: Persona) => {
    setPersonaState(p);
  }, []);

  return {
    persona,
    setPersona,
  };
}
