/**
 * データ最新化 + AI推奨生成ボタン
 * 進捗はヘッダー下のインラインバーで表示（モーダルなし）
 */
import { useState, useEffect, useRef, createContext, useContext } from 'react'
import { triggerDataSync, fetchSyncStatus, triggerAIPredictions, fetchPredictStatus } from '../api/client'

type TaskStatus = 'idle' | 'running' | 'success' | 'error'

// 進捗バーの状態をApp全体で共有するためのContext
interface ProgressState {
  visible: boolean
  title: string
  progress: { current: number; total: number }
  done: boolean
  result: { success: number; errors: number } | null
}
const ProgressContext = createContext<{
  state: ProgressState
  setState: (s: ProgressState) => void
}>({ state: { visible: false, title: '', progress: { current: 0, total: 0 }, done: false, result: null }, setState: () => {} })

export function useProgressBar() { return useContext(ProgressContext) }
export function ProgressProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<ProgressState>({ visible: false, title: '', progress: { current: 0, total: 0 }, done: false, result: null })
  return <ProgressContext.Provider value={{ state, setState }}>{children}</ProgressContext.Provider>
}

/** ヘッダー直下に表示する進捗バー */
export function ProgressBar() {
  const { state } = useProgressBar()
  if (!state.visible) return null

  const pct = state.progress.total > 0
    ? Math.round((state.progress.current / state.progress.total) * 100)
    : 0

  return (
    <div className="bg-gray-900 border-b border-gray-700 px-5 py-2 shrink-0">
      <div className="flex items-center justify-between text-xs mb-1">
        <div className="flex items-center gap-2">
          {!state.done && (
            <svg className="w-3.5 h-3.5 animate-spin text-emerald-400" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          )}
          {state.done && (
            <svg className="w-3.5 h-3.5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
          )}
          <span className="text-gray-300 font-medium">{state.title}</span>
        </div>
        <div className="flex items-center gap-3 text-gray-400">
          {state.progress.total > 0 && <span>{state.progress.current}/{state.progress.total}</span>}
          {state.progress.total > 0 && <span>{pct}%</span>}
          {state.done && state.result && (
            <span>
              <span className="text-emerald-400">{state.result.success}件成功</span>
              {state.result.errors > 0 && <span className="text-red-400 ml-2">{state.result.errors}件エラー</span>}
            </span>
          )}
        </div>
      </div>
      {state.progress.total > 0 && (
        <div className="w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${state.done ? 'bg-emerald-400' : 'bg-emerald-500'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  )
}

export default function ActionButtons() {
  const [syncStatus, setSyncStatus] = useState<TaskStatus>('idle')
  const [predictStatus, setPredictStatus] = useState<TaskStatus>('idle')
  const [syncMessage, setSyncMessage] = useState('')
  const [predictMessage, setPredictMessage] = useState('')
  const [showScopeMenu, setShowScopeMenu] = useState(false)
  const { setState: setProgress } = useProgressBar()

  const syncPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const predictPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ドロップダウン外クリックで閉じる
  useEffect(() => {
    if (!showScopeMenu) return
    const close = () => setShowScopeMenu(false)
    const timer = setTimeout(() => document.addEventListener('click', close), 0)
    return () => { clearTimeout(timer); document.removeEventListener('click', close) }
  }, [showScopeMenu])

  // 同期ポーリング
  useEffect(() => {
    if (syncStatus === 'running') {
      syncPollRef.current = setInterval(async () => {
        try {
          const s = await fetchSyncStatus()
          if (!s.running) {
            const ok = s.last_result?.status === 'success'
            setSyncStatus(ok ? 'success' : 'error')
            setSyncMessage(ok ? '完了' : 'エラー')
            setProgress({ visible: true, title: ok ? 'データ最新化 完了' : 'データ最新化 エラー', progress: { current: 0, total: 0 }, done: true, result: null })
            if (syncPollRef.current) clearInterval(syncPollRef.current)
            setTimeout(() => { setSyncStatus('idle'); setSyncMessage(''); setProgress(p => ({ ...p, visible: false })) }, 5000)
          }
        } catch {}
      }, 3000)
    }
    return () => { if (syncPollRef.current) clearInterval(syncPollRef.current) }
  }, [syncStatus])

  // 予測ポーリング
  useEffect(() => {
    if (predictStatus === 'running') {
      predictPollRef.current = setInterval(async () => {
        try {
          const s = await fetchPredictStatus()
          if (s.log) {
            const lines = s.log.trim().split('\n')
            const last = lines[lines.length - 1] || ''
            const m = last.match(/\[(\d+)\/(\d+)\]/)
            if (m) {
              const cur = parseInt(m[1]), tot = parseInt(m[2])
              setPredictMessage(`${cur}/${tot}`)
              setProgress(prev => ({ ...prev, progress: { current: cur, total: tot } }))
            }
          }
          if (!s.running && s.last_result) {
            const ok = s.last_result.status === 'success'
            setPredictStatus(ok ? 'success' : 'error')
            setPredictMessage(ok ? `${s.last_result.success}件` : 'エラー')
            setProgress({
              visible: true,
              title: ok ? 'AI推奨生成 完了' : 'AI推奨生成 エラー',
              progress: { current: s.last_result.success + s.last_result.errors, total: s.last_result.success + s.last_result.errors },
              done: true,
              result: { success: s.last_result.success || 0, errors: s.last_result.errors || 0 },
            })
            if (predictPollRef.current) clearInterval(predictPollRef.current)
            setTimeout(() => { setPredictStatus('idle'); setPredictMessage(''); setProgress(p => ({ ...p, visible: false })) }, 8000)
          }
        } catch {}
      }, 2000)
    }
    return () => { if (predictPollRef.current) clearInterval(predictPollRef.current) }
  }, [predictStatus])

  // データ最新化
  const handleSync = async () => {
    if (syncStatus === 'running') return
    setSyncStatus('running')
    setSyncMessage('同期中...')
    setProgress({ visible: true, title: 'データ最新化中...', progress: { current: 0, total: 0 }, done: false, result: null })
    try { await triggerDataSync() } catch {
      setSyncStatus('error'); setSyncMessage('接続エラー')
      setProgress({ visible: true, title: 'データ最新化 接続エラー', progress: { current: 0, total: 0 }, done: true, result: null })
      setTimeout(() => { setSyncStatus('idle'); setSyncMessage(''); setProgress(p => ({ ...p, visible: false })) }, 5000)
    }
  }

  // AI推奨生成
  const handlePredict = async (scope: 'week' | 'month' | string) => {
    if (predictStatus === 'running') return
    setShowScopeMenu(false)
    const label = scope === 'week' ? '今週' : scope === 'month' ? '今月' : scope
    setPredictStatus('running')
    setPredictMessage(`${label}...`)
    setProgress({ visible: true, title: `AI推奨生成（${label}）`, progress: { current: 0, total: 0 }, done: false, result: null })
    try {
      const res = await triggerAIPredictions(scope)
      if (res.status !== 'started' && res.status !== 'already_running') {
        setPredictStatus('error'); setPredictMessage('エラー')
        setProgress({ visible: true, title: 'AI推奨生成 エラー', progress: { current: 0, total: 0 }, done: true, result: null })
        setTimeout(() => { setPredictStatus('idle'); setPredictMessage(''); setProgress(p => ({ ...p, visible: false })) }, 5000)
      }
    } catch {
      setPredictStatus('error'); setPredictMessage('接続エラー')
      setProgress({ visible: true, title: 'AI推奨生成 接続エラー', progress: { current: 0, total: 0 }, done: true, result: null })
      setTimeout(() => { setPredictStatus('idle'); setPredictMessage(''); setProgress(p => ({ ...p, visible: false })) }, 5000)
    }
  }

  return (
    <div className="flex items-center gap-1.5">
      {/* データ最新化 */}
      <button onClick={handleSync} disabled={syncStatus === 'running' || predictStatus === 'running'}
        className={`flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-medium rounded-lg transition-all ${
          syncStatus === 'running' ? 'bg-blue-900/50 text-blue-300 cursor-wait'
          : syncStatus === 'success' ? 'bg-green-900/50 text-green-300'
          : syncStatus === 'error' ? 'bg-red-900/50 text-red-300'
          : 'bg-blue-600/80 text-white hover:bg-blue-500'
        }`} title="RACE/DIFN差分取得 + speed_index再計算">
        <SpinnerOrIcon status={syncStatus} icon="sync" />
        {syncMessage || 'データ最新化'}
      </button>

      {/* AI推奨生成（ドロップダウン） */}
      <div className="relative">
        <button onClick={() => predictStatus !== 'running' && setShowScopeMenu(!showScopeMenu)}
          disabled={syncStatus === 'running' || predictStatus === 'running'}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-medium rounded-lg transition-all ${
            predictStatus === 'running' ? 'bg-emerald-900/50 text-emerald-300 cursor-wait'
            : predictStatus === 'success' ? 'bg-green-900/50 text-green-300'
            : predictStatus === 'error' ? 'bg-red-900/50 text-red-300'
            : 'bg-emerald-600/80 text-white hover:bg-emerald-500'
          }`} title="AI予測を一括生成">
          <SpinnerOrIcon status={predictStatus} icon="ai" />
          {predictMessage || 'AI推奨生成'}
          {predictStatus === 'idle' && (
            <svg className="w-3 h-3 ml-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
            </svg>
          )}
        </button>
        {showScopeMenu && (
          <div className="absolute right-0 top-full mt-1 w-40 bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-600 py-1 z-50">
            <button onClick={() => handlePredict('week')} className="w-full text-left px-3 py-2 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200">今週の開催のみ</button>
            <button onClick={() => handlePredict('month')} className="w-full text-left px-3 py-2 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200">今月すべて</button>
            <div className="border-t border-gray-200 dark:border-gray-600 my-1" />
            <button onClick={() => {
              const d = prompt('日付を入力 (YYYY-MM-DD)')
              if (d && /^\d{4}-\d{2}-\d{2}$/.test(d)) handlePredict(d)
              else if (d) alert('YYYY-MM-DD形式で入力してください')
              else setShowScopeMenu(false)
            }} className="w-full text-left px-3 py-2 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200">日付を指定...</button>
          </div>
        )}
      </div>
    </div>
  )
}

function SpinnerOrIcon({ status, icon }: { status: TaskStatus; icon: 'sync' | 'ai' }) {
  if (status === 'running') return (
    <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
  if (status === 'success') return (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  )
  if (icon === 'sync') return (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  )
  return (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
    </svg>
  )
}
