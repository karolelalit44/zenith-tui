import type { ScenarioEvent } from '../../types/scenario';

export const getEventDelay = (event: ScenarioEvent): number => {
  switch (event.kind) {
    case 'thinking':
      return event.duration;
    case 'file_create':
      return 800;
    case 'file_edit':
      return 600;
    case 'file_delete':
      return 400;
    case 'terminal':
      return event.duration + 400;
    case 'error':
      return 600;
    case 'warning':
      return 400;
    case 'retry':
      return 400;
    case 'success':
      return 300;
    case 'summary':
      return 200;
    case 'message':
      return 300;
    case 'progress':
      return 400;
    case 'waiting':
      return event.duration;
    case 'test_execution':
      return 1000;
    case 'build_step':
      return (event.duration ?? 500) + 300;
    case 'deployment':
      return 800;
    case 'analysis':
      return event.sections.length * 200 + 300;
    default:
      return 300;
  }
};
