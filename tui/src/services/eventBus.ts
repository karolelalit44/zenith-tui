/**
 * Typed pub/sub event bus for the frontend.
 *
 * Provides type-safe subscribe/unsubscribe for scenario events,
 * connection status changes, and custom app events.
 */

type Unsubscribe = () => void;
type Listener<T> = (data: T) => void;

interface EventMap {
  'scenario:event': import('../types/scenario').ScenarioEvent;
  'scenario:complete': undefined;
  'scenario:error': { message: string; code?: string };
  'connection:status': import('./transport/WebSocketClient').WsStatus;
  'confirmation:request': import('../types/scenario').ConfirmationRequestEvent;
  'confirmation:response': { confirmationId: string; approved: boolean };
  'app:mode-change': import('../types/scenario').ScenarioMode;
}

type EventKey = keyof EventMap;

class EventBus {
  private listeners = new Map<string, Set<Listener<any>>>();

  on<K extends EventKey>(event: K, listener: Listener<EventMap[K]>): Unsubscribe {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(listener);
    return () => this.off(event, listener);
  }

  off<K extends EventKey>(event: K, listener: Listener<EventMap[K]>): void {
    this.listeners.get(event)?.delete(listener);
  }

  emit<K extends EventKey>(event: K, data: EventMap[K]): void {
    this.listeners.get(event)?.forEach((listener) => {
      try {
        listener(data);
      } catch (err) {
        console.error(`EventBus listener error for '${event}':`, err);
      }
    });
  }

  once<K extends EventKey>(event: K, listener: Listener<EventMap[K]>): Unsubscribe {
    const wrapper: Listener<EventMap[K]> = (data) => {
      this.off(event, wrapper);
      listener(data);
    };
    return this.on(event, wrapper);
  }

  removeAll(event?: EventKey): void {
    if (event) {
      this.listeners.delete(event);
    } else {
      this.listeners.clear();
    }
  }
}

export const eventBus = new EventBus();
export type { EventKey, EventMap, Unsubscribe };
