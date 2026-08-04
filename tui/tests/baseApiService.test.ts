import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, BaseApiService } from '../src/services/api/BaseApiService';

class TestApi extends BaseApiService {
  getThing = () => this.get<{ id: number }>('/things/1');
  createThing = (name: string) => this.post<{ id: number }>('/things', { name });
  noContent = () => this.delete<void>('/things/1');
}

describe('BaseApiService', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('performs a GET and returns parsed JSON', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ id: 7 }), { status: 200 }));

    const api = new TestApi();
    await expect(api.getThing()).resolves.toEqual({ id: 7 });

    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe('http://localhost:8765/things/1');
    expect(init.method).toBe('GET');
    expect(init.headers).toMatchObject({ Accept: 'application/json' });
  });

  it('performs a POST and JSON-stringifies the body', async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ id: 8 }), { status: 201 }));

    const api = new TestApi();
    await expect(api.createThing('widget')).resolves.toEqual({ id: 8 });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ name: 'widget' });
  });

  it('treats a 204 response as empty output', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    const api = new TestApi();
    await expect(api.noContent()).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0][1].method).toBe('DELETE');
  });

  it('normalizes a non-ok HTTP response into an ApiError with its status', async () => {
    fetchMock.mockResolvedValue(new Response('boom', { status: 500, statusText: 'Internal Server Error' }));

    const api = new TestApi();
    const err = await api.getThing().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(500);
    expect((err as ApiError).message).toContain('500');
  });

  it('wraps network failures into an ApiError with code "network"', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));

    const api = new TestApi();
    const err = await api.getThing().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe('network');
  });
});
