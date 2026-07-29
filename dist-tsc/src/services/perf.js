/**
 * Simple performance benchmarking utilities.
 *
 * Usage:
 *   import { PerfTimer, measureRender } from '../services/perf';
 *   const timer = new PerfTimer('my-operation');
 *   timer.start();
 *   // ... do work
 *   timer.stop(); // prints to console
 */
export class PerfTimer {
    label;
    t0 = 0;
    marks = [];
    constructor(label) {
        this.label = label;
    }
    start() {
        this.t0 = performance.now();
        this.marks = [];
    }
    mark(label) {
        this.marks.push({ label, time: performance.now() - this.t0 });
    }
    stop() {
        const elapsed = performance.now() - this.t0;
        const marks = this.marks.map((m) => `  ${m.label}: ${m.time.toFixed(2)}ms`).join('\n');
        console.log(`[perf] ${this.label}: ${elapsed.toFixed(2)}ms${marks ? `\n${marks}` : ''}`);
        return elapsed;
    }
    elapsed() {
        return performance.now() - this.t0;
    }
}
export function benchmark(name, fn, iterations = 100) {
    const times = [];
    for (let i = 0; i < iterations; i++) {
        const t0 = performance.now();
        fn();
        times.push(performance.now() - t0);
    }
    times.sort((a, b) => a - b);
    const totalMs = times.reduce((s, t) => s + t, 0);
    const result = {
        iterations,
        totalMs,
        avgMs: totalMs / iterations,
        minMs: times[0],
        maxMs: times[iterations - 1],
        p50Ms: times[Math.floor(iterations * 0.5)],
        p95Ms: times[Math.floor(iterations * 0.95)],
        p99Ms: times[Math.floor(iterations * 0.99)],
    };
    console.log(`[bench] ${name} (${iterations} iterations):`);
    console.log(`  avg: ${result.avgMs.toFixed(2)}ms | p50: ${result.p50Ms.toFixed(2)}ms | p95: ${result.p95Ms.toFixed(2)}ms`);
    console.log(`  min: ${result.minMs.toFixed(2)}ms | max: ${result.maxMs.toFixed(2)}ms`);
    return result;
}
export function measureRender(label) {
    const timer = new PerfTimer(label);
    timer.start();
    return {
        stop: () => timer.stop(),
    };
}
