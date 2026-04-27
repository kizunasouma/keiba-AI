/**
 * Electronプリロードスクリプト
 * レンダラープロセスに安全に公開するAPIを定義する
 */
import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electronAPI', {
  /** OS情報 */
  platform: process.platform,
  /** ポップアップウィンドウを独立したBrowserWindowとして開く */
  openPopup: (type: string, id: string) => ipcRenderer.invoke('open-popup', type, id),
  /** ポップアップウィンドウのタイトルを更新する */
  setPopupTitle: (title: string) => ipcRenderer.invoke('set-popup-title', title),
})
