import { useState, type FormEvent } from 'react';
import Spinner from '../Spinner';
import { ApiError, admin } from '../../api';
import { usePolling } from '../../hooks';
import { formatDateTime, sourceLabel } from '../../format';
import type { CookieProfile } from '../../types';

const SOURCE_OPTIONS = ['youtube', 'instagram', 'tiktok', 'vk', 'vimeo', 'twitter', 'twitch'];

export default function CookiesPanel() {
  const { data, loading, error, refetch } = usePolling<CookieProfile[]>(() => admin.cookies(), 0);

  const [source, setSource] = useState('youtube');
  const [name, setName] = useState('default');
  const [cookieData, setCookieData] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!cookieData.trim()) return;
    setBusy(true);
    setMsg(null);
    try {
      await admin.upsertCookie(source, name.trim() || 'default', cookieData);
      setMsg('Cookie-профиль сохранён.');
      setCookieData('');
      refetch();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : 'Не удалось сохранить cookie.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="admin-cookies">
      <div className="admin-panel-head">
        <h2>Cookie-профили</h2>
        <button className="btn btn-ghost btn-sm" onClick={refetch} type="button">
          Обновить
        </button>
      </div>

      <p className="muted">
        Cookie-данные хранятся зашифрованными и никогда не возвращаются API — отображается лишь факт
        их наличия и статус.
      </p>

      {error && <div className="alert alert-error">Не удалось загрузить профили.</div>}

      {loading && !data ? (
        <Spinner label="Загрузка…" />
      ) : (
        <div className="table-scroll">
          <table className="admin-table">
            <thead>
              <tr>
                <th>Источник</th>
                <th>Профиль</th>
                <th>Данные</th>
                <th>Состояние</th>
                <th>Проверено</th>
              </tr>
            </thead>
            <tbody>
              {(data ?? []).length === 0 ? (
                <tr>
                  <td colSpan={5} className="muted">
                    Профили не заданы.
                  </td>
                </tr>
              ) : (
                (data ?? []).map((c) => (
                  <tr key={c.id}>
                    <td>{sourceLabel(c.source)}</td>
                    <td>{c.name}</td>
                    <td>
                      {c.has_data ? (
                        <span className="chip chip-sm chip-primary">есть</span>
                      ) : (
                        <span className="chip chip-sm chip-muted">нет</span>
                      )}
                    </td>
                    <td>{c.health_status}</td>
                    <td className="cell-nowrap">{formatDateTime(c.last_checked_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      <form className="proxy-form" onSubmit={submit}>
        <h4>Загрузить cookie-профиль</h4>
        <div className="form-grid">
          <label className="field">
            <span>Источник</span>
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              {SOURCE_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {sourceLabel(s)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Название профиля</span>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="default" />
          </label>
        </div>
        <label className="field">
          <span>Cookie (формат Netscape / cookies.txt)</span>
          <textarea
            value={cookieData}
            onChange={(e) => setCookieData(e.target.value)}
            rows={6}
            placeholder="# Netscape HTTP Cookie File&#10;.youtube.com  TRUE  /  TRUE  0  KEY  VALUE"
            spellCheck={false}
            autoComplete="off"
          />
        </label>
        {msg && <p className="hint">{msg}</p>}
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
          {busy ? 'Сохранение…' : 'Сохранить cookie'}
        </button>
      </form>
    </div>
  );
}
