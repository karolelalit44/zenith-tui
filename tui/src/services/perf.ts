export class PerfTimer {
  private label: string;
  private t0 = 0;
  private marks: { label: string; time: number }[] = [];

  constructor(label: string) {
    this.label = label;
  }

  start(): void {
    this.t0 = performance.now();
    this.marks = [];
  }

  mark(label: string): void {
    this.marks.push({ label, time: performance.now() - this.t0 });
  }

  stop(): number {
    const elapsed = performance.now() - this.t0;
    const marks = this.marks.map((m) => `  ${m.label}: ${m.time.toFixed(2)}ms`).join('\n');
    console.log(`[perf] ${this.label}: ${elapsed.toFixed(2)}ms${marks ? `\n${marks}` : ''}`);
    return elapsed;
  }

  elapsed(): number {
    return performance.now() - this.t0;
  }
}

export interface BenchmarkResult {
  iterations: number;
  totalMs: number;
  avgMs: number;
  minMs: number;
  maxMs: number;
  p50Ms: number;
  p95Ms: number;
  p99Ms: number;
}

export function benchmark(name: string, fn: () => void, iterations = 100): BenchmarkResult {
  const times: number[] = [];
  for (let i = 0; i < iterations; i++) {
    const t0 = performance.now();
    fn();
    times.push(performance.now() - t0);
  }
  times.sort((a, b) => a - b);

  const totalMs = times.reduce((s, t) => s + t, 0);
  const result: BenchmarkResult = {
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
  console.log(
    `  avg: ${result.avgMs.toFixed(2)}ms | p50: ${result.p50Ms.toFixed(2)}ms | p95: ${result.p95Ms.toFixed(2)}ms`,
  );
  console.log(`  min: ${result.minMs.toFixed(2)}ms | max: ${result.maxMs.toFixed(2)}ms`);

  return result;
}

export function measureRender(label: string): { stop: () => number } {
  const timer = new PerfTimer(label);
  timer.start();
  return {
    stop: () => timer.stop(),
  };
}
