import { useCallback, useState } from 'react';
import { loadUserProfile, saveUserProfile } from '../services/data/userProfileService';
import type { Persona } from '../types';

export interface UsePersonaReturn {
  persona: Persona;
  setPersona: (p: Persona) => void;
}

export function usePersona(initialPersona?: Persona): UsePersonaReturn {
  const [persona, setPersonaState] = useState<Persona>(() => {
    if (initialPersona) return initialPersona;
    const profile = loadUserProfile();
    return (profile.persona as Persona) || 'architect';
  });

  const setPersona = useCallback((p: Persona) => {
    setPersonaState(p);
    saveUserProfile({ persona: p });
  }, []);

  return {
    persona,
    setPersona,
  };
}
