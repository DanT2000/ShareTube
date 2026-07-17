// Renders the official Telegram Login Widget and hands the signed auth payload
// back to the caller. The widget injects a cross-origin <iframe> button and
// invokes a global callback we register per-instance.
import { useEffect, useId, useRef } from 'react';
import type { TelegramAuthPayload } from '../types';

const BOT_USERNAME =
  (import.meta.env.VITE_TG_BOT_USERNAME as string | undefined) || 'sharetube_bot';

interface TelegramLoginButtonProps {
  onAuth: (payload: TelegramAuthPayload) => void;
  botUsername?: string;
  size?: 'small' | 'medium' | 'large';
  cornerRadius?: number;
  requestAccess?: boolean;
}

// Global registry so the widget's inline `data-onauth` can find our handler.
interface AuthCallbackWindow extends Window {
  __sharetubeTgAuth?: Record<string, (user: TelegramAuthPayload) => void>;
}

export default function TelegramLoginButton({
  onAuth,
  botUsername = BOT_USERNAME,
  size = 'large',
  cornerRadius = 12,
  requestAccess = true,
}: TelegramLoginButtonProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rawId = useId();
  const callbackName = `cb_${rawId.replace(/[^a-zA-Z0-9]/g, '')}`;
  const onAuthRef = useRef(onAuth);
  onAuthRef.current = onAuth;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const w = window as AuthCallbackWindow;
    w.__sharetubeTgAuth = w.__sharetubeTgAuth || {};
    w.__sharetubeTgAuth[callbackName] = (user: TelegramAuthPayload) => {
      onAuthRef.current(user);
    };

    const script = document.createElement('script');
    script.async = true;
    script.src = 'https://telegram.org/js/telegram-widget.js?22';
    script.setAttribute('data-telegram-login', botUsername);
    script.setAttribute('data-size', size);
    script.setAttribute('data-radius', String(cornerRadius));
    script.setAttribute('data-onauth', `window.__sharetubeTgAuth.${callbackName}(user)`);
    if (requestAccess) script.setAttribute('data-request-access', 'write');
    script.setAttribute('data-userpic', 'true');

    container.appendChild(script);

    return () => {
      container.innerHTML = '';
      if (w.__sharetubeTgAuth) delete w.__sharetubeTgAuth[callbackName];
    };
  }, [botUsername, size, cornerRadius, requestAccess, callbackName]);

  return <div className="tg-login-widget" ref={containerRef} />;
}
