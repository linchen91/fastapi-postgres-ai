import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Bind IPv4 explicitly so Playwright's webServer probe (127.0.0.1) and
    // browsers using 127.0.0.1 can reach the dev server. Vite's default
    // "localhost" may bind only [::1] on some systems.
    host: '127.0.0.1',
    port: 5173,
  },
})
