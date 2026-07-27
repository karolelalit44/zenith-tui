import type React from 'react';
import type { ScenarioEvent } from '../../../types/scenario';
import type { EventRenderContext } from './componentRegistry';

export interface EventComponentProps {
  event: ScenarioEvent;
  context?: EventRenderContext;
}

export interface EventComponentMeta {
  isExpandable?: boolean;
  isFocusable?: boolean;
  isAnimatable?: boolean;
}

export type EventComponentWithMeta = React.FC<EventComponentProps> & EventComponentMeta;
