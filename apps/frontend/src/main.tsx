import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { registerSW } from 'virtual:pwa-register';
import App from './App';
import { AuthProvider } from './auth';
import { initTelegram } from './telegram';
import './styles.css';

// Sync Telegram Mini App theme/viewport before first paint (no-op on the web).
initTelegram();

// Auto-updating PWA service worker (registerType: 'autoUpdate').
registerSW({ immediate: true });

const container = document.getElementById('root');
if (!container) throw new Error('Root element #root not found');

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
