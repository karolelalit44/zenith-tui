import { render } from 'ink-testing-library';
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ComposerFooter } from '../src/components/Input/ComposerFooter';
import { modelStore } from '../src/services/providers/ModelStore';
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

  function seedModel() {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{}', { status: 200 })),
    );
    modelStore.set({ providerID: 'nvidia', modelID: nvidiaModel });
  }

  it('truncates the model chip instead of wrapping when content exceeds the width', () => {
    const restore = stubColumns(100);
    seedModel();

    const app = mount(
      <ComposerFooter
        mode="build"
        modelFallback="nvidia/nemotron-3-ultra-550b-a55b"
        providerName="NVIDIA AI"
        dir=".../code/zenith-frontend-tui"
        branch="fix/ser-tu-communication-n-separations"
        totalTokens={10}
        effectiveMaxTokens={131072}
        running={false}
        disabled={false}
        inputEmpty
        tokenScope="session"
      />,
    );

    const frame = app.lastFrame();
    expect(frame).not.toContain('nvidia/nvidia/');
    expect(frame).toContain('◇ nvidia/');
    expect(frame).toContain('0.0K');
    restore();
  });

  it('renders a single-line footer at 100 columns (no wrapped continuation line)', () => {
    const restore = stubColumns(100);
    seedModel();

    const app = mount(
      <ComposerFooter
        mode="build"
        modelFallback="nvidia/nemotron-3-ultra-550b-a55b"
        providerName="NVIDIA AI"
        dir=".../code/zenith-frontend-tui"
        branch="fix/ser-tu-communication-n-separations"
        totalTokens={10}
        effectiveMaxTokens={131072}
        running
        disabled={false}
        inputEmpty
        tokenScope="turn"
      />,
    );

    const frame = app.lastFrame();
    expect(frame).toContain('Esc cancel');
    expect(frame).toContain('0.0K');
    const lines = frame.split('\n').filter((line) => line.length > 0);
    expect(lines).toHaveLength(1);
    restore();
  });

  it('renders the on-open affordance when onContextOpen is provided', () => {
    const restore = stubColumns(120);
    seedModel();

    const app = mount(
      <ComposerFooter
        mode="build"
        modelFallback="nvidia/nemotron-3-ultra-550b-a55b"
        providerName="NVIDIA AI"
        dir=".../code/zenith-frontend-tui"
        branch="fix/ser-tu-communication-n-separations"
        totalTokens={10}
        effectiveMaxTokens={131072}
        running={false}
        disabled={false}
        inputEmpty
        tokenScope="session"
        onContextOpen={() => undefined}
      />,
    );

    const frame = app.lastFrame();
    expect(frame).toContain('⏎');
    restore();
  });

  it('omits the on-open affordance when onContextOpen is absent', () => {
    const restore = stubColumns(120);
    seedModel();

    const app = mount(
      <ComposerFooter
        mode="build"
        modelFallback="nvidia/nemotron-3-ultra-550b-a55b"
        providerName="NVIDIA AI"
        dir=".../code/zenith-frontend-tui"
        branch="fix/ser-tu-communication-n-separations"
        totalTokens={10}
        effectiveMaxTokens={131072}
        running={false}
        disabled={false}
        inputEmpty
        tokenScope="session"
      />,
    );

    expect(app.lastFrame()).not.toContain('⏎');
    restore();
  });

  it('shows the live before→after transition while compacting', () => {
    const restore = stubColumns(120);
    seedModel();

    const app = mount(
      <ComposerFooter
        mode="build"
        modelFallback="nvidia/nemotron-3-ultra-550b-a55b"
        providerName="NVIDIA AI"
        dir=".../code/zenith-frontend-tui"
        branch="fix/ser-tu-communication-n-separations"
        totalTokens={118_000}
        effectiveMaxTokens={128_000}
        running
        disabled={false}
        inputEmpty
        tokenScope="session"
        compaction={{
          kind: 'context_compaction_flow',
          id: 'evt_1',
          phase: 'compacting',
          beforeTokens: 118_000,
          afterTokens: 43_000,
          totalTokens: 128_000,
        }}
      />,
    );

    const frame = app.lastFrame();
    expect(frame).toContain('Compacting…');
    expect(frame).toContain('118.0k');
    expect(frame).toContain('43.0k');
    restore();
  });

  it('shows the model-reported after-context once compaction is ready', () => {
    const restore = stubColumns(120);
    seedModel();

    const app = mount(
      <ComposerFooter
        mode="build"
        modelFallback="nvidia/nemotron-3-ultra-550b-a55b"
        providerName="NVIDIA AI"
        dir=".../code/zenith-frontend-tui"
        branch="fix/ser-tu-communication-n-separations"
        totalTokens={118_000}
        effectiveMaxTokens={128_000}
        running={false}
        disabled={false}
        inputEmpty
        tokenScope="session"
        compaction={{
          kind: 'context_compaction_flow',
          id: 'evt_1',
          phase: 'ready',
          beforeTokens: 118_000,
          afterTokens: 43_000,
          totalTokens: 128_000,
          tokensSaved: 75_000,
        }}
      />,
    );

    expect(app.lastFrame()).toContain('Context 43.0k');
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
        totalTokens: 10,
        effectiveMaxTokens: 131072,
        running: true,
        disabled: false,
        inputEmpty: true,
        tokenScope: 'turn',
      });

      const contentWidth = columns - 4;
      const renderedWidth =
        layout.modeLabel.length +
        2 +
        layout.chip.length +
        layout.provider.length +
        (layout.dirText ? layout.dirText.length : 0) +
        (layout.branchText ? layout.branchText.length + 1 : 0) +
        layout.tokenUsage.length +
        11;

      expect(renderedWidth).toBeLessThanOrEqual(contentWidth);
    }
  });
});
