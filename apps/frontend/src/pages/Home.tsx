import { useCallback, useEffect, useState } from 'react';
import UrlInput from '../components/UrlInput';
import MediaCard, { type StartOptions } from '../components/MediaCard';
import JobList from '../components/JobList';
import LoginCard from '../components/LoginCard';
import Spinner from '../components/Spinner';
import { ApiError, jobs as jobsApi } from '../api';
import { useAuth } from '../auth';
import { useJob } from '../hooks';
import { haptic } from '../telegram';
import type { JobOut } from '../types';

export default function Home() {
  const { user, loading: authLoading, isMiniApp } = useAuth();

  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [seed, setSeed] = useState<JobOut | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [starting, setStarting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [recent, setRecent] = useState<JobOut[]>([]);
  const [recentLoading, setRecentLoading] = useState(false);

  const { job, live, connected } = useJob(activeJobId, seed);

  const loadRecent = useCallback(async () => {
    if (!user) return;
    setRecentLoading(true);
    try {
      const list = await jobsApi.list(8);
      setRecent(list);
    } catch {
      /* non-fatal */
    } finally {
      setRecentLoading(false);
    }
  }, [user]);

  useEffect(() => {
    void loadRecent();
  }, [loadRecent]);

  // Refresh the recent list whenever the active job reaches a terminal state.
  useEffect(() => {
    if (job && (job.status === 'done' || job.status === 'failed' || job.status === 'cancelled')) {
      void loadRecent();
    }
  }, [job?.status, loadRecent]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleAnalyze = useCallback(async (url: string) => {
    setError(null);
    setAnalyzing(true);
    try {
      const created = await jobsApi.analyze(url);
      setSeed(created);
      setActiveJobId(created.id);
      haptic('success');
    } catch (err) {
      haptic('error');
      if (err instanceof ApiError) {
        setError(
          err.status === 429
            ? 'Слишком много запросов. Подождите немного и попробуйте снова.'
            : err.message,
        );
      } else {
        setError('Не удалось проанализировать ссылку. Проверьте её и попробуйте снова.');
      }
    } finally {
      setAnalyzing(false);
    }
  }, []);

  const handleStart = useCallback(
    async (opts: StartOptions) => {
      if (!activeJobId) return;
      setStarting(true);
      setError(null);
      try {
        await jobsApi.start(activeJobId, opts);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Не удалось начать загрузку.');
      } finally {
        setStarting(false);
      }
    },
    [activeJobId],
  );

  const handleCancel = useCallback(async () => {
    if (!activeJobId) return;
    setCancelling(true);
    try {
      await jobsApi.cancel(activeJobId);
    } catch {
      /* the poller will reflect the real state */
    } finally {
      setCancelling(false);
    }
  }, [activeJobId]);

  const handleRetry = useCallback(async () => {
    if (!activeJobId) return;
    setError(null);
    try {
      await jobsApi.retry(activeJobId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось повторить задание.');
    }
  }, [activeJobId]);

  const resetCurrent = useCallback(() => {
    setActiveJobId(null);
    setSeed(null);
    setError(null);
    void loadRecent();
  }, [loadRecent]);

  if (authLoading) {
    return (
      <div className="page-center">
        <Spinner label="Загрузка…" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="home">
        <section className="hero">
          <h1 className="hero-title">Скачивайте медиа из любимых площадок</h1>
          <p className="hero-sub">
            YouTube, VK, TikTok, Instagram, Vimeo и другие — видео, аудио и галереи в один клик.
          </p>
        </section>
        <LoginCard />
      </div>
    );
  }

  const showAnalyzing =
    Boolean(activeJobId) && (job === null || job.status === 'pending' || job.status === 'analyzing');

  return (
    <div className="home">
      <section className="hero">
        <h1 className="hero-title">Что скачиваем?</h1>
        <p className="hero-sub">Вставьте ссылку — мы подберём качество и формат.</p>
      </section>

      <UrlInput onSubmit={handleAnalyze} loading={analyzing} />

      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}

      {activeJobId && (
        <section className="current-job">
          <div className="current-job-head">
            <h2 className="section-title">Текущая ссылка</h2>
            <button type="button" className="btn btn-ghost btn-sm" onClick={resetCurrent}>
              Новая ссылка
            </button>
          </div>

          {showAnalyzing && !job?.formats.length ? (
            <div className="analyzing-card">
              <Spinner label="Анализируем ссылку и определяем доступные форматы…" />
            </div>
          ) : job ? (
            <MediaCard
              job={job}
              live={live}
              onStart={handleStart}
              onCancel={handleCancel}
              onRetry={handleRetry}
              starting={starting}
              cancelling={cancelling}
              connected={connected}
              isMiniApp={isMiniApp}
            />
          ) : null}
        </section>
      )}

      <section className="recent">
        <div className="recent-head">
          <h2 className="section-title">Недавние загрузки</h2>
          {recentLoading && <Spinner />}
        </div>
        <JobList
          jobs={recent}
          emptyText="Здесь появятся ваши загрузки."
          onOpen={(j) => {
            setSeed(j);
            setActiveJobId(j.id);
            window.scrollTo({ top: 0, behavior: 'smooth' });
          }}
        />
      </section>
    </div>
  );
}
