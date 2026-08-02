import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import type { ModelSelection, ProviderInfo } from './types';

const MODEL_DIR = path.join(os.homedir(), '.zenith');
const MODEL_PATH = path.join(MODEL_DIR, 'model.json');
const RECENT_LIMIT = 10;

function getModelPath(): string {
  return process.env.ZENITH_MODEL_FILE ?? MODEL_PATH;
}

interface PersistedModelData {
  current?: ModelSelection | null;
  recent?: ModelSelection[];
  favorite?: ModelSelection[];
}

function parseModel(value: string): ModelSelection {
  const [providerID, ...rest] = value.split('/');
  return { providerID, modelID: rest.join('/') };
}

function sameModel(a: ModelSelection, b: ModelSelection): boolean {
  return a.providerID === b.providerID && a.modelID === b.modelID;
}

function ensureDir(): void {
  try {
    const dir = path.dirname(getModelPath());
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  } catch {
    // Ignore mkdir errors (permissions, etc.)
  }
}

function readFromDisk(): PersistedModelData | null {
  try {
    ensureDir();
    const modelPath = getModelPath();
    if (fs.existsSync(modelPath)) {
      const raw = fs.readFileSync(modelPath, 'utf-8');
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') return parsed as PersistedModelData;
    }
  } catch {
    // Ignore read errors
  }
  return null;
}

function writeToDisk(data: PersistedModelData): void {
  try {
    ensureDir();
    const modelPath = getModelPath();
    const tmp = `${modelPath}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(data, null, 2), 'utf-8');
    fs.renameSync(tmp, modelPath);
  } catch {
    // Ignore write errors
  }
}

type ModelListener = (store: ModelStore) => void;

export class ModelStore {
  private currentModel: ModelSelection | null = null;
  private recentModels: ModelSelection[] = [];
  private favoriteModels: ModelSelection[] = [];
  private listeners: Set<ModelListener> = new Set();
  private loaded = false;

  public constructor() {
    const persisted = readFromDisk();
    if (persisted) {
      this.currentModel = persisted.current ?? null;
      this.recentModels = Array.isArray(persisted.recent) ? persisted.recent.slice(0, RECENT_LIMIT) : [];
      this.favoriteModels = Array.isArray(persisted.favorite) ? persisted.favorite : [];
    }
    this.loaded = true;
  }

  public static parse(value: string): ModelSelection {
    return parseModel(value);
  }

  public static isModelValid(value: string | null | undefined): value is string {
    if (!value) return false;
    const { providerID, modelID } = parseModel(value);
    return Boolean(providerID && modelID);
  }

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

  public set(sel: ModelSelection): ModelSelection {
    this.currentModel = sel;
    this.pushRecent(sel);
    this.persist();
    this.notify();
    return sel;
  }

  public clearCurrent(): void {
    this.currentModel = null;
    this.persist();
    this.notify();
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

  /** Cycle through recent models (newest first). Returns the next selection. */
  public cycle(reverse = false): ModelSelection | null {
    return this.cycleThrough(this.recentModels, reverse);
  }

  /** Cycle through favorite models. Returns the next selection. */
  public cycleFavorite(reverse = false): ModelSelection | null {
    return this.cycleThrough(this.favoriteModels, reverse);
  }

  private cycleThrough(list: ModelSelection[], reverse: boolean): ModelSelection | null {
    if (list.length === 0) return null;
    const idx = this.currentModel ? list.findIndex((item) => sameModel(item, this.currentModel!)) : -1;
    if (idx < 0) return list[0];
    const next = reverse ? (idx - 1 + list.length) % list.length : (idx + 1) % list.length;
    const sel = list[next];
    return sel;
  }

  /**
   * First-valid-model resolution chain (ported from opencode's local model store):
   * persisted current → active provider config model → first recent → provider
   * default model → first model in the provider catalog.
   */
  public getFirstValidModel(providers: ProviderInfo[]): ModelSelection | null {
    const candidates: ModelSelection[] = [];

    if (this.currentModel) candidates.push(this.currentModel);

    for (const provider of providers) {
      if (!provider.is_active) continue;
      if (provider.model) candidates.push({ providerID: provider.id, modelID: provider.model });
      break;
    }

    candidates.push(...this.recentModels);

    for (const provider of providers) {
      const models = Object.values(provider.models);
      const defaultValue = provider.model;
      if (defaultValue) candidates.push({ providerID: provider.id, modelID: defaultValue });
      for (const model of models) {
        candidates.push({ providerID: provider.id, modelID: model.id });
      }
      if (models.length === 0 && !provider.model) {
        const metaDefault = provider.model || '';
        if (metaDefault) candidates.push({ providerID: provider.id, modelID: metaDefault });
      }
    }

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

  private persist(): void {
    if (!this.loaded) return;
    writeToDisk({
      current: this.currentModel,
      recent: this.recentModels,
      favorite: this.favoriteModels,
    });
  }
}

export const modelStore = new ModelStore();
