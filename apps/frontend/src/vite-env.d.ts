/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/client" />

import type { TelegramWebApp } from './telegram';

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp;
    };
  }
}

export {};
