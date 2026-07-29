import { fetchJson } from './fetchJson';
class TokenUsageService {
    stats = null;
    fetchPromise = null;
    async fetchStats(since, until) {
        const params = new URLSearchParams();
        if (since)
            params.set('since', since);
        if (until)
            params.set('until', until);
        const qs = params.toString();
        const url = `/usage/token-stats${qs ? `?${qs}` : ''}`;
        if (this.fetchPromise && !since && !until)
            return this.fetchPromise;
        const promise = this._doFetch(url);
        if (!since && !until) {
            this.fetchPromise = promise;
            try {
                this.stats = await this.fetchPromise;
                return this.stats;
            }
            finally {
                this.fetchPromise = null;
            }
        }
        return promise;
    }
    async _doFetch(url = '/usage/token-stats') {
        try {
            const data = await fetchJson(url);
            return data;
        }
        catch {
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
    async fetchCostSummary(period = 'all') {
        try {
            const data = await fetchJson(`/usage/cost-summary?period=${period}`);
            return data.data;
        }
        catch {
            return [];
        }
    }
    async fetchBudgetStatus(sessionId) {
        try {
            return await fetchJson(`/usage/budget/${sessionId}`);
        }
        catch {
            return { active: false, max_session_cost: 0, max_daily_cost: 0, max_monthly_cost: 0 };
        }
    }
    async upsertBudget(sessionId, maxSessionCost, maxDailyCost, maxMonthlyCost, active = true) {
        try {
            const result = await fetchJson('/usage/budget', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    max_session_cost: maxSessionCost,
                    max_daily_cost: maxDailyCost,
                    max_monthly_cost: maxMonthlyCost,
                    active,
                }),
            });
            return result.ok;
        }
        catch {
            return false;
        }
    }
    async fetchStepStats(sessionId) {
        try {
            const data = await fetchJson(`/usage/steps/${sessionId}`);
            return data.steps;
        }
        catch {
            return [];
        }
    }
    async fetchEfficiency(sessionId) {
        try {
            return await fetchJson(`/usage/efficiency/${sessionId}`);
        }
        catch {
            return null;
        }
    }
    getStats() {
        return this.stats;
    }
}
export const tokenUsageService = new TokenUsageService();
