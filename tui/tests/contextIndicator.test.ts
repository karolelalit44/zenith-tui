import { describe, expect, it } from 'vitest';
import { contextLabel, contextLevelForFraction, contextLevelForPercent } from '../src/config/context';

describe('context level thresholds', () => {
  it('returns neutral below attention threshold', () => {
    expect(contextLevelForPercent(0)).toBe('neutral');
    expect(contextLevelForPercent(50)).toBe('neutral');
    expect(contextLevelForPercent(69)).toBe('neutral');
  });

  it('returns attention between 70 and 84', () => {
    expect(contextLevelForPercent(70)).toBe('attention');
    expect(contextLevelForPercent(75)).toBe('attention');
    expect(contextLevelForPercent(84)).toBe('attention');
  });

  it('returns preparing between 85 and 94', () => {
    expect(contextLevelForPercent(85)).toBe('preparing');
    expect(contextLevelForPercent(90)).toBe('preparing');
    expect(contextLevelForPercent(94)).toBe('preparing');
  });

  it('returns required at 95+', () => {
    expect(contextLevelForPercent(95)).toBe('required');
    expect(contextLevelForPercent(100)).toBe('required');
  });

  it('contextLabel returns correct suffix for each level', () => {
    expect(contextLabel('neutral')).toBeNull();
    expect(contextLabel('attention')).toBeNull();
    expect(contextLabel('preparing')).toBe('Preparing');
    expect(contextLabel('required')).toBe('Compaction required');
  });

  it('contextLevelForFraction matches percent thresholds', () => {
    expect(contextLevelForFraction(0.7)).toBe('attention');
    expect(contextLevelForFraction(0.85)).toBe('preparing');
    expect(contextLevelForFraction(0.95)).toBe('required');
  });
});
