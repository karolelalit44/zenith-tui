import { render } from 'ink-testing-library';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ComposerFooter } from '../src/components/Input/ComposerFooter';
import { computeFooterLayout } from '../src/utils/footerLayout';

const nvidiaModel = 'nvidia/nemotron-3-ultra-550b-a55b';

const cleanups: Array<() => void> = [];

function mount(node: React.ReactNode) {
  const app = render(node);
  cleanups.push(app.unmount);
  return app;
}

function stubColumns(columns: number) {
  const original = Object.getOwnPropertyDescriptor(process.stdout, 'columns');
  Object.defineProperty(process.stdout, 'columns', { configurable: true, get: () => columns });
  return () => {
    if (original) Object.defineProperty(process.stdout, 'columns', original);
    else delete (process.stdout as { columns?: number }).columns;
  };
}

describe('ComposerFooter', () => {
  afterEach(() => {
    for (const unmount of cleanups.splice(0)) unmount();
    vi.unstubAllGlobals();
  });

  it('truncates the model chip instead of wrapping when content exceeds the width', () => {
    const restore = stubColumns(100);

    const app = mount(
      <ComposerFooter
        mode="build"
        modelFallback="nvidia/nemotron-3-ultra-550b-a55b"
        providerName="NVIDIA AI"
        dir=".../code/zenith-frontend-tui"
        branch="fix/ser-tu-communication-n-separations"
        effectiveMaxTokens={131072}
      />,
    );

    const frame = app.lastFrame();
    expect(frame).not.toContain('nvidia/nvidia/');
    expect(frame).toContain('◇ nvidia/');
    restore();
  });

  it('renders a single-line footer at 100 columns (no wrapped continuation line)', () => {
    const restore = stubColumns(100);

    const app = mount(
      <ComposerFooter
        mode="build"
        modelFallback="nvidia/nemotron-3-ultra-550b-a55b"
        providerName="NVIDIA AI"
        dir=".../code/zenith-frontend-tui"
        branch="fix/ser-tu-communication-n-separations"
        effectiveMaxTokens={131072}
      />,
    );

    const frame = app.lastFrame();
    const lines = frame.split('\n').filter((line) => line.length > 0);
    expect(lines).toHaveLength(1);
    restore();
  });

  it('renders cumulative run usage and composed-context gauge as separate figures', () => {
    const restore = stubColumns(120);

    const app = mount(
      <ComposerFooter
        mode="build"
        modelFallback="nvidia/nemotron-3-ultra-550b-a55b"
        providerName="NVIDIA AI"
        dir=".../code/zenith-frontend-tui"
        branch="fix/ser-tu-communication-n-separations"
        effectiveMaxTokens={200_000}
        runTokens={12_400}
        contextPercent={39}
      />,
    );

    const frame = app.lastFrame();
    // The footer count is cumulative run/API usage and context percent...
    expect(frame).toContain('12.4K (39.0%)');
    expect(frame).not.toContain('78.8K');
    expect(frame).not.toContain('RUN');
    expect(frame).not.toContain('CTX');
    expect(frame).not.toContain('░');
    restore();
  });

  it('renders exact run usage and context window without a tilde', () => {
    const restore = stubColumns(120);

    const app = mount(
      <ComposerFooter
        mode="build"
        modelFallback="nvidia/nemotron-3-ultra-550b-a55b"
        providerName="NVIDIA AI"
        dir=".../code/zenith-frontend-tui"
        branch="fix/ser-tu-communication-n-separations"
        effectiveMaxTokens={200_000}
        runTokens={12_400}
        runEstimated={true}
        contextPercent={39}
        windowEstimated={true}
      />,
    );

    const frame = app.lastFrame();
    expect(frame).toContain('12.4K (39.0%)');
    expect(frame).not.toContain('~');
    expect(frame).not.toContain('░');
    restore();
  });

  it('renders no running status and no context indicator', () => {
    const restore = stubColumns(120);

    const app = mount(
      <ComposerFooter
        mode="build"
        modelFallback="nvidia/nemotron-3-ultra-550b-a55b"
        providerName="NVIDIA AI"
        dir=".../code/zenith-frontend-tui"
        branch="fix/ser-tu-communication-n-separations"
        effectiveMaxTokens={131072}
      />,
    );

    const frame = app.lastFrame();
    expect(frame).not.toContain('Esc cancel');
    expect(frame).not.toContain('Context');
    expect(frame).not.toContain('⏎');
    expect(frame).not.toContain('Compacting');
    restore();
  });

  it('computeFooterLayout never exceeds the available width', () => {
    for (const columns of [60, 80, 100, 120, 160]) {
      const layout = computeFooterLayout({
        columns,
        mode: 'build',
        chip: nvidiaModel,
        providerName: 'NVIDIA AI',
        dir: '.../code/zenith-frontend-tui',
        branch: 'fix/ser-tu-communication-n-separations',
        effectiveMaxTokens: 131072,
      });

      const contentWidth = columns - 4;
      const renderedWidth =
        layout.modeLabel.length +
        2 +
        layout.chip.length +
        layout.provider.length +
        (layout.dirText ? layout.dirText.length : 0) +
        (layout.branchText ? layout.branchText.length + 1 : 0) +
        (layout.gauge ? layout.gauge.length + 1 : 0) +
        layout.tokenUsage.length;

      expect(renderedWidth).toBeLessThanOrEqual(contentWidth);
    }
  });

  it('computeFooterLayout budgets the composed-context gauge width', () => {
    for (const columns of [80, 100, 120, 160]) {
      const layout = computeFooterLayout({
        columns,
        mode: 'build',
        chip: nvidiaModel,
        providerName: 'NVIDIA AI',
        dir: '.../code/zenith-frontend-tui',
        branch: 'fix/ser-tu-communication-n-separations',
        effectiveMaxTokens: 128_000,
        runTokens: 12_400,
        runEstimated: true,
        contextPercent: 100,
        windowEstimated: true,
      });

      const contentWidth = columns - 4;
      const renderedWidth =
        layout.modeLabel.length +
        2 +
        layout.chip.length +
        layout.provider.length +
        (layout.dirText ? layout.dirText.length : 0) +
        (layout.branchText ? layout.branchText.length + 1 : 0) +
        (layout.gauge ? layout.gauge.length + 1 : 0) +
        layout.tokenUsage.length;

      expect(renderedWidth).toBeLessThanOrEqual(contentWidth);
    }
  });

  it('computeFooterLayout leaves tokenUsage empty when no token inputs are provided', () => {
    for (const columns of [60, 80, 120]) {
      const layout = computeFooterLayout({
        columns,
        mode: 'build',
        chip: nvidiaModel,
        providerName: 'NVIDIA AI',
        dir: '.../code/zenith-frontend-tui',
        branch: 'fix/ser-tu-communication-n-separations',
      });

      expect(layout.tokenUsage).toBe('');
      expect(layout.gauge).toBe('');
      expect(layout.showGauge).toBe(false);
    }
  });
});
