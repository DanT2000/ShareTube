import { useState } from 'react';
import TelegramLoginButton from './TelegramLoginButton';
import { ApiError } from '../api';
import { useAuth } from '../auth';
import type { TelegramAuthPayload } from '../types';

export default function LoginCard({ compact }: { compact?: boolean }) {
  const { loginWithTelegram } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleAuth = async (payload: TelegramAuthPayload) => {
    setBusy(true);
    setError(null);
    try {
      await loginWithTelegram(payload);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'Не удалось войти. Попробуйте ещё раз.',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={`login-card${compact ? ' login-card-compact' : ''}`}>
      {!compact && (
        <>
          <img src="/logo.svg" alt="" className="login-logo" width={56} height={56} />
          <h2>Вход в ShareTube</h2>
          <p className="muted">
            Войдите через Telegram, чтобы скачивать видео, аудио и галереи и хранить историю
            загрузок.
          </p>
        </>
      )}
      <div className="login-widget-wrap">
        <TelegramLoginButton onAuth={handleAuth} />
      </div>
      {busy && <p className="hint">Выполняется вход…</p>}
      {error && <p className="hint hint-warn">{error}</p>}
    </section>
  );
}
