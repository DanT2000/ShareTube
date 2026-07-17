import { useState } from 'react';
import Spinner from '../Spinner';
import StatusBadge from '../StatusBadge';
import { admin, ACTIVE_STATUSES } from '../../api';
import { usePolling } from '../../hooks';
import { formatBytes, formatDateTime, sourceLabel } from '../../format';
import type { AdminJob } from '../../types';

type Preset = 'active' | 'queued' | 'failed' | 'all';

const PRESET_TITLES: Record<Preset, string> = {
  active: 'Активные задания',
  queued: 'Очередь',
  failed: 'Ошибки',
  all: 'Все задания',
};

export default function JobsAdmin({ preset }: { preset: Preset }) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // The server filters by a single status; "active" spans several, so we fetch
  // broadly and filter client-side for that preset.
  const serverStatus = preset === 'queued' ? 'queued' : preset === 'failed' ? 'failed' : undefined;

  const { data, loading, error, refetch } = usePolling<AdminJob[]>(
    () => admin.jobs({ status: serverStatus, limit: 100 }),
    5000,
  );

  const rows = (data ?? []).filter((j) =>
    preset === 'active' ? ACTIVE_STATUSES.has(j.status) : true,
  );

  const doCancel = async (id: string) => {
    setBusyId(id);
    setNotice(null);
    try {
      await admin.cancelJob(id);
      setNotice('Задание отменено.');
      refetch();
    } catch {
      setNotice('Не удалось отменить задание.');
    } finally {
      setBusyId(null);
    }
  };

  const doDeleteFile = async (id: string) => {
    setBusyId(id);
    setNotice(null);
    try {
      await admin.deleteJobFile(id);
      setNotice('Файл удалён.');
      refetch();
    } catch {
      setNotice('Не удалось удалить файл.');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="admin-jobs">
      <div className="admin-panel-head">
        <h2>{PRESET_TITLES[preset]}</h2>
        <button className="btn btn-ghost btn-sm" onClick={refetch} type="button">
          Обновить
        </button>
      </div>

      {notice && <div className="alert alert-info">{notice}</div>}
      {error && <div className="alert alert-error">Ошибка загрузки заданий.</div>}

      {loading && !data ? (
        <Spinner label="Загрузка…" />
      ) : rows.length === 0 ? (
        <p className="muted">Нет заданий в этой категории.</p>
      ) : (
        <div className="table-scroll">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Статус</th>
                <th>Источник</th>
                <th>Ссылка</th>
                <th>Размер</th>
                <th>Создано</th>
                <th aria-label="Действия" />
              </tr>
            </thead>
            <tbody>
              {rows.map((j) => (
                <tr key={j.id}>
                  <td>
                    <StatusBadge status={j.status} />
                    {j.error_code && <span className="error-code"> {j.error_code}</span>}
                  </td>
                  <td>{sourceLabel(j.source)}</td>
                  <td className="cell-url" title={j.url}>
                    {j.url}
                  </td>
                  <td>{formatBytes(j.actual_size_bytes)}</td>
                  <td className="cell-nowrap">{formatDateTime(j.created_at)}</td>
                  <td className="cell-actions">
                    {ACTIVE_STATUSES.has(j.status) || j.status === 'queued' ? (
                      <button
                        type="button"
                        className="btn btn-sm btn-danger"
                        disabled={busyId === j.id}
                        onClick={() => doCancel(j.id)}
                      >
                        Отменить
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost"
                      disabled={busyId === j.id}
                      onClick={() => doDeleteFile(j.id)}
                      title="Удалить сохранённый файл"
                    >
                      Удалить файл
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
