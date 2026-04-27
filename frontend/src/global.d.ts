/**
 * グローバル型定義 — Electron APIのWindow拡張
 */
declare global {
  interface Window {
    electronAPI?: {
      /** OS情報 */
      platform: string
      /** ポップアップウィンドウを独立したBrowserWindowとして開く */
      openPopup: (type: string, id: string) => Promise<void>
      /** ポップアップウィンドウのタイトルを更新する */
      setPopupTitle: (title: string) => Promise<void>
    }
  }
}

export {}
