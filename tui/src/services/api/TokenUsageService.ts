import { BaseApiService } from './BaseApiService';

export interface ModelTokenStats {
  provider: string;
  model: string;
  request_count: number;
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  total_cache_read: number;
  total_cache_creation: number;
  context_window: number;
}

export interface TokenUsageTotals {
  total_requests: number;
  grand_total_tokens: number;
  grand_total_input: number;
  grand_total_output: number;
  grand_total_prompt: number;
  grand_total_completion: number;
  grand_total_cost_usd: number;
  grand_total_cache_read: number;
  grand_total_cache_creation: number;
  unique_models: number;
}

export interface TokenUsageStats {
  models: ModelTokenStats[];
  totals: TokenUsageTotals;
}

export interface CostSummaryItem {
  provider: string;
  model: string;
  requests: number;
  total_tokens: number;
  total_cost: number;
  total_input: number;
  total_output: number;
}

export interface StepTokenUsage {
  id?: string;
  session_id: string;
  step_index: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
  model: string;
  provider: string;
}

export interface EfficiencyMetrics {
  total_tokens_consumed: number;
  total_cost_usd: number;
  final_context_used: number;
  waste_ratio: number;
  summarization_count: number;
  average_context_utilization: number;
}

class TokenUsageService extends BaseApiService {
  private stats: TokenUsageStats | null = null;
  private fetchPromise: Promise<TokenUsageStats> | null = null;

  async fetchStats(since?: string, until?: string): Promise<TokenUsageStats> {
    const params = new URLSearchParams();
    if (since) params.set('since', since);
    if (until) params.set('until', until);
    const qs = params.toString();
    const url = `/usage/token-stats${qs ? `?${qs}` : ''}`;
    if (this.fetchPromise && !since && !until) return this.fetchPromise;
    const promise = this._doFetch(url);
    if (!since && !until) {
      this.fetchPromise = promise;
      try {
        this.stats = await this.fetchPromise;
        return this.stats;
      } finally {
        this.fetchPromise = null;
      }
    }
    return promise;
  }

  private async _doFetch(url: string = '/usage/token-stats'): Promise<TokenUsageStats> {
    try {
      const data = await this.get<TokenUsageStats>(url);
      return data;
    } catch {
      return {
        models: [],
        totals: {
          total_requests: 0,
          grand_total_tokens: 0,
          grand_total_input: 0,
          grand_total_output: 0,
          grand_total_prompt: 0,
          grand_total_completion: 0,
          grand_total_cost_usd: 0,
          grand_total_cache_read: 0,
          grand_total_cache_creation: 0,
          unique_models: 0,
        },
      };
    }
  }

  async fetchCostSummary(period: string = 'all'): Promise<CostSummaryItem[]> {
    try {
      const data = await this.get<{ data: CostSummaryItem[] }>(`/usage/cost-summary?period=${period}`);
      return data.data;
    } catch {
      return [];
    }
  }

  async fetchStepStats(sessionId: string): Promise<StepTokenUsage[]> {
    try {
      const data = await this.get<{ steps: StepTokenUsage[] }>(`/usage/steps/${sessionId}`);
      return data.steps;
    } catch {
      return [];
    }
  }

  async fetchEfficiency(sessionId: string): Promise<EfficiencyMetrics | null> {
    try {
      return await this.get<EfficiencyMetrics>(`/usage/efficiency/${sessionId}`);
    } catch {
      return null;
    }
  }

  getStats(): TokenUsageStats | null {
    return this.stats;
  }
}

export const tokenUsageService = new TokenUsageService();
