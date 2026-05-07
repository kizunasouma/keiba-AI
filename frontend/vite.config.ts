import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import electron from 'vite-plugin-electron'

// ELECTRON=1 環境変数でElectron起動を制御（デフォルトはブラウザモード）
const useElectron = process.env.ELECTRON === '1'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    ...(useElectron
      ? [
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
        ]
      : []),
  ],
  server: {
    port: 5173,
  },
})
