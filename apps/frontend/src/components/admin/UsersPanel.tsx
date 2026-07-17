import { useState } from 'react';
import Spinner from '../Spinner';
import { admin } from '../../api';
import { usePolling } from '../../hooks';
import { formatDateTime } from '../../format';
import type { AdminUser } from '../../types';

export default function UsersPanel() {
  const { data, loading, error, refetch } = usePolling<AdminUser[]>(() => admin.users(), 0);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const toggleBlock = async (u: AdminUser) => {
    setBusyId(u.id);
    setNotice(null);
    try {
      await admin.blockUser(u.id, !u.is_blocked);
      setNotice(u.is_blocked ? 'Пользователь разблокирован.' : 'Пользователь заблокирован.');
      refetch();
    } catch {
      setNotice('Не удалось изменить статус.');
    } finally {
      setBusyId(null);
    }
  };

  const setQuota = async (u: AdminUser) => {
    const raw = window.prompt(
      'Дневной лимит заданий (пусто = без лимита):',
      u.quota_daily_jobs?.toString() ?? '',
    );
    if (raw === null) return;
    const trimmed = raw.trim();
    const value = trimmed === '' ? null : Number(trimmed);
    if (value !== null && (!Number.isFinite(value) || value < 0)) {
      setNotice('Некорректное значение квоты.');
      return;
    }
    setBusyId(u.id);
    setNotice(null);
    try {
      await admin.setQuota(u.id, value);
      setNotice('Квота обновлена.');
      refetch();
    } catch {
      setNotice('Не удалось обновить квоту.');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="admin-users">
      <div className="admin-panel-head">
        <h2>Пользователи</h2>
        <button className="btn btn-ghost btn-sm" onClick={refetch} type="button">
          Обновить
        </button>
      </div>

      {notice && <div className="alert alert-info">{notice}</div>}
      {error && <div className="alert alert-error">Ошибка загрузки пользователей.</div>}

      {loading && !data ? (
        <Spinner label="Загрузка…" />
      ) : (
        <div className="table-scroll">
          <table className="admin-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Имя</th>
                <th>Роль</th>
                <th>Статус</th>
                <th>Квота/день</th>
                <th>Регистрация</th>
                <th aria-label="Действия" />
              </tr>
            </thead>
            <tbody>
              {(data ?? []).map((u) => (
                <tr key={u.id} className={u.is_blocked ? 'row-blocked' : undefined}>
                  <td>{u.id}</td>
                  <td>{u.display_name || '—'}</td>
                  <td>{u.is_admin ? <span className="chip chip-sm">админ</span> : 'пользователь'}</td>
                  <td>
                    {u.is_blocked ? (
                      <span className="status-badge" data-tone="failed">
                        заблокирован
                      </span>
                    ) : (
                      <span className="status-badge" data-tone="done">
                        активен
                      </span>
                    )}
                  </td>
                  <td>{u.quota_daily_jobs ?? '∞'}</td>
                  <td className="cell-nowrap">{formatDateTime(u.created_at)}</td>
                  <td className="cell-actions">
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost"
                      disabled={busyId === u.id}
                      onClick={() => setQuota(u)}
                    >
                      Квота
                    </button>
                    <button
                      type="button"
                      className={`btn btn-sm ${u.is_blocked ? 'btn-secondary' : 'btn-danger'}`}
                      disabled={busyId === u.id}
                      onClick={() => toggleBlock(u)}
                    >
                      {u.is_blocked ? 'Разблокировать' : 'Заблокировать'}
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
