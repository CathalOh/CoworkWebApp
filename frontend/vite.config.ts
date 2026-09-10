import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  // BACKEND_ORIGIN (from .env or the shell) points the dev proxy at the FastAPI server.
  const env = loadEnv(mode, '.', '')
  const backend = env.BACKEND_ORIGIN || 'http://localhost:8000'
  return {
    plugins: [react()],
    resolve: { alias: { '@': '/src' } },
    server: {
      port: 5173,
      proxy: {
        '/v1': { target: backend, changeOrigin: false, ws: true },
        '/healthz': { target: backend },
        '/readyz': { target: backend },
      },
    },
    build: { sourcemap: false, chunkSizeWarningLimit: 900 },
  }
})
