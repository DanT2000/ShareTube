import Spinner from '../Spinner';
import { admin } from '../../api';
import { usePolling } from '../../hooks';
import { formatBytes } from '../../format';
import type { AdminDashboard } from '../../types';

function StatCard({
  label,
  value,
  tone,
  sub,
}: {
  label: string;
  value: string | number;
  tone?: string;
  sub?: string;
}) {
  return (
    <div className="admin-stat" data-tone={tone}>
      <span className="admin-stat-value">{value}</span>
      <span className="admin-stat-label">{label}</span>
      {sub && <span className="admin-stat-sub">{sub}</span>}
    </div>
  );
}

function Bar({ used, cap }: { used: number; cap: number }) {
  const pct = cap > 0 ? Math.min(100, (used / cap) * 100) : 0;
  const tone = pct > 90 ? 'failed' : pct > 70 ? 'warn' : 'done';
  return (
    <div className="storage-bar" data-tone={tone}>
      <div className="storage-fill" style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function Dashboard() {
  const { data, loading, error, refetch } = usePolling<AdminDashboard>(
    () => admin.dashboard(),
    10000,
  );

  if (loading && !data) return <Spinner label="Загрузка панели…" />;
  if (error && !data) return <div className="alert alert-error">Ошибка загрузки панели.</div>;
  if (!data) return null;

  const { jobs, users, storage } = data;

  return (
    <div className="admin-dashboard">
      <div className="admin-panel-head">
        <h2>Обзор</h2>
        <button className="btn btn-ghost btn-sm" onClick={refetch} type="button">
          Обновить
        </button>
      </div>

      <div className="admin-stats-grid">
        <StatCard label="Активные" value={jobs.active} tone="active" />
        <StatCard label="В очереди" value={jobs.queued} tone="idle" />
        <StatCard label="Ошибки" value={jobs.failed} tone="failed" />
        <StatCard label="Завершено" value={jobs.done} tone="done" />
        <StatCard label="Пользователи" value={users} />
      </div>

      <div className="admin-card">
        <h3>Хранилище</h3>
        <Bar used={storage.used_bytes} cap={storage.cap_bytes} />
        <div className="storage-legend">
          <span>
            Использовано <strong>{formatBytes(storage.used_bytes)}</strong> из{' '}
            {formatBytes(storage.cap_bytes)}
          </span>
          {storage.disk_free !== null && storage.disk_total !== null && (
            <span className="muted">
              Диск: свободно {formatBytes(storage.disk_free)} из {formatBytes(storage.disk_total)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
