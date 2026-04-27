/**
 * タブ状態管理フック
 * ブラウザ風タブの開閉・切替・タイトル更新を管理する
 */
import { useState, useCallback, useMemo } from 'react'

// --- 型定義 ---
export type TabDescriptor =
  | { type: 'race'; raceKey: string }
  | { type: 'horse'; horseId: number }
  | { type: 'jockey'; jockeyId: number }
  | { type: 'trainer'; trainerId: number }

export interface Tab {
  id: string
  descriptor: TabDescriptor
  title: string
  openedAt: number
}

const MAX_TABS = 10

/** descriptor から決定的なIDを生成 */
function makeId(d: TabDescriptor): string {
  switch (d.type) {
    case 'race': return `race-${d.raceKey}`
    case 'horse': return `horse-${d.horseId}`
    case 'jockey': return `jockey-${d.jockeyId}`
    case 'trainer': return `trainer-${d.trainerId}`
  }
}

/** デフォルトタイトルを生成 */
function defaultTitle(d: TabDescriptor): string {
  switch (d.type) {
    case 'race': return 'レース読込中...'
    case 'horse': return '馬 読込中...'
    case 'jockey': return '騎手 読込中...'
    case 'trainer': return '調教師 読込中...'
  }
}

export function useTabManager() {
  const [tabs, setTabs] = useState<Tab[]>([])
  const [activeTabId, setActiveTabId] = useState<string | null>(null)

  const activeTab = useMemo(
    () => tabs.find(t => t.id === activeTabId) ?? null,
    [tabs, activeTabId],
  )

  /** タブを開く（既存なら切替、新規なら追加） */
  const openTab = useCallback((descriptor: TabDescriptor, title?: string) => {
    const id = makeId(descriptor)
    setTabs(prev => {
      // 既存タブがあればフォーカスのみ
      if (prev.find(t => t.id === id)) {
        return prev
      }
      // 上限チェック: 最古の非アクティブタブを閉じる
      let next = [...prev]
      if (next.length >= MAX_TABS) {
        const oldest = next
          .filter(t => t.id !== activeTabId)
          .sort((a, b) => a.openedAt - b.openedAt)[0]
        if (oldest) {
          next = next.filter(t => t.id !== oldest.id)
        }
      }
      next.push({
        id,
        descriptor,
        title: title ?? defaultTitle(descriptor),
        openedAt: Date.now(),
      })
      return next
    })
    setActiveTabId(id)
  }, [activeTabId])

  /** タブを閉じる */
  const closeTab = useCallback((id: string) => {
    setTabs(prev => {
      const idx = prev.findIndex(t => t.id === id)
      if (idx === -1) return prev
      const next = prev.filter(t => t.id !== id)
      // 閉じたのがアクティブタブの場合、隣に移動
      setActiveTabId(current => {
        if (current !== id) return current
        if (next.length === 0) return null
        // 右隣、なければ左隣
        const newIdx = Math.min(idx, next.length - 1)
        return next[newIdx].id
      })
      return next
    })
  }, [])

  /** タブタイトルを更新 */
  const updateTabTitle = useCallback((id: string, title: string) => {
    setTabs(prev => prev.map(t => t.id === id ? { ...t, title } : t))
  }, [])

  /** 他のタブを全て閉じる */
  const closeOtherTabs = useCallback((keepId: string) => {
    setTabs(prev => prev.filter(t => t.id === keepId))
    setActiveTabId(keepId)
  }, [])

  /** 全タブを閉じる */
  const closeAllTabs = useCallback(() => {
    setTabs([])
    setActiveTabId(null)
  }, [])

  return {
    tabs,
    activeTabId,
    activeTab,
    openTab,
    closeTab,
    setActiveTab: setActiveTabId,
    updateTabTitle,
    closeOtherTabs,
    closeAllTabs,
  }
}
