import { describe, expect, it, vi } from 'vitest';
import * as envModule from '../src/config/environment';
import {
  ZENITH_BACKEND_URL,
  ZENITH_CONTEXT_ATTENTION,
  ZENITH_CONTEXT_PREPARING,
  ZENITH_CONTEXT_REQUIRED,
  ZENITH_GIT_CACHE_TTL,
  ZENITH_GIT_TIMEOUT,
  ZENITH_STARTUP_RETRIES,
  ZENITH_STARTUP_RETRY_DELAY_MS,
  ZENITH_STARTUP_RETRY_MAX_DELAY_MS,
  ZENITH_WS_MAX_RECONNECT,
  ZENITH_WS_PATH,
  ZENITH_WS_RECONNECT_DELAY,
  ZENITH_WS_RECONNECT_WAIT_MS,
  ZENITH_WS_RPC_TIMEOUT,
  ZENITH_WS_STALE_TIMEOUT_MS,
  envBool,
  envFloat,
  envInt,
  envStr,
  readEnvironment,
} from '../src/config/environment';

describe('environment configuration', () => {
  it('defines all required environment keys as direct constants', () => {
    expect(ZENITH_BACKEND_URL).toBeDefined();
    expect(ZENITH_WS_PATH).toBeDefined();
    expect(ZENITH_WS_RPC_TIMEOUT).toBeGreaterThan(0);
    expect(ZENITH_WS_MAX_RECONNECT).toBeGreaterThanOrEqual(0);
    expect(ZENITH_WS_RECONNECT_DELAY).toBeGreaterThan(0);
    expect(ZENITH_WS_STALE_TIMEOUT_MS).toBeGreaterThan(0);
    expect(ZENITH_WS_RECONNECT_WAIT_MS).toBeGreaterThan(0);
    expect(ZENITH_GIT_CACHE_TTL).toBeGreaterThan(0);
    expect(ZENITH_GIT_TIMEOUT).toBeGreaterThan(0);
    expect(ZENITH_STARTUP_RETRIES).toBeGreaterThanOrEqual(0);
    expect(ZENITH_STARTUP_RETRY_DELAY_MS).toBeGreaterThan(0);
    expect(ZENITH_STARTUP_RETRY_MAX_DELAY_MS).toBeGreaterThan(0);
    expect(ZENITH_CONTEXT_ATTENTION).toBeGreaterThan(0);
    expect(ZENITH_CONTEXT_PREPARING).toBeGreaterThan(0);
    expect(ZENITH_CONTEXT_REQUIRED).toBeGreaterThan(0);
  });

  it('envStr returns explicit value from constants', () => {
    expect(envStr('ZENITH_BACKEND_URL')).toBe(ZENITH_BACKEND_URL);
  });

  it('envInt returns parsed integer from constants', () => {
    expect(envInt('ZENITH_GIT_TIMEOUT')).toBe(ZENITH_GIT_TIMEOUT);
  });

  it('envFloat returns parsed float from constants', () => {
    expect(envFloat('ZENITH_CONTEXT_ATTENTION')).toBe(ZENITH_CONTEXT_ATTENTION);
  });

  it('envBool returns boolean from process.env', () => {
    vi.stubEnv('TEST_BOOL_FLAG', 'true');
    expect(envBool('TEST_BOOL_FLAG')).toBe(true);
    vi.stubEnv('TEST_BOOL_FLAG', '0');
    expect(envBool('TEST_BOOL_FLAG')).toBe(false);
    vi.unstubAllEnvs();
  });

  it('throws when requesting an undefined key without fallbacks', () => {
    expect(() => envStr('UNKNOWN_KEY_NOT_IN_ENV')).toThrow(
      "Required environment variable 'UNKNOWN_KEY_NOT_IN_ENV' is not defined",
    );
  });

  it('throws on invalid numeric conversions', () => {
    vi.stubEnv('TEST_INVALID_NUM', 'not-a-number');
    expect(() => envInt('TEST_INVALID_NUM')).toThrow('must be a valid number');
    expect(() => envFloat('TEST_INVALID_NUM')).toThrow('must be a valid number');
    vi.unstubAllEnvs();
  });

  it('ignores any fallback parameters passed to getter functions', () => {
    // If a secondary/fallback value is passed as 2nd param, it must be ignored
    // @ts-expect-error test fallback ignore
    const val = envStr('ZENITH_BACKEND_URL', 'http://fallback.invalid');
    expect(val).toBe(ZENITH_BACKEND_URL);
  });

  it('does not export readDotEnv', () => {
    expect('readDotEnv' in envModule).toBe(false);
  });

  it('readEnvironment returns full environment map without .env files', () => {
    const env = readEnvironment();
    expect(env.ZENITH_BACKEND_URL).toBe(ZENITH_BACKEND_URL);
  });
});
