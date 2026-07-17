import Spinner from '../Spinner';
import { admin } from '../../api';
import { usePolling } from '../../hooks';
import { formatDateTime } from '../../format';
import type { AuditLogEntry } from '../../types';

export default function LogsPanel() {
  const { data, loading, error, refetch } = usePolling<AuditLogEntry[]>(() => admin.logs(200), 15000);

  return (
    <div className="admin-logs">
      <div className="admin-panel-head">
        <h2>Журнал аудита</h2>
        <button className="btn btn-ghost btn-sm" onClick={refetch} type="button">
          Обновить
        </button>
      </div>

      {error && <div className="alert alert-error">Не удалось загрузить логи.</div>}

      {loading && !data ? (
        <Spinner label="Загрузка…" />
      ) : (
        <div className="table-scroll">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Время</th>
                <th>Кто</th>
                <th>Действие</th>
                <th>Объект</th>
                <th>Детали</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).length === 0 ? (
                <tr>
                  <td colSpan={5} className="muted">
                    Записей нет.
                  </td>
                </tr>
              ) : (
                (data ?? []).map((l, i) => (
                  <tr key={i}>
                    <td className="cell-nowrap">{formatDateTime(l.created_at)}</td>
                    <td>{l.actor}</td>
                    <td>
                      <span className="chip chip-sm">{l.action}</span>
                    </td>
                    <td>{l.target ?? '—'}</td>
                    <td className="cell-detail">
                      {l.detail ? <code>{JSON.stringify(l.detail)}</code> : '—'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
