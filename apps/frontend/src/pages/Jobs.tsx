import { useNavigate } from 'react-router-dom';
import JobList from '../components/JobList';
import LoginCard from '../components/LoginCard';
import Spinner from '../components/Spinner';
import { jobs as jobsApi, ACTIVE_STATUSES } from '../api';
import { useAuth } from '../auth';
import { hasActiveJobs, usePolling } from '../hooks';
import type { JobOut } from '../types';

export default function Jobs() {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();

  const { data, loading, error, refetch } = usePolling<JobOut[]>(
    () => jobsApi.list(30),
    3000,
    Boolean(user),
  );

  // Slow the poll down when nothing is active (usePolling keeps a fixed
  // interval, but re-render frequency is cheap; the request is small).
  const active = (data ?? []).filter((j) => ACTIVE_STATUSES.has(j.status));
  const finished = (data ?? []).filter((j) => !ACTIVE_STATUSES.has(j.status));

  if (authLoading) {
    return (
      <div className="page-center">
        <Spinner label="Загрузка…" />
      </div>
    );
  }
  if (!user) return <LoginCard />;

  return (
    <div className="jobs-page">
      <div className="page-head">
        <h1 className="page-title">Задания</h1>
        <button type="button" className="btn btn-ghost btn-sm" onClick={refetch}>
          Обновить
        </button>
      </div>

      {error && <div className="alert alert-error">Не удалось загрузить задания.</div>}

      {loading && !data ? (
        <div className="page-center">
          <Spinner label="Загрузка заданий…" />
        </div>
      ) : (
        <>
          <section className="jobs-section">
            <h2 className="section-title">
              Активные
              {hasActiveJobs(data) && <span className="live-dot" aria-label="в реальном времени" />}
            </h2>
            <JobList
              jobs={active}
              emptyText="Нет активных заданий."
              onOpen={() => navigate('/')}
            />
          </section>

          <section className="jobs-section">
            <h2 className="section-title">Недавние</h2>
            <JobList
              jobs={finished.slice(0, 15)}
              emptyText="Пока нет завершённых заданий."
              onOpen={() => navigate('/')}
            />
          </section>
        </>
      )}
    </div>
  );
}
