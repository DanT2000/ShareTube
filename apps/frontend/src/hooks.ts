// Reusable hooks: live job progress via SSE, and lightweight polling.
import { useEffect, useRef, useState } from 'react';
import { jobs as jobsApi, TERMINAL_STATUSES } from './api';
import type { JobOut, JobProgressEvent } from './types';

/**
 * Subscribe to a job's Server-Sent Events progress stream.
 *
 * EventSource is used with `withCredentials` so the session cookie is sent.
 * Note: EventSource cannot set custom headers, so Telegram Mini App auth over
 * SSE relies on the cookie set at login (initData header can't ride along here).
 * The stream auto-closes on a terminal status; we also expose a manual close.
 */
export function useJobEvents(
  jobId: string | null,
  onEvent: (ev: JobProgressEvent) => void,
): { connected: boolean; error: boolean } {
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(false);
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    if (!jobId) return;
    setError(false);
    const es = new EventSource(jobsApi.eventsUrl(jobId), { withCredentials: true });

    es.onopen = () => {
      setConnected(true);
      setError(false);
    };

    es.onmessage = (msg) => {
      if (!msg.data || msg.data.startsWith(':')) return;
      try {
        const parsed = JSON.parse(msg.data) as JobProgressEvent;
        handlerRef.current(parsed);
        if (parsed.status && TERMINAL_STATUSES.has(parsed.status)) {
          es.close();
          setConnected(false);
        }
      } catch {
        /* ignore keepalive / malformed lines */
      }
    };

    es.onerror = () => {
      // Browser auto-reconnects; flag the transient error but keep the source.
      setConnected(false);
      setError(true);
    };

    return () => {
      es.close();
      setConnected(false);
    };
  }, [jobId]);

  return { connected, error };
}

/**
 * Poll a fetcher on an interval. Pauses when `enabled` is false. Returns the
 * latest data, loading flag, error, and a manual refetch.
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
  enabled = true,
): { data: T | null; loading: boolean; error: Error | null; refetch: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    const run = async () => {
      try {
        const result = await fetcherRef.current();
        if (alive) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (alive) setError(err instanceof Error ? err : new Error(String(err)));
      } finally {
        if (alive) setLoading(false);
      }
    };
    void run();

    if (!enabled || intervalMs <= 0) return () => {
      alive = false;
    };
    const id = window.setInterval(run, intervalMs);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [intervalMs, enabled, tick]);

  return { data, loading, error, refetch: () => setTick((t) => t + 1) };
}

/** True while any of the given jobs is still active (drives auto-refresh). */
export function hasActiveJobs(list: JobOut[] | null): boolean {
  if (!list) return false;
  return list.some((j) => !TERMINAL_STATUSES.has(j.status));
}

/**
 * Track a single job through its whole lifecycle.
 *
 * - Polls GET /jobs/{id} while the job is non-terminal — this is the
 *   authoritative source for status, available formats and download_url, and
 *   works over Telegram Mini App header auth (unlike EventSource).
 * - Subscribes to SSE for smooth, high-frequency progress numbers in between
 *   polls; on a terminal event it forces an immediate refetch.
 *
 * `seed` (e.g. the JobOut returned by /analyze) is shown instantly so the UI
 * doesn't flash empty while the first poll is in flight.
 */
export function useJob(
  jobId: string | null,
  seed?: JobOut | null,
): { job: JobOut | null; live: JobProgressEvent | null; connected: boolean } {
  const [job, setJob] = useState<JobOut | null>(null);
  const [live, setLive] = useState<JobProgressEvent | null>(null);
  const seedRef = useRef(seed);
  seedRef.current = seed;

  useEffect(() => {
    setLive(null);
    if (!jobId) {
      setJob(null);
      return;
    }
    if (seedRef.current && seedRef.current.id === jobId) setJob(seedRef.current);

    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const fresh = await jobsApi.get(jobId);
        if (!alive) return;
        setJob(fresh);
        if (!TERMINAL_STATUSES.has(fresh.status)) timer = window.setTimeout(tick, 1500);
      } catch {
        if (alive) timer = window.setTimeout(tick, 3000);
      }
    };
    void tick();

    return () => {
      alive = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [jobId]);

  const active = job ? !TERMINAL_STATUSES.has(job.status) : Boolean(jobId);
  const { connected } = useJobEvents(active ? jobId : null, (ev) => {
    setLive(ev);
    if (jobId && TERMINAL_STATUSES.has(ev.status)) {
      jobsApi
        .get(jobId)
        .then((fresh) => setJob(fresh))
        .catch(() => undefined);
    }
  });

  return { job, live, connected };
}
