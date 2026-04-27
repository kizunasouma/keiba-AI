/**
 * フローティングウィンドウ管理フック
 * ウィンドウの開閉・位置・サイズ・重ね順を管理する
 */
import { useState, useCallback } from 'react'

export type WindowDescriptor =
  | { type: 'race'; raceKey: string }
  | { type: 'horse'; horseId: number }
  | { type: 'jockey'; jockeyId: number }
  | { type: 'trainer'; trainerId: number }

export interface FloatingWindow {
  id: string
  descriptor: WindowDescriptor
  title: string
  x: number
  y: number
  width: number
  height: number
  zIndex: number
  minimized: boolean
  maximized: boolean
}

// ウィンドウ種別ごとのデフォルトサイズ
const DEFAULT_SIZE: Record<string, { w: number; h: number }> = {
  race: { w: 1200, h: 800 },
  horse: { w: 950, h: 700 },
  jockey: { w: 900, h: 650 },
  trainer: { w: 850, h: 600 },
}

let nextZ = 100
// 新規ウィンドウの位置をずらすカウンター
let openCount = 0

/** DescriptorからIDのみを取得（IPC送信用） */
function getDescriptorId(d: WindowDescriptor): string {
  switch (d.type) {
    case 'race': return d.raceKey
    case 'horse': return String(d.horseId)
    case 'jockey': return String(d.jockeyId)
    case 'trainer': return String(d.trainerId)
  }
}

function makeId(d: WindowDescriptor): string {
  switch (d.type) {
    case 'race': return `race-${d.raceKey}`
    case 'horse': return `horse-${d.horseId}`
    case 'jockey': return `jockey-${d.jockeyId}`
    case 'trainer': return `trainer-${d.trainerId}`
  }
}

function defaultTitle(d: WindowDescriptor): string {
  switch (d.type) {
    case 'race': return 'レース読込中...'
    case 'horse': return '馬 読込中...'
    case 'jockey': return '騎手 読込中...'
    case 'trainer': return '調教師 読込中...'
  }
}

export function useWindowManager() {
  const [windows, setWindows] = useState<FloatingWindow[]>([])

  /** ウィンドウを開く（既存ならフォーカス）
   * Electron環境ではOS別BrowserWindowとして開く
   * ブラウザ環境では従来のフローティングウィンドウにフォールバック */
  const openWindow = useCallback((descriptor: WindowDescriptor, title?: string) => {
    // Electron環境: IPCで独立したBrowserWindowを生成
    if (window.electronAPI?.openPopup) {
      const id = getDescriptorId(descriptor)
      window.electronAPI.openPopup(descriptor.type, id)
      return
    }

    // ブラウザ環境: 従来のフローティングウィンドウ方式
    const id = makeId(descriptor)
    setWindows(prev => {
      const existing = prev.find(w => w.id === id)
      if (existing) {
        // 既存をフォーカス（最前面）+ 最小化解除
        nextZ++
        return prev.map(w => w.id === id ? { ...w, zIndex: nextZ, minimized: false } : w)
      }
      // 新規ウィンドウ
      const size = DEFAULT_SIZE[descriptor.type] ?? { w: 700, h: 500 }
      const offset = (openCount % 8) * 30
      openCount++
      nextZ++
      return [...prev, {
        id,
        descriptor,
        title: title ?? defaultTitle(descriptor),
        x: 60 + offset,
        y: 40 + offset,
        width: size.w,
        height: size.h,
        zIndex: nextZ,
        minimized: false,
        maximized: false,
      }]
    })
  }, [])

  /** ウィンドウを閉じる */
  const closeWindow = useCallback((id: string) => {
    setWindows(prev => prev.filter(w => w.id !== id))
  }, [])

  /** ウィンドウをフォーカス（最前面に） */
  const focusWindow = useCallback((id: string) => {
    nextZ++
    setWindows(prev => prev.map(w => w.id === id ? { ...w, zIndex: nextZ } : w))
  }, [])

  /** ウィンドウ位置を更新 */
  const moveWindow = useCallback((id: string, x: number, y: number) => {
    setWindows(prev => prev.map(w => w.id === id ? { ...w, x, y } : w))
  }, [])

  /** ウィンドウサイズを更新 */
  const resizeWindow = useCallback((id: string, width: number, height: number) => {
    setWindows(prev => prev.map(w => w.id === id ? { ...w, width, height } : w))
  }, [])

  /** ウィンドウの位置とサイズを同時に更新（辺・角リサイズ用） */
  const moveAndResizeWindow = useCallback((id: string, x: number, y: number, width: number, height: number) => {
    setWindows(prev => prev.map(w => w.id === id ? { ...w, x, y, width, height } : w))
  }, [])

  /** タイトル更新 */
  const updateTitle = useCallback((id: string, title: string) => {
    setWindows(prev => prev.map(w => w.id === id ? { ...w, title } : w))
  }, [])

  /** 最小化/復元 */
  const toggleMinimize = useCallback((id: string) => {
    setWindows(prev => prev.map(w => w.id === id ? { ...w, minimized: !w.minimized } : w))
  }, [])

  /** 最大化/復元 */
  const toggleMaximize = useCallback((id: string) => {
    nextZ++
    setWindows(prev => prev.map(w => w.id === id ? { ...w, maximized: !w.maximized, zIndex: nextZ } : w))
  }, [])

  /** 全ウィンドウを閉じる */
  const closeAll = useCallback(() => {
    setWindows([])
  }, [])

  /** ウィンドウ整列（カスケード） */
  const cascadeWindows = useCallback(() => {
    setWindows(prev => prev.map((w, i) => ({
      ...w,
      x: 40 + i * 30,
      y: 40 + i * 30,
      maximized: false,
      minimized: false,
      zIndex: 100 + i,
    })))
    nextZ = 100 + windows.length
  }, [windows.length])

  /** ウィンドウ整列（タイル） */
  const tileWindows = useCallback(() => {
    const visible = windows.filter(w => !w.minimized)
    if (visible.length === 0) return
    const cols = Math.ceil(Math.sqrt(visible.length))
    const rows = Math.ceil(visible.length / cols)
    // 画面サイズの80%を使う想定
    const areaW = window.innerWidth - 40
    const areaH = window.innerHeight - 140
    const tileW = Math.floor(areaW / cols)
    const tileH = Math.floor(areaH / rows)
    let idx = 0
    setWindows(prev => prev.map(w => {
      if (w.minimized) return w
      const col = idx % cols
      const row = Math.floor(idx / cols)
      idx++
      return { ...w, x: 20 + col * tileW, y: 20 + row * tileH, width: tileW - 10, height: tileH - 10, maximized: false }
    }))
  }, [windows])

  return {
    windows,
    openWindow,
    closeWindow,
    focusWindow,
    moveWindow,
    resizeWindow,
    moveAndResizeWindow,
    updateTitle,
    toggleMinimize,
    toggleMaximize,
    closeAll,
    cascadeWindows,
    tileWindows,
  }
}
