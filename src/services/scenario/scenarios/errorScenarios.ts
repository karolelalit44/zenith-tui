import { Scenario } from '../../../types/scenario';

let idCounter = 0;
const uid = () => `err_${Date.now()}_${++idCounter}`;

export const modeMismatchScenario = (prompt: string, currentMode: 'plan' | 'build'): Scenario => {
  const suggestedMode = currentMode === 'plan' ? 'build' : 'plan';
  const reason = currentMode === 'plan'
    ? 'Code creation/editing requested while in Plan mode.'
    : 'High-level architectural planning requested while in Build mode.';

  return {
    id: `mismatch_${Date.now()}`,
    mode: currentMode,
    prompt,
    events: [
      {
        kind: 'thinking',
        id: uid(),
        thoughts: [
          { text: `Evaluating prompt intent: "${prompt}"`, delay: 200 },
          { text: `Detected conflict between prompt intent and active [${currentMode.toUpperCase()}] mode`, delay: 250 },
        ],
        duration: 800,
      },
      {
        kind: 'mode_mismatch',
        id: uid(),
        currentMode,
        suggestedMode,
        reason,
        prompt,
      },
    ],
  };
};

export const providerErrorScenario = (prompt: string, errorType = 'rate_limit'): Scenario => ({
  id: `provider_err_${Date.now()}`,
  mode: 'build',
  prompt,
  events: [
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Connecting to Zenith 3.7 Sonnet API provider...', delay: 200 },
        { text: 'HTTP 429 Too Many Requests response received from provider endpoint', delay: 250 },
      ],
      duration: 800,
    },
    {
      kind: 'error',
      id: uid(),
      message: 'Provider Rate Limit Exceeded (HTTP 429)',
      stack: 'RateLimitError: Tokens per minute (TPM) limit reached for Zenith 3.7 Sonnet. Reset in 12.4s.',
    },
    {
      kind: 'retry',
      id: uid(),
      message: 'Exponential backoff scheduled (Retrying in 5s...)',
      attempt: 1,
    },
  ],
});

export const systemErrorScenario = (prompt: string): Scenario => ({
  id: `system_err_${Date.now()}`,
  mode: 'build',
  prompt,
  events: [
    {
      kind: 'thinking',
      id: uid(),
      thoughts: [
        { text: 'Inspecting project workspace configuration...', delay: 200 },
        { text: 'Failed to access target file system path due to missing read permissions', delay: 250 },
      ],
      duration: 800,
    },
    {
      kind: 'error',
      id: uid(),
      message: 'Permission Denied: Cannot access ./backend/app/config.py',
      stack: 'EACCES: permission denied, open "./backend/app/config.py"',
      command: 'fs.readFile("./backend/app/config.py")',
    },
  ],
});
