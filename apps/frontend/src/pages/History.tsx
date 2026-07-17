import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import JobList from '../components/JobList';
import LoginCard from '../components/LoginCard';
import Spinner from '../components/Spinner';
import { jobs as jobsApi, TERMINAL_STATUSES } from '../api';
import { useAuth } from '../auth';
import { usePolling } from '../hooks';
import { formatBytes } from '../format';
import type { JobOut } from '../types';

export default function History() {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();

  // History is static-ish; poll slowly to reflect newly finished jobs.
  const { data, loading, error, refetch } = usePolling<JobOut[]>(
    () => jobsApi.list(50),
    15000,
    Boolean(user),
  );

  const finished = useMemo(
    () => (data ?? []).filter((j) => TERMINAL_STATUSES.has(j.status)),
    [data],
  );

  const totalBytes = useMemo(
    () => finished.reduce((sum, j) => sum + (j.actual_size_bytes ?? 0), 0),
    [finished],
  );
  const doneCount = finished.filter((j) => j.status === 'done').length;

  if (authLoading) {
    return (
      <div className="page-center">
        <Spinner label="Загрузка…" />
      </div>
    );
  }
  if (!user) return <LoginCard />;

  return (
    <div className="history-page">
      <div className="page-head">
        <h1 className="page-title">История</h1>
        <button type="button" className="btn btn-ghost btn-sm" onClick={refetch}>
          Обновить
        </button>
      </div>

      {finished.length > 0 && (
        <div className="history-stats">
          <div className="stat">
            <span className="stat-value">{doneCount}</span>
            <span className="stat-label">успешных</span>
          </div>
          <div className="stat">
            <span className="stat-value">{finished.length}</span>
            <span className="stat-label">всего</span>
          </div>
          <div className="stat">
            <span className="stat-value">{formatBytes(totalBytes)}</span>
            <span className="stat-label">объём</span>
          </div>
        </div>
      )}

      {error && <div className="alert alert-error">Не удалось загрузить историю.</div>}

      {loading && !data ? (
        <div className="page-center">
          <Spinner label="Загрузка истории…" />
        </div>
      ) : (
        <JobList
          jobs={finished}
          emptyText="История пуста. Скачайте что-нибудь на главной."
          onOpen={() => navigate('/')}
        />
      )}
    </div>
  );
}
