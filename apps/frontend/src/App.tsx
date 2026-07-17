import { useCallback, useEffect, useState } from 'react';
import { NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { useAuth } from './auth';
import { isTelegramMiniApp } from './telegram';
import Home from './pages/Home';
import Jobs from './pages/Jobs';
import History from './pages/History';
import Admin from './pages/Admin';

type Theme = 'dark' | 'light';

const THEME_KEY = 'sharetube-theme';

function initialTheme(): Theme {
  if (isTelegramMiniApp()) {
    // Telegram drives the theme; read what telegram.ts already stamped.
    const attr = document.documentElement.getAttribute('data-theme');
    return attr === 'light' ? 'light' : 'dark';
  }
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === 'light' || saved === 'dark') return saved;
  if (window.matchMedia?.('(prefers-color-scheme: light)').matches) return 'light';
  return 'dark';
}

function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={onToggle}
      aria-label={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
      title={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
    >
      {theme === 'dark' ? '☀️' : '🌙'}
    </button>
  );
}

function Header({ theme, onToggleTheme }: { theme: Theme; onToggleTheme: () => void }) {
  const { user } = useAuth();
  const miniApp = isTelegramMiniApp();

  return (
    <header className="app-header">
      <div className="container header-inner">
        <NavLink to="/" className="brand" aria-label="ShareTube — на главную">
          <img src="/logo.svg" alt="" className="brand-mark" width={32} height={32} />
          <span className="brand-word">ShareTube</span>
        </NavLink>

        <nav className="main-nav" aria-label="Основная навигация">
          <NavLink to="/" end className="nav-link">
            Главная
          </NavLink>
          <NavLink to="/jobs" className="nav-link">
            Задания
          </NavLink>
          <NavLink to="/history" className="nav-link">
            История
          </NavLink>
          {user?.is_admin && (
            <NavLink to="/admin" className="nav-link">
              Админ
            </NavLink>
          )}
        </nav>

        <div className="header-actions">
          {!miniApp && <ThemeToggle theme={theme} onToggle={onToggleTheme} />}
        </div>
      </div>
    </header>
  );
}

function BottomNav() {
  const { user } = useAuth();
  return (
    <nav className="bottom-nav" aria-label="Мобильная навигация">
      <NavLink to="/" end className="bottom-link">
        <span className="bottom-icon" aria-hidden>🏠</span>
        <span>Главная</span>
      </NavLink>
      <NavLink to="/jobs" className="bottom-link">
        <span className="bottom-icon" aria-hidden>⏳</span>
        <span>Задания</span>
      </NavLink>
      <NavLink to="/history" className="bottom-link">
        <span className="bottom-icon" aria-hidden>🕓</span>
        <span>История</span>
      </NavLink>
      {user?.is_admin && (
        <NavLink to="/admin" className="bottom-link">
          <span className="bottom-icon" aria-hidden>⚙️</span>
          <span>Админ</span>
        </NavLink>
      )}
    </nav>
  );
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(() => initialTheme());
  const location = useLocation();
  const miniApp = isTelegramMiniApp();

  useEffect(() => {
    // In a Mini App, telegram.ts controls data-theme; don't fight it.
    if (miniApp) return;
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme, miniApp]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  }, []);

  const isAdmin = location.pathname.startsWith('/admin');

  return (
    <div className={`app-shell${miniApp ? ' is-miniapp' : ''}`}>
      <Header theme={theme} onToggleTheme={toggleTheme} />
      <main className="app-main">
        <div className="container">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/history" element={<History />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="*" element={<Home />} />
          </Routes>
        </div>
      </main>
      {!isAdmin && <BottomNav />}
      <footer className="app-footer">
        <div className="container">
          <span>ShareTube · загрузчик медиа</span>
        </div>
      </footer>
    </div>
  );
}
