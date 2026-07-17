// Tiny typed fetch wrapper around the ShareTube backend.
// - Same-origin, prefix /api.
// - Cookie auth (credentials: 'include').
// - Telegram Mini App: X-Telegram-Init-Data header on every request.

import { getInitData } from './telegram';
import type {
  AdminDashboard,
  AdminJob,
  AdminSettings,
  AdminUser,
  AuditLogEntry,
  CookieProfile,
  JobOut,
  JobStatus,
  Me,
  ProxyCheckResult,
  ProxyProfile,
  TelegramAuthPayload,
  TelegramLoginResult,
  ToolVersions,
} from './types';

export const API_PREFIX = '/api';

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

export interface RequestOptions {
  method?: string;
  /** Object -> JSON body. Pass a string/FormData to send as-is. */
  body?: unknown;
  /** Extra query params appended to the URL. */
  query?: Record<string, string | number | boolean | null | undefined>;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

/** Build a full API path with an optional, properly-encoded query string. */
export function buildUrl(path: string, query?: RequestOptions['query']): string {
  const base = path.startsWith('/api') ? path : `${API_PREFIX}${path}`;
  if (!query) return base;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null) continue;
    params.append(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}

function extractError(status: number, payload: unknown): ApiError {
  // FastAPI returns either {detail: "..."} or {detail: {code, message}}.
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === 'string') return new ApiError(status, detail);
    if (detail && typeof detail === 'object') {
      const d = detail as { code?: string; message?: string };
      return new ApiError(status, d.message || `Ошибка ${status}`, d.code);
    }
  }
  return new ApiError(status, `Ошибка ${status}`);
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = buildUrl(path, options.query);
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');

  const initData = getInitData();
  if (initData) headers.set('X-Telegram-Init-Data', initData);

  let body: BodyInit | undefined;
  if (options.body !== undefined && options.body !== null) {
    if (typeof options.body === 'string' || options.body instanceof FormData) {
      body = options.body as BodyInit;
    } else {
      body = JSON.stringify(options.body);
      if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    }
  }

  const res = await fetch(url, {
    method: options.method ?? (body ? 'POST' : 'GET'),
    headers,
    body,
    credentials: 'include',
    signal: options.signal,
  });

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) throw extractError(res.status, data);
  return data as T;
}

// ---------------- Auth ----------------

export const auth = {
  me: () => apiFetch<Me>('/auth/me'),
  telegramLogin: (payload: TelegramAuthPayload) =>
    apiFetch<TelegramLoginResult>('/auth/telegram', { method: 'POST', body: payload }),
  logout: () => apiFetch<{ ok: boolean }>('/auth/logout', { method: 'POST' }),
};

// ---------------- Jobs ----------------

export const jobs = {
  analyze: (url: string, confirmPlaylist = false) =>
    apiFetch<JobOut>('/analyze', {
      method: 'POST',
      body: { url, confirm_playlist: confirmPlaylist },
    }),
  get: (id: string) => apiFetch<JobOut>(`/jobs/${encodeURIComponent(id)}`),
  list: (limit = 20) => apiFetch<JobOut[]>('/jobs', { query: { limit } }),
  start: (
    id: string,
    opts: { format_id?: number; format_label?: string; deliver_to_telegram?: boolean } = {},
  ) => apiFetch<JobOut>(`/jobs/${encodeURIComponent(id)}/start`, { method: 'POST', body: opts }),
  cancel: (id: string) =>
    apiFetch<JobOut>(`/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST' }),
  retry: (id: string) =>
    apiFetch<JobOut>(`/jobs/${encodeURIComponent(id)}/retry`, { method: 'POST' }),
  /** SSE endpoint URL for a job's progress stream. */
  eventsUrl: (id: string) => `${API_PREFIX}/jobs/${encodeURIComponent(id)}/events`,
};

// ---------------- Admin ----------------

export const admin = {
  login: (payload: TelegramAuthPayload) =>
    apiFetch<{ ok: boolean }>('/admin/login', { method: 'POST', body: payload }),
  logout: () => apiFetch<{ ok: boolean }>('/admin/logout', { method: 'POST' }),

  dashboard: () => apiFetch<AdminDashboard>('/admin/dashboard'),

  jobs: (params: { status?: string; limit?: number } = {}) =>
    apiFetch<AdminJob[]>('/admin/jobs', { query: params }),
  cancelJob: (id: string) =>
    apiFetch<{ ok: boolean }>(`/admin/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST' }),
  deleteJobFile: (id: string) =>
    apiFetch<{ ok: boolean }>(`/admin/jobs/${encodeURIComponent(id)}/file`, { method: 'DELETE' }),

  users: () => apiFetch<AdminUser[]>('/admin/users'),
  blockUser: (id: number, blocked: boolean) =>
    apiFetch<{ ok: boolean }>(`/admin/users/${id}/block`, {
      method: 'POST',
      query: { blocked },
    }),
  setQuota: (id: number, dailyJobs: number | null) =>
    apiFetch<{ ok: boolean }>(`/admin/users/${id}/quota`, {
      method: 'POST',
      query: dailyJobs === null ? {} : { daily_jobs: dailyJobs },
    }),

  proxies: () => apiFetch<ProxyProfile[]>('/admin/proxies'),
  createHttpProxy: (body: {
    name: string;
    url: string;
    is_primary: boolean;
    is_backup: boolean;
    priority: number;
    bound_sources?: string;
  }) => apiFetch<ProxyProfile>('/admin/proxies/http', { method: 'POST', body }),
  createXrayProxy: (body: {
    name: string;
    config_or_uri: string;
    is_primary: boolean;
    is_backup: boolean;
    priority: number;
  }) => apiFetch<ProxyProfile>('/admin/proxies/xray', { method: 'POST', body }),
  checkProxy: (id: number) =>
    apiFetch<ProxyCheckResult>(`/admin/proxies/${id}/check`, { method: 'POST' }),
  toggleProxy: (id: number, enabled: boolean) =>
    apiFetch<{ ok: boolean }>(`/admin/proxies/${id}/toggle`, {
      method: 'POST',
      query: { enabled },
    }),
  setProxyRole: (id: number, primary: boolean, backup: boolean) =>
    apiFetch<{ ok: boolean }>(`/admin/proxies/${id}/role`, {
      method: 'POST',
      query: { primary, backup },
    }),
  deleteProxy: (id: number) =>
    apiFetch<{ ok: boolean }>(`/admin/proxies/${id}`, { method: 'DELETE' }),

  cookies: () => apiFetch<CookieProfile[]>('/admin/cookies'),
  upsertCookie: (source: string, name: string, cookieData: string) =>
    apiFetch<{ ok: boolean; id: number }>('/admin/cookies', {
      method: 'POST',
      query: { source, name, cookie_data: cookieData },
    }),

  versions: () => apiFetch<ToolVersions>('/admin/versions'),
  settings: () => apiFetch<AdminSettings>('/admin/settings'),
  logs: (limit = 100) => apiFetch<AuditLogEntry[]>('/admin/logs', { query: { limit } }),
  cleanup: () =>
    apiFetch<{ expired: number; freed_bytes: number; stale_tmp: number }>('/admin/cleanup', {
      method: 'POST',
    }),
};

/** Statuses at which a job is finished (no more SSE updates expected). */
export const TERMINAL_STATUSES: ReadonlySet<JobStatus> = new Set<JobStatus>([
  'done',
  'failed',
  'cancelled',
]);

/** Statuses at which a job is actively working. */
export const ACTIVE_STATUSES: ReadonlySet<JobStatus> = new Set<JobStatus>([
  'analyzing',
  'queued',
  'downloading',
  'merging',
  'converting',
  'uploading',
]);
