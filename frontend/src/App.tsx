/**
 * アプリルート — ダッシュボード + フローティングウィンドウ型UI
 * ナビ: レース / AI予想 / 統計DB
 *
 * ポップアップモード: URLに ?popup=race&id=xxx がある場合、
 * ナビゲーション非表示で対応コンポーネントのみをレンダリングする。
 * Electronの独立BrowserWindowとして開かれた場合に使用される。
 */
import { useState, useEffect, useCallback } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useWindowManager } from './hooks/useWindowManager'
import type { WindowDescriptor } from './hooks/useWindowManager'
import Dashboard from './components/Dashboard'
import AIPredictionView from './components/AIPredictionView'
import StatsView from './components/StatsView'
import FavoritesView from './components/FavoritesView'
import HorseSearchView from './components/HorseSearchView'
import FloatingWindow from './components/FloatingWindow'
import RaceDetail from './components/RaceDetail'
import HorseDetail from './components/HorseDetail'
import JockeyDetail from './components/JockeyDetail'
import TrainerDetail from './components/TrainerDetail'
import StatusBar from './components/StatusBar'
import ActionButtons, { ProgressProvider, ProgressBar } from './components/ActionButtons'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

type NavMode = 'races' | 'ai' | 'stats' | 'favorites' | 'search'

/** ポップアップモードの情報を取得する */
function getPopupParams(): { type: string; id: string } | null {
  const params = new URLSearchParams(window.location.search)
  const type = params.get('popup')
  const id = params.get('id')
  if (type && id) return { type, id }
  return null
}

/**
 * ポップアップウィンドウ用コンポーネント
 * ナビなし、対応するDetailコンポーネントのみレンダリング
 */
function PopupApp({ type, id }: { type: string; id: string }) {
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark')

  // ダークモード設定をlocalStorageから読み取り適用
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  // ポップアップからさらにポップアップを開く（Electron IPC経由）
  const openPopup = (popupType: string, popupId: string) => {
    if (window.electronAPI?.openPopup) {
      window.electronAPI.openPopup(popupType, popupId)
    }
  }

  // ポップアップウィンドウのタイトルを更新する
  const updatePopupTitle = (title: string) => {
    if (window.electronAPI?.setPopupTitle) {
      window.electronAPI.setPopupTitle(title)
    }
    // ブラウザのタイトルも更新
    document.title = title
  }

  // ダークモード切り替え（ポップアップ内でも操作可能）
  const toggleDark = () => {
    const next = !dark
    setDark(next)
    localStorage.setItem('theme', next ? 'dark' : 'light')
  }

  return (
    <QueryClientProvider client={queryClient}>
      <div className="flex flex-col h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100" style={{ minHeight: '100vh', maxHeight: '100vh' }}>
        {/* ポップアップ用ミニヘッダー（ダークモード切替のみ） */}
        {/* ポップアップ用ヘッダー（backdrop-blurで区別をつける） */}
        <header className="flex items-center justify-end px-3 py-1 bg-white dark:bg-gray-950/90 backdrop-blur-sm border-b border-gray-200 dark:border-gray-700 shrink-0">
          <button onClick={toggleDark} className="p-1.5 rounded-lg bg-gray-800 text-gray-400 hover:text-white"
            title={dark ? 'ライトモード' : 'ダークモード'}>
            {dark ? <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" /></svg>
                 : <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" /></svg>}
          </button>
        </header>

        {/* ポップアップコンテンツ */}
        <div className="flex-1 overflow-y-auto">
          {type === 'race' && (
            <RaceDetail raceKey={id}
              onNavigateHorse={(horseId, name) => openPopup('horse', String(horseId))}
              onNavigateJockey={(jockeyId, name) => openPopup('jockey', String(jockeyId))}
              onNavigateTrainer={(trainerId, name) => openPopup('trainer', String(trainerId))}
              onTitleReady={updatePopupTitle} />
          )}
          {type === 'horse' && (
            <HorseDetail horseId={Number(id)}
              onTitleReady={updatePopupTitle} />
          )}
          {type === 'jockey' && (
            <JockeyDetail jockeyId={Number(id)}
              onTitleReady={updatePopupTitle} />
          )}
          {type === 'trainer' && (
            <TrainerDetail trainerId={Number(id)}
              onTitleReady={updatePopupTitle} />
          )}
          {!['race', 'horse', 'jockey', 'trainer'].includes(type) && (
            <div className="flex items-center justify-center h-full text-gray-500">
              不明なポップアップ種別: {type}
            </div>
          )}
        </div>
      </div>
    </QueryClientProvider>
  )
}

/** ウィンドウ内のコンテンツ */
function WindowContent({ descriptor, winId, openWindow, updateTitle }: {
  descriptor: WindowDescriptor; winId: string
  openWindow: (d: WindowDescriptor, title?: string) => void
  updateTitle: (id: string, title: string) => void
}) {
  switch (descriptor.type) {
    case 'race':
      return <RaceDetail raceKey={descriptor.raceKey}
        onNavigateHorse={(id, name) => openWindow({ type: 'horse', horseId: id }, name ?? undefined)}
        onNavigateJockey={(id, name) => openWindow({ type: 'jockey', jockeyId: id }, name ?? undefined)}
        onNavigateTrainer={(id, name) => openWindow({ type: 'trainer', trainerId: id }, name ?? undefined)}
        onTitleReady={(t) => updateTitle(winId, t)} />
    case 'horse':
      return <HorseDetail horseId={descriptor.horseId} onTitleReady={(t) => updateTitle(winId, t)} />
    case 'jockey':
      return <JockeyDetail jockeyId={descriptor.jockeyId} onTitleReady={(t) => updateTitle(winId, t)} />
    case 'trainer':
      return <TrainerDetail trainerId={descriptor.trainerId} onTitleReady={(t) => updateTitle(winId, t)} />
  }
}

export default function App() {
  // ポップアップモード判定: URLに ?popup=xxx&id=yyy がある場合
  const popupParams = getPopupParams()
  if (popupParams) {
    return <PopupApp type={popupParams.type} id={popupParams.id} />
  }

  // 通常モード
  return <MainApp />
}

/** メインアプリ（通常モード） */
function MainApp() {
  const wm = useWindowManager()
  const [dark, setDark] = useState(() => localStorage.getItem('theme') === 'dark')
  const [nav, setNav] = useState<NavMode>('races')

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  const openWin = (d: WindowDescriptor, title?: string) => wm.openWindow(d, title)
  const minimizedWindows = wm.windows.filter(w => w.minimized)

  return (
    <QueryClientProvider client={queryClient}>
      <ProgressProvider>
      <div className="flex flex-col h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100" style={{ minHeight: '100vh', maxHeight: '100vh' }}>

        {/* ヘッダー（backdrop-blurで奥行き感を出す） */}
        <header className="flex items-center justify-between px-5 py-2 bg-white dark:bg-gray-950/90 backdrop-blur-sm border-b border-gray-200 dark:border-gray-700 shrink-0 z-50">
          <div className="flex items-center gap-4">
            <h1 className="text-lg font-bold tracking-tight cursor-default">
              <span className="text-emerald-500">AI</span>
              <span className="text-white">競馬予測</span>
            </h1>

            {/* メインナビ */}
            <nav className="flex gap-1 ml-4">
              {([
                ['races', '🏇 レース', 'レースダッシュボード'],
                ['ai', '🤖 AI予想', 'AI予想・期待値分析'],
                ['stats', '📊 統計DB', 'データベース・統計分析'],
                ['favorites', '⭐ お気に入り', 'お気に入り馬・出走予定'],
                ['search', '🔍 検索', '馬・騎手・調教師・レース名で検索'],
              ] as [NavMode, string, string][]).map(([key, label, tip]) => (
                <button key={key} onClick={() => setNav(key)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    nav === key ? 'bg-emerald-600 text-white' : 'text-gray-400 hover:text-white hover:bg-gray-800'
                  }`} title={tip}>{label}</button>
              ))}
            </nav>

            {/* ウィンドウ操作 */}
            {wm.windows.length > 0 && (
              <div className="flex gap-1 ml-2 pl-2 border-l border-gray-700">
                <button onClick={wm.tileWindows} className="px-2 py-1 text-[10px] rounded bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700" title="タイル整列">📐 整列</button>
                <button onClick={wm.cascadeWindows} className="px-2 py-1 text-[10px] rounded bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700" title="カスケード">📋 重ねる</button>
                <button onClick={wm.closeAll} className="px-2 py-1 text-[10px] rounded bg-gray-800 text-gray-400 hover:text-red-400 hover:bg-gray-700" title="全閉じ">✕</button>
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            <ActionButtons />
            <button onClick={() => setDark(!dark)} className="p-1.5 rounded-lg bg-gray-800 text-gray-400 hover:text-white"
              title={dark ? 'ライトモード' : 'ダークモード'}>
              {dark ? <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" /></svg>
                   : <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" /></svg>}
            </button>
            <StatusBar />
          </div>
        </header>
        <ProgressBar />

        {/* メインエリア */}
        <div className="flex-1 relative" style={{ overflow: 'hidden', minHeight: 0 }}>
          {/* 背景コンテンツ（スクロール可能） */}
          <div className="absolute inset-0 overflow-y-auto">
            {nav === 'races' && <Dashboard onOpenRace={(rk, t) => openWin({ type: 'race', raceKey: rk }, t)} />}
            {nav === 'ai' && <AIPredictionView onOpenRace={(rk, t) => openWin({ type: 'race', raceKey: rk }, t)} />}
            {nav === 'stats' && <StatsView />}
            {nav === 'favorites' && <FavoritesView onOpenHorse={(id, name) => openWin({ type: 'horse', horseId: id }, name)} onOpenRace={(rk, t) => openWin({ type: 'race', raceKey: rk }, t)} />}
            {nav === 'search' && <HorseSearchView
              onOpenHorse={(id, name) => openWin({ type: 'horse', horseId: id }, name)}
              onOpenJockey={(id, name) => openWin({ type: 'jockey', jockeyId: id }, name)}
              onOpenTrainer={(id, name) => openWin({ type: 'trainer', trainerId: id }, name)}
              onOpenRace={(rk, t) => openWin({ type: 'race', raceKey: rk }, t)}
            />}
          </div>

          {/* フローティングウィンドウ群 */}
          {wm.windows.map(win => (
            <FloatingWindow key={win.id} win={win}
              onFocus={() => wm.focusWindow(win.id)}
              onClose={() => wm.closeWindow(win.id)}
              onMove={(x, y) => wm.moveWindow(win.id, x, y)}
              onResize={(w, h) => wm.resizeWindow(win.id, w, h)}
              onMoveAndResize={(x, y, w, h) => wm.moveAndResizeWindow(win.id, x, y, w, h)}
              onMinimize={() => wm.toggleMinimize(win.id)}
              onMaximize={() => wm.toggleMaximize(win.id)}>
              <WindowContent descriptor={win.descriptor} winId={win.id} openWindow={openWin} updateTitle={wm.updateTitle} />
            </FloatingWindow>
          ))}

          {/* 最小化タスクバー（ボーダー明確化） */}
          {minimizedWindows.length > 0 && (
            <div className="absolute bottom-0 left-0 right-0 flex gap-1 px-2 py-1 bg-white dark:bg-gray-950/90 backdrop-blur-sm border-t border-gray-200 dark:border-gray-700 z-[9999]">
              {minimizedWindows.map(w => (
                <button key={w.id} onClick={() => wm.toggleMinimize(w.id)}
                  className="px-3 py-1 text-xs rounded bg-gray-800 text-gray-400 hover:text-white hover:bg-gray-700 truncate max-w-[180px]">
                  {w.title}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      </ProgressProvider>
    </QueryClientProvider>
  )
}
