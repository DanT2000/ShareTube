import { useCallback, useEffect, useState } from 'react';
import TelegramLoginButton from '../components/TelegramLoginButton';
import Spinner from '../components/Spinner';
import Dashboard from '../components/admin/Dashboard';
import JobsAdmin from '../components/admin/JobsAdmin';
import UsersPanel from '../components/admin/UsersPanel';
import ProxyPanel from '../components/admin/ProxyPanel';
import CookiesPanel from '../components/admin/CookiesPanel';
import SourcesPanel from '../components/admin/SourcesPanel';
import VersionsPanel from '../components/admin/VersionsPanel';
import SettingsPanel from '../components/admin/SettingsPanel';
import LogsPanel from '../components/admin/LogsPanel';
import CleanupPanel from '../components/admin/CleanupPanel';
import { ApiError, admin } from '../api';
import type { TelegramAuthPayload } from '../types';

type TabKey =
  | 'dashboard'
  | 'active'
  | 'queue'
  | 'failed'
  | 'users'
  | 'proxies'
  | 'cookies'
  | 'sources'
  | 'versions'
  | 'settings'
  | 'logs'
  | 'cleanup';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'dashboard', label: 'Обзор' },
  { key: 'active', label: 'Активные' },
  { key: 'queue', label: 'Очередь' },
  { key: 'failed', label: 'Ошибки' },
  { key: 'users', label: 'Пользователи' },
  { key: 'proxies', label: 'Сеть и прокси' },
  { key: 'cookies', label: 'Cookies' },
  { key: 'sources', label: 'Источники' },
  { key: 'versions', label: 'Версии' },
  { key: 'settings', label: 'Настройки' },
  { key: 'logs', label: 'Логи' },
  { key: 'cleanup', label: 'Очистка' },
];

type AuthPhase = 'checking' | 'need-login' | 'ok';

function TabContent({ tab }: { tab: TabKey }) {
  switch (tab) {
    case 'dashboard':
      return <Dashboard />;
    case 'active':
      return <JobsAdmin preset="active" />;
    case 'queue':
      return <JobsAdmin preset="queued" />;
    case 'failed':
      return <JobsAdmin preset="failed" />;
    case 'users':
      return <UsersPanel />;
    case 'proxies':
      return <ProxyPanel />;
    case 'cookies':
      return <CookiesPanel />;
    case 'sources':
      return <SourcesPanel />;
    case 'versions':
      return <VersionsPanel />;
    case 'settings':
      return <SettingsPanel />;
    case 'logs':
      return <LogsPanel />;
    case 'cleanup':
      return <CleanupPanel />;
    default:
      return null;
  }
}

export default function Admin() {
  const [phase, setPhase] = useState<AuthPhase>('checking');
  const [tab, setTab] = useState<TabKey>('dashboard');
  const [loginError, setLoginError] = useState<string | null>(null);

  // Probe the admin session (there's no /admin/me): if the dashboard is
  // reachable, the st_admin cookie is valid.
  const probe = useCallback(async () => {
    try {
      await admin.dashboard();
      setPhase('ok');
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        setPhase('need-login');
      } else {
        // Network / server error — still show login so admin can retry.
        setPhase('need-login');
      }
    }
  }, []);

  useEffect(() => {
    void probe();
  }, [probe]);

  const handleAdminAuth = async (payload: TelegramAuthPayload) => {
    setLoginError(null);
    try {
      await admin.login(payload);
      setPhase('ok');
    } catch (err) {
      if (err instanceof ApiError) {
        setLoginError(
          err.status === 403
            ? 'Этот аккаунт не является администратором.'
            : err.message,
        );
      } else {
        setLoginError('Не удалось выполнить вход.');
      }
    }
  };

  const handleLogout = async () => {
    try {
      await admin.logout();
    } finally {
      setPhase('need-login');
    }
  };

  if (phase === 'checking') {
    return (
      <div className="page-center">
        <Spinner label="Проверка доступа…" />
      </div>
    );
  }

  if (phase === 'need-login') {
    return (
      <div className="admin-login">
        <div className="login-card">
          <img src="/logo.svg" alt="" className="login-logo" width={56} height={56} />
          <h2>Панель администратора</h2>
          <p className="muted">Войдите через Telegram аккаунтом администратора.</p>
          <div className="login-widget-wrap">
            <TelegramLoginButton onAuth={handleAdminAuth} />
          </div>
          {loginError && <p className="hint hint-warn">{loginError}</p>}
        </div>
      </div>
    );
  }

  return (
    <div className="admin-panel">
      <div className="admin-topbar">
        <h1 className="page-title">Администрирование</h1>
        <button type="button" className="btn btn-ghost btn-sm" onClick={handleLogout}>
          Выйти
        </button>
      </div>

      <nav className="admin-tabs" aria-label="Разделы администрирования">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`admin-tab${tab === t.key ? ' is-active' : ''}`}
            onClick={() => setTab(t.key)}
            aria-current={tab === t.key ? 'page' : undefined}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <div className="admin-content">
        <TabContent tab={tab} />
      </div>
    </div>
  );
}
