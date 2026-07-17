import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

// ShareTube frontend build config.
// Dev proxy forwards API/download/health calls to the FastAPI backend on :8989
// so that cookies + same-origin requests behave exactly like production.
const BACKEND = process.env.VITE_BACKEND_ORIGIN || 'http://localhost:8989';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      // We ship our own hand-authored public/manifest.webmanifest, so let the
      // plugin manage only the service worker and precache.
      manifest: false,
      includeAssets: ['logo.svg', 'robots.txt', 'manifest.webmanifest'],
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
        // Offline shell fallback: any navigation that misses the cache serves index.html.
        navigateFallback: '/index.html',
        // Never hijack real backend routes with the SPA shell.
        navigateFallbackDenylist: [/^\/api/, /^\/download/, /^\/health/, /^\/metrics/],
        cleanupOutdatedCaches: true,
        clientsClaim: true,
        skipWaiting: true,
      },
      devOptions: {
        enabled: false,
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: BACKEND, changeOrigin: true, ws: true },
      '/download': { target: BACKEND, changeOrigin: true },
      '/health': { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    target: 'es2019',
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
  test: {
    globals: true,
    environment: 'jsdom',
    css: false,
  },
});
