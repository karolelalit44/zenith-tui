/**
 * Typed pub/sub event bus for the frontend.
 *
 * Provides type-safe subscribe/unsubscribe for scenario events,
 * connection status changes, and custom app events.
 */
class EventBus {
    listeners = new Map();
    on(event, listener) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, new Set());
        }
        this.listeners.get(event).add(listener);
        return () => this.off(event, listener);
    }
    off(event, listener) {
        this.listeners.get(event)?.delete(listener);
    }
    emit(event, data) {
        this.listeners.get(event)?.forEach((listener) => {
            try {
                listener(data);
            }
            catch (err) {
                console.error(`EventBus listener error for '${event}':`, err);
            }
        });
    }
    once(event, listener) {
        const wrapper = (data) => {
            this.off(event, wrapper);
            listener(data);
        };
        return this.on(event, wrapper);
    }
    removeAll(event) {
        if (event) {
            this.listeners.delete(event);
        }
        else {
            this.listeners.clear();
        }
    }
}
export const eventBus = new EventBus();
