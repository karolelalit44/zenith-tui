import type { Scenario, ScenarioMode } from '../../../types/scenario';
import { createScenario, type ScenarioTemplate } from '../templateLoader';

const modeMismatchTemplate = (prompt: string, currentMode: ScenarioMode): ScenarioTemplate => {
  const suggestedMode = currentMode === 'plan' ? 'build' : 'plan';
  const reason =
    currentMode === 'plan'
      ? 'Code creation/editing requested while in Plan mode.'
      : 'High-level architectural planning requested while in Build mode.';

  return {
    mode: currentMode,
    events: [
      {
        kind: 'thinking',
        thoughts: [
          { text: `Evaluating prompt intent: "${prompt}"`, delay: 200 },
          {
            text: `Detected conflict between prompt intent and active [${currentMode.toUpperCase()}] mode`,
            delay: 250,
          },
        ],
        duration: 800,
      },
      {
        kind: 'mode_mismatch',
        currentMode,
        suggestedMode,
        reason,
        prompt,
      },
    ],
  };
};

export const modeMismatchScenario = (prompt: string, currentMode: ScenarioMode): Scenario =>
  createScenario(prompt, modeMismatchTemplate(prompt, currentMode));

const providerErrorTemplate: ScenarioTemplate = {
  mode: 'build',
  events: [
    {
      kind: 'thinking',
      thoughts: [
        { text: 'Connecting to Zenith 3.7 Sonnet API provider...', delay: 200 },
        { text: 'HTTP 429 Too Many Requests response received from provider endpoint', delay: 250 },
      ],
      duration: 800,
    },
    {
      kind: 'error',
      message: 'Provider Rate Limit Exceeded (HTTP 429)',
      stack: 'RateLimitError: Tokens per minute (TPM) limit reached for Zenith 3.7 Sonnet. Reset in 12.4s.',
    },
    {
      kind: 'retry',
      message: 'Exponential backoff scheduled (Retrying in 5s...)',
      attempt: 1,
    },
  ],
};

export const providerErrorScenario = (prompt: string): Scenario => createScenario(prompt, providerErrorTemplate);

const systemErrorTemplate: ScenarioTemplate = {
  mode: 'build',
  events: [
    {
      kind: 'thinking',
      thoughts: [
        { text: 'Inspecting project workspace configuration...', delay: 200 },
        { text: 'Failed to access target file system path due to missing read permissions', delay: 250 },
      ],
      duration: 800,
    },
    {
      kind: 'error',
      message: 'Permission Denied: Cannot access ./backend/app/config.py',
      stack: 'EACCES: permission denied, open "./backend/app/config.py"',
      command: 'fs.readFile("./backend/app/config.py")',
    },
  ],
};

export const systemErrorScenario = (prompt: string): Scenario => createScenario(prompt, systemErrorTemplate);
