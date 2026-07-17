import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiFetch, buildUrl, jobs } from '../api';

// Minimal fetch Response stand-in for the wrapper (it only reads status + text()).
function makeResponse(body: unknown, init: { status?: number; ok?: boolean } = {}) {
  const status = init.status ?? 200;
  const text = typeof body === 'string' ? body : JSON.stringify(body);
  return {
    ok: init.ok ?? (status >= 200 && status < 300),
    status,
    text: () => Promise.resolve(text),
  } as unknown as Response;
}

type FetchMock = ReturnType<typeof vi.fn>;

function setInitData(value: string | undefined) {
  if (value === undefined) {
    (window as unknown as { Telegram?: unknown }).Telegram = undefined;
  } else {
    (window as unknown as { Telegram?: { WebApp: { initData: string } } }).Telegram = {
      WebApp: { initData: value },
    };
  }
}

describe('buildUrl', () => {
  it('prefixes /api when missing', () => {
    expect(buildUrl('/auth/me')).toBe('/api/auth/me');
  });

  it('does not double-prefix an explicit /api path', () => {
    expect(buildUrl('/api/jobs/x/events')).toBe('/api/jobs/x/events');
  });

  it('encodes query params and skips null/undefined', () => {
    const url = buildUrl('/jobs', { limit: 20, status: 'failed', empty: null, gone: undefined });
    expect(url).toBe('/api/jobs?limit=20&status=failed');
  });
});

describe('apiFetch', () => {
  let fetchMock: FetchMock;

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue(makeResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);
    setInitData(undefined);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    setInitData(undefined);
  });

  it('calls the correct URL with credentials included', async () => {
    await apiFetch('/auth/me');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/auth/me');
    expect(options.credentials).toBe('include');
    expect(options.method).toBe('GET');
  });

  it('does NOT send the Telegram header on a plain website', async () => {
    await apiFetch('/auth/me');
    const [, options] = fetchMock.mock.calls[0];
    const headers = options.headers as Headers;
    expect(headers.get('X-Telegram-Init-Data')).toBeNull();
  });

  it('sends X-Telegram-Init-Data when running as a Mini App', async () => {
    setInitData('query_id=AAA&user=%7B%22id%22%3A1%7D&hash=deadbeef');
    await apiFetch('/auth/me');
    const [, options] = fetchMock.mock.calls[0];
    const headers = options.headers as Headers;
    expect(headers.get('X-Telegram-Init-Data')).toBe(
      'query_id=AAA&user=%7B%22id%22%3A1%7D&hash=deadbeef',
    );
  });

  it('serializes an object body as JSON and sets Content-Type + POST default', async () => {
    await apiFetch('/analyze', { body: { url: 'https://youtu.be/x', confirm_playlist: false } });
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/analyze');
    expect(options.method).toBe('POST');
    expect(options.body).toBe(JSON.stringify({ url: 'https://youtu.be/x', confirm_playlist: false }));
    const headers = options.headers as Headers;
    expect(headers.get('Content-Type')).toBe('application/json');
  });

  it('appends encoded query params', async () => {
    await apiFetch('/jobs', { query: { limit: 5 } });
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/jobs?limit=5');
  });

  it('parses {detail:{code,message}} errors into ApiError', async () => {
    fetchMock.mockResolvedValueOnce(
      makeResponse({ detail: { code: 'bad_state', message: 'Нельзя запустить' } }, { status: 409 }),
    );
    await expect(apiFetch('/jobs/1/start', { method: 'POST' })).rejects.toMatchObject({
      status: 409,
      code: 'bad_state',
      message: 'Нельзя запустить',
    });
  });

  it('parses string detail errors', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse({ detail: 'not found' }, { status: 404 }));
    const err = await apiFetch('/jobs/missing').catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(404);
    expect(err.message).toBe('not found');
  });

  it('returns parsed JSON on success', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse({ id: 'job-1', status: 'analyzed' }));
    const data = await apiFetch<{ id: string; status: string }>('/jobs/job-1');
    expect(data).toEqual({ id: 'job-1', status: 'analyzed' });
  });
});

describe('jobs.eventsUrl', () => {
  it('builds the SSE endpoint URL with an encoded id', () => {
    expect(jobs.eventsUrl('abc 1')).toBe('/api/jobs/abc%201/events');
  });
});
