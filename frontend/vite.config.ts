import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import electron from 'vite-plugin-electron'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    electron([
      {
        // Electronメインプロセス
        entry: 'electron/main.ts',
        onstart(options) {
          options.startup()
        },
      },
      {
        // プリロードスクリプト
        entry: 'electron/preload.ts',
        onstart(options) {
          options.reload()
        },
      },
    ]),
  ],
  server: {
    port: 5173,
  },
})
