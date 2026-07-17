import { useState, type FormEvent } from 'react';
import Spinner from '../Spinner';
import { ApiError, admin } from '../../api';
import { usePolling } from '../../hooks';
import { formatDateTime } from '../../format';
import type { AuditLogEntry, ProxyDisplayMeta, ProxyProfile } from '../../types';

// Build a masked, safe-to-display connection string. The backend never returns
// credentials or full URLs — only protocol/host/port/has_auth — so this can
// never leak a secret.
function maskedMeta(meta: ProxyDisplayMeta | null): string {
  if (!meta) return 'скрыто';
  const proto = meta.protocol ? `${meta.protocol}://` : '';
  const host = meta.host ?? '•••';
  const port = meta.port ? `:${meta.port}` : '';
  const auth = meta.has_auth ? ' · с авторизацией' : '';
  return `${proto}${host}${port}${auth}`;
}

function statusTone(status: string): string {
  const s = status.toLowerCase();
  if (s === 'ok' || s === 'healthy') return 'done';
  if (s === 'failed' || s === 'error' || s === 'down') return 'failed';
  if (s === 'checking') return 'active';
  return 'idle';
}

function ProxyRow({
  p,
  onChanged,
}: {
  p: ProxyProfile;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [checkResult, setCheckResult] = useState<string | null>(null);

  const run = async (action: string, fn: () => Promise<unknown>) => {
    setBusy(action);
    setCheckResult(null);
    try {
      await fn();
      onChanged();
    } catch (err) {
      setCheckResult(err instanceof ApiError ? err.message : 'Ошибка операции');
    } finally {
      setBusy(null);
    }
  };

  const doCheck = async () => {
    setBusy('check');
    setCheckResult(null);
    try {
      const res = await admin.checkProxy(p.id);
      setCheckResult(
        `Проверка: ${res.status}` +
          (res.latency_ms !== null ? ` · ${res.latency_ms} мс` : '') +
          (res.error_category ? ` · ${res.error_category}` : ''),
      );
      onChanged();
    } catch (err) {
      setCheckResult(err instanceof ApiError ? err.message : 'Ошибка проверки');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className={`proxy-card${p.enabled ? '' : ' is-disabled'}`}>
      <div className="proxy-card-head">
        <div className="proxy-title">
          <span className="proxy-name">{p.name}</span>
          <span className="chip chip-sm">{p.kind}</span>
          {p.is_primary && <span className="chip chip-sm chip-primary">основной</span>}
          {p.is_backup && <span className="chip chip-sm chip-muted">резерв</span>}
          {!p.enabled && <span className="chip chip-sm chip-muted">выключен</span>}
        </div>
        <span className="status-badge" data-tone={statusTone(p.last_status)}>
          {p.last_status || 'unknown'}
        </span>
      </div>

      <div className="proxy-meta">
        <code className="proxy-endpoint">{maskedMeta(p.display_meta)}</code>
      </div>

      <dl className="proxy-facts">
        <div>
          <dt>Задержка</dt>
          <dd>{p.last_latency_ms !== null ? `${p.last_latency_ms} мс` : '—'}</dd>
        </div>
        <div>
          <dt>Проверено</dt>
          <dd>{formatDateTime(p.last_checked_at)}</dd>
        </div>
        <div>
          <dt>Ошибок</dt>
          <dd>{p.error_count}</dd>
        </div>
        <div>
          <dt>Приоритет</dt>
          <dd>{p.priority}</dd>
        </div>
        {p.last_error_category && (
          <div>
            <dt>Категория</dt>
            <dd className="error-code">{p.last_error_category}</dd>
          </div>
        )}
        {p.bound_sources && (
          <div>
            <dt>Источники</dt>
            <dd>{p.bound_sources}</dd>
          </div>
        )}
      </dl>

      {checkResult && <p className="hint">{checkResult}</p>}

      <div className="proxy-actions">
        <button type="button" className="btn btn-sm btn-secondary" disabled={busy !== null} onClick={doCheck}>
          {busy === 'check' ? 'Проверка…' : 'Проверить'}
        </button>
        <button
          type="button"
          className="btn btn-sm btn-ghost"
          disabled={busy !== null}
          onClick={() => run('toggle', () => admin.toggleProxy(p.id, !p.enabled))}
        >
          {p.enabled ? 'Выключить' : 'Включить'}
        </button>
        <button
          type="button"
          className="btn btn-sm btn-ghost"
          disabled={busy !== null || p.is_primary}
          onClick={() => run('primary', () => admin.setProxyRole(p.id, true, false))}
          title="Сделать основным маршрутом"
        >
          Сделать основным
        </button>
        <button
          type="button"
          className="btn btn-sm btn-ghost"
          disabled={busy !== null || p.is_backup}
          onClick={() => run('backup', () => admin.setProxyRole(p.id, false, true))}
        >
          В резерв
        </button>
        <button
          type="button"
          className="btn btn-sm btn-danger"
          disabled={busy !== null}
          onClick={() => {
            if (window.confirm(`Удалить профиль «${p.name}»?`)) {
              void run('delete', () => admin.deleteProxy(p.id));
            }
          }}
        >
          Удалить
        </button>
      </div>
    </div>
  );
}

function CreateHttpForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [priority, setPriority] = useState(100);
  const [isPrimary, setIsPrimary] = useState(false);
  const [isBackup, setIsBackup] = useState(false);
  const [boundSources, setBoundSources] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await admin.createHttpProxy({
        name: name.trim(),
        url: url.trim(),
        is_primary: isPrimary,
        is_backup: isBackup,
        priority,
        bound_sources: boundSources.trim() || undefined,
      });
      setMsg('HTTP-профиль добавлен.');
      setName('');
      setUrl('');
      setBoundSources('');
      onCreated();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : 'Не удалось создать профиль.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="proxy-form" onSubmit={submit}>
      <h4>Добавить HTTP / SOCKS прокси</h4>
      <div className="form-grid">
        <label className="field">
          <span>Название</span>
          <input value={name} onChange={(e) => setName(e.target.value)} required placeholder="http-main" />
        </label>
        <label className="field field-wide">
          <span>URL</span>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            placeholder="http://user:pass@host:port или socks5://host:port"
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <label className="field">
          <span>Приоритет</span>
          <input
            type="number"
            value={priority}
            onChange={(e) => setPriority(Number(e.target.value))}
            min={0}
          />
        </label>
        <label className="field field-wide">
          <span>Источники (через запятую, опц.)</span>
          <input
            value={boundSources}
            onChange={(e) => setBoundSources(e.target.value)}
            placeholder="instagram,tiktok"
          />
        </label>
      </div>
      <div className="form-checks">
        <label className="checkbox-row">
          <input type="checkbox" checked={isPrimary} onChange={(e) => setIsPrimary(e.target.checked)} />
          <span>Основной</span>
        </label>
        <label className="checkbox-row">
          <input type="checkbox" checked={isBackup} onChange={(e) => setIsBackup(e.target.checked)} />
          <span>Резервный</span>
        </label>
      </div>
      {msg && <p className="hint">{msg}</p>}
      <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
        {busy ? 'Сохранение…' : 'Добавить HTTP-профиль'}
      </button>
      <p className="hint">Секрет хранится зашифрованным и маскируется во всех ответах API.</p>
    </form>
  );
}

function CreateXrayForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('');
  const [config, setConfig] = useState('');
  const [priority, setPriority] = useState(50);
  const [isPrimary, setIsPrimary] = useState(false);
  const [isBackup, setIsBackup] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await admin.createXrayProxy({
        name: name.trim(),
        config_or_uri: config.trim(),
        is_primary: isPrimary,
        is_backup: isBackup,
        priority,
      });
      setMsg('Xray-профиль добавлен.');
      setName('');
      setConfig('');
      onCreated();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : 'Не удалось создать профиль.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="proxy-form" onSubmit={submit}>
      <h4>Добавить Xray (VLESS / VMess / Trojan / SS)</h4>
      <div className="form-grid">
        <label className="field">
          <span>Название</span>
          <input value={name} onChange={(e) => setName(e.target.value)} required placeholder="xray-main" />
        </label>
        <label className="field">
          <span>Приоритет</span>
          <input
            type="number"
            value={priority}
            onChange={(e) => setPriority(Number(e.target.value))}
            min={0}
          />
        </label>
      </div>
      <label className="field">
        <span>JSON-конфиг, URI или ссылка на подписку</span>
        <textarea
          value={config}
          onChange={(e) => setConfig(e.target.value)}
          required
          rows={5}
          placeholder='vless://... либо {"outbounds":[...]} либо https://sub.example/link'
          spellCheck={false}
          autoComplete="off"
        />
      </label>
      <div className="form-checks">
        <label className="checkbox-row">
          <input type="checkbox" checked={isPrimary} onChange={(e) => setIsPrimary(e.target.checked)} />
          <span>Основной</span>
        </label>
        <label className="checkbox-row">
          <input type="checkbox" checked={isBackup} onChange={(e) => setIsBackup(e.target.checked)} />
          <span>Резервный</span>
        </label>
      </div>
      {msg && <p className="hint">{msg}</p>}
      <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
        {busy ? 'Сохранение…' : 'Добавить Xray-профиль'}
      </button>
    </form>
  );
}

function SwitchLog() {
  const { data } = usePolling<AuditLogEntry[]>(() => admin.logs(50), 20000);
  const proxyLogs = (data ?? []).filter((l) => l.action.includes('proxy'));
  if (proxyLogs.length === 0) {
    return <p className="muted">Пока нет событий переключения маршрутов.</p>;
  }
  return (
    <ul className="switch-log">
      {proxyLogs.slice(0, 15).map((l, i) => (
        <li key={i}>
          <span className="switch-time">{formatDateTime(l.created_at)}</span>
          <span className="switch-action">{l.action}</span>
          {l.target && <span className="switch-target">{l.target}</span>}
        </li>
      ))}
    </ul>
  );
}

export default function ProxyPanel() {
  const { data, loading, error, refetch } = usePolling<ProxyProfile[]>(() => admin.proxies(), 15000);

  return (
    <div className="admin-proxies">
      <div className="admin-panel-head">
        <h2>Сеть и прокси</h2>
        <button className="btn btn-ghost btn-sm" onClick={refetch} type="button">
          Обновить
        </button>
      </div>

      <p className="muted">
        Все загрузки медиа идут только через активные исходящие профили. Секреты маскируются —
        полный URL профиля не показывается никогда.
      </p>

      {error && <div className="alert alert-error">Не удалось загрузить профили.</div>}

      {loading && !data ? (
        <Spinner label="Загрузка профилей…" />
      ) : (
        <div className="proxy-list">
          {(data ?? []).length === 0 && <p className="muted">Профили не настроены.</p>}
          {(data ?? []).map((p) => (
            <ProxyRow key={p.id} p={p} onChanged={refetch} />
          ))}
        </div>
      )}

      <div className="admin-card">
        <h3>Журнал переключений маршрутов</h3>
        <SwitchLog />
      </div>

      <div className="proxy-forms">
        <CreateHttpForm onCreated={refetch} />
        <CreateXrayForm onCreated={refetch} />
      </div>
    </div>
  );
}
