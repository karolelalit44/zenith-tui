import type { ScenarioEvent } from '../../types/scenario';

function estimateEventTokens(event: ScenarioEvent): number {
  let chars = 0;

  if ('text' in event && typeof event.text === 'string') {
    chars += event.text.length;
  }
  if ('thoughts' in event && Array.isArray(event.thoughts)) {
    for (const thought of event.thoughts) {
      if (typeof thought === 'string') {
        chars += thought.length;
      } else if (typeof thought === 'object' && thought !== null && 'text' in thought) {
        chars += (thought as { text: string }).text.length;
      }
    }
  }
  if ('message' in event && typeof event.message === 'string') {
    chars += event.message.length;
  }
  if ('details' in event && typeof event.details === 'string') {
    chars += event.details.length;
  }
  if ('title' in event && typeof event.title === 'string') {
    chars += event.title.length;
  }
  if ('description' in event && typeof event.description === 'string') {
    chars += event.description.length;
  }
  if ('command' in event && typeof event.command === 'string') {
    chars += event.command.length;
  }
  if ('output' in event && Array.isArray(event.output)) {
    for (const line of event.output) {
      if (typeof line === 'string') chars += line.length;
    }
  }
  if ('sections' in event && Array.isArray(event.sections)) {
    for (const section of event.sections) {
      if ('title' in section && typeof section.title === 'string') chars += section.title.length;
      if ('items' in section && Array.isArray(section.items)) {
        for (const item of section.items) {
          if (typeof item === 'string') chars += item.length;
        }
      }
    }
  }
  if ('filePath' in event && typeof event.filePath === 'string') {
    chars += event.filePath.length;
  }
  if ('lines' in event && Array.isArray(event.lines)) {
    for (const line of event.lines) {
      if ('text' in line && typeof line.text === 'string') chars += line.text.length;
    }
  }
  if ('verified' in event && Array.isArray(event.verified)) {
    for (const v of event.verified) {
      if (typeof v === 'string') chars += v.length;
    }
  }

  return Math.round(chars / 4);
}

export function estimateTokensForEvents(events: ScenarioEvent[]): number {
  return events.reduce((sum, evt) => sum + estimateEventTokens(evt), 0);
}

export function formatTokenCount(count: number): string {
  if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}k`;
  }
  return String(count);
}
