import { appConfig } from '../../config/appConfig';
import type { ModelSelection, ProviderInfo } from './types';

const RECENT_LIMIT = 10;

interface PersistedModelStore {
  current?: ModelSelection | null;
  recent?: ModelSelection[];
  favorite?: ModelSelection[];
}

function sameModel(a: ModelSelection, b: ModelSelection): boolean {
  return a.providerID === b.providerID && a.modelID === b.modelID;
}

type ModelListener = (store: ModelStore) => void;

export class ModelStore {
  private currentModel: ModelSelection | null = null;
  private recentModels: ModelSelection[] = [];
  private favoriteModels: ModelSelection[] = [];
  private listeners: Set<ModelListener> = new Set();

  public subscribe(listener: ModelListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify(): void {
    for (const listener of this.listeners) {
      try {
        listener(this);
      } catch {
        // ignore
      }
    }
  }

  public get current(): ModelSelection | null {
    return this.currentModel;
  }

  public get recent(): ModelSelection[] {
    return this.recentModels;
  }

  public get favorite(): ModelSelection[] {
    return this.favoriteModels;
  }

  /** Hydrate current/recent/favorite from the backend SQL model store. */
  public async hydrate(): Promise<void> {
    try {
      const res = await fetch(appConfig.buildUrl('/startup/model-selection'), {
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(appConfig.timeout.fetchMs),
      });
      if (!res.ok) return;
      const data = (await res.json()) as PersistedModelStore;
      if (Array.isArray(data.recent)) {
        this.recentModels = data.recent.slice(0, RECENT_LIMIT);
      }
      if (Array.isArray(data.favorite)) {
        this.favoriteModels = data.favorite;
      }
      if (data.current) {
        this.currentModel = data.current;
      }
      this.notify();
    } catch {
      // Backend unreachable — keep in-memory state
    }
  }

  public set(sel: ModelSelection): ModelSelection {
    this.currentModel = sel;
    this.pushRecent(sel);
    this.persist();
    this.notify();
    return sel;
  }

  public isFavorite(sel: ModelSelection): boolean {
    return this.favoriteModels.some((item) => sameModel(item, sel));
  }

  public toggleFavorite(sel: ModelSelection): boolean {
    const idx = this.favoriteModels.findIndex((item) => sameModel(item, sel));
    if (idx >= 0) {
      this.favoriteModels = this.favoriteModels.filter((_, i) => i !== idx);
    } else {
      this.favoriteModels = [sel, ...this.favoriteModels];
    }
    this.persist();
    this.notify();
    return idx < 0;
  }

  private pushRecent(sel: ModelSelection): void {
    const rest = this.recentModels.filter((item) => !sameModel(item, sel));
    this.recentModels = [sel, ...rest].slice(0, RECENT_LIMIT);
  }

  /**
   * First-valid-model resolution: persisted current → first recent still present
   * in the provider list. Never invents a default provider/model — returns null
   * when nothing explicitly selected remains valid.
   */
  public getFirstValidModel(providers: ProviderInfo[]): ModelSelection | null {
    const candidates: ModelSelection[] = [];
    if (this.currentModel) candidates.push(this.currentModel);
    candidates.push(...this.recentModels);

    for (const candidate of candidates) {
      if (this.isModelInProviders(candidate, providers)) return candidate;
    }
    return null;
  }

  private isModelInProviders(sel: ModelSelection, providers: ProviderInfo[]): boolean {
    const provider = providers.find((item) => item.id === sel.providerID);
    if (!provider) return false;
    return Boolean(provider.models[sel.modelID]) || provider.model === sel.modelID;
  }

  public toDisplayString(sel: ModelSelection | null): string {
    if (!sel) return '';
    return `${sel.providerID}/${sel.modelID}`;
  }

  /** Persist the store to the backend SQL model store (fire-and-forget). */
  private persist(): void {
    fetch(appConfig.buildUrl('/startup/model-selection'), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        current: this.currentModel,
        recent: this.recentModels,
        favorite: this.favoriteModels,
      }),
      signal: AbortSignal.timeout(appConfig.timeout.fetchMs),
    }).catch(() => {
      // Backend unreachable — keep in-memory state
    });
  }
}

export const modelStore = new ModelStore();
