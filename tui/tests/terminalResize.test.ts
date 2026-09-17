import { describe, expect, it } from 'vitest';
import { subscribeTerminalResize } from '../src/hooks/useTerminalDimensions';

describe('terminal resize subscriptions', () => {
  it('shares one stdout listener across many subscribers', () => {
    const baseline = process.stdout.listenerCount('resize');
    const first = () => {};
    const second = () => {};

    const unsubscribeFirst = subscribeTerminalResize(first);
    const unsubscribeSecond = subscribeTerminalResize(second);

    expect(process.stdout.listenerCount('resize')).toBe(baseline + 1);

    unsubscribeFirst();
    expect(process.stdout.listenerCount('resize')).toBe(baseline + 1);

    unsubscribeSecond();
    expect(process.stdout.listenerCount('resize')).toBe(baseline);
  });
});
