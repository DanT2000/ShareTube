// Telegram Mini App integration helpers.
//
// telegram-web-app.js is loaded from index.html. On a plain website
// window.Telegram.WebApp may still exist but `initData` is an empty string,
// which is how we distinguish a real Mini App launch from an ordinary browser.

export interface TelegramThemeParams {
  bg_color?: string;
  text_color?: string;
  hint_color?: string;
  link_color?: string;
  button_color?: string;
  button_text_color?: string;
  secondary_bg_color?: string;
  header_bg_color?: string;
  accent_text_color?: string;
  section_bg_color?: string;
  destructive_text_color?: string;
}

export interface TelegramWebApp {
  initData: string;
  initDataUnsafe: Record<string, unknown> & {
    user?: {
      id: number;
      first_name?: string;
      last_name?: string;
      username?: string;
      photo_url?: string;
    };
  };
  version: string;
  platform: string;
  colorScheme: 'light' | 'dark';
  themeParams: TelegramThemeParams;
  isExpanded: boolean;
  viewportHeight: number;
  viewportStableHeight: number;
  headerColor: string;
  backgroundColor: string;
  ready(): void;
  expand(): void;
  close(): void;
  setHeaderColor(color: string): void;
  setBackgroundColor(color: string): void;
  openLink(url: string, options?: { try_instant_view?: boolean }): void;
  openTelegramLink(url: string): void;
  showAlert(message: string, callback?: () => void): void;
  onEvent(eventType: string, handler: () => void): void;
  offEvent(eventType: string, handler: () => void): void;
  HapticFeedback?: {
    impactOccurred(style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft'): void;
    notificationOccurred(type: 'error' | 'success' | 'warning'): void;
    selectionChanged(): void;
  };
  MainButton?: {
    text: string;
    isVisible: boolean;
    show(): void;
    hide(): void;
    setText(text: string): void;
    onClick(cb: () => void): void;
    offClick(cb: () => void): void;
  };
}

export function getWebApp(): TelegramWebApp | undefined {
  if (typeof window === 'undefined') return undefined;
  return window.Telegram?.WebApp;
}

/** Non-empty initData string means we are inside a genuine Telegram Mini App. */
export function getInitData(): string {
  const wa = getWebApp();
  const initData = wa?.initData;
  return initData && initData.length > 0 ? initData : '';
}

export function isTelegramMiniApp(): boolean {
  return getInitData().length > 0;
}

let themeHandler: (() => void) | null = null;

/** Map Telegram theme params onto our CSS variables so the Mini App matches the client. */
function applyThemeParams(wa: TelegramWebApp): void {
  const p = wa.themeParams || {};
  const root = document.documentElement;
  const set = (cssVar: string, value?: string) => {
    if (value) root.style.setProperty(cssVar, value);
  };
  root.setAttribute('data-tg', '1');
  root.setAttribute('data-theme', wa.colorScheme === 'light' ? 'light' : 'dark');
  set('--bg', p.bg_color);
  set('--surface', p.secondary_bg_color || p.section_bg_color);
  set('--text', p.text_color);
  set('--muted', p.hint_color);
  set('--accent', p.button_color);
  set('--accent-text', p.button_text_color);
  set('--link', p.link_color);
}

/**
 * Initialize the Mini App: signal readiness, expand to full height, sync theme,
 * and keep CSS vars in sync when the user switches Telegram themes.
 * No-op on a normal website. Returns true when running inside Telegram.
 */
export function initTelegram(): boolean {
  const wa = getWebApp();
  if (!wa) return false;
  try {
    wa.ready();
    wa.expand();
    applyThemeParams(wa);
    if (themeHandler) wa.offEvent('themeChanged', themeHandler);
    themeHandler = () => applyThemeParams(wa);
    wa.onEvent('themeChanged', themeHandler);
  } catch {
    // Older Telegram clients may not implement every method — degrade gracefully.
  }
  return isTelegramMiniApp();
}

/** Prefer Telegram's in-app browser / share sheet when available. */
export function openExternal(url: string): void {
  const wa = getWebApp();
  if (wa) {
    try {
      wa.openLink(url);
      return;
    } catch {
      /* fall through */
    }
  }
  if (typeof window !== 'undefined') window.open(url, '_blank', 'noopener');
}

export function haptic(type: 'success' | 'error' | 'warning' = 'success'): void {
  getWebApp()?.HapticFeedback?.notificationOccurred(type);
}

/** Read the Mini App user id (already validated server-side via initData). */
export function getTelegramUserId(): number | undefined {
  return getWebApp()?.initDataUnsafe?.user?.id;
}
