import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
// Firebase Hosting へ載せる Static SPA。Backend(Cloud Run) は別Originのため
// Hosting Rewrite ではなく VITE_API_BASE_URL の直接HTTPSで叩く（AGENTS.md §2.1）。
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
