/**
 * 統合検索画面 — 馬・騎手・調教師・レースを横断検索
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { searchHorses, searchJockeys, searchTrainers, searchRaces } from '../api/client'
import EmptyState from './EmptyState'

/** 検索履歴をlocalStorageで管理するフック（直近10件） */
const HISTORY_KEY = 'searchHistory'
const MAX_HISTORY = 10

function useSearchHistory() {
  const [history, setHistory] = useState<string[]>(() => {
    try {
      const stored = localStorage.getItem(HISTORY_KEY)
      return stored ? JSON.parse(stored) : []
    } catch { return [] }
  })

  // 検索クエリを履歴に追加
  const addHistory = useCallback((q: string) => {
    setHistory(prev => {
      const filtered = prev.filter(h => h !== q)
      const next = [q, ...filtered].slice(0, MAX_HISTORY)
      localStorage.setItem(HISTORY_KEY, JSON.stringify(next))
      return next
    })
  }, [])

  // 履歴クリア
  const clearHistory = useCallback(() => {
    localStorage.removeItem(HISTORY_KEY)
    setHistory([])
  }, [])

  return { history, addHistory, clearHistory }
}

interface Props {
  onOpenHorse: (horseId: number, name?: string) => void
  onOpenJockey?: (jockeyId: number, name?: string) => void
  onOpenTrainer?: (trainerId: number, name?: string) => void
  onOpenRace?: (raceKey: string, title?: string) => void
}

const SEX_L: Record<number, string> = { 1: '牡', 2: '牝', 3: '騸' }
const TRACK_L: Record<number, string> = { 1: '芝', 2: 'ダ', 3: '障' }
const GRADE_L: Record<number, string> = { 1: 'G1', 2: 'G2', 3: 'G3', 4: '重賞', 5: 'OP' }
const GRADE_C: Record<number, string> = { 1: 'bg-yellow-400 text-yellow-900', 2: 'bg-red-400 text-white', 3: 'bg-green-400 text-white' }
const VENUE: Record<string, string> = {
  '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
  '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉',
}

type SearchCategory = 'all' | 'horse' | 'jockey' | 'trainer' | 'race'

export default function HorseSearchView({ onOpenHorse, onOpenJockey, onOpenTrainer, onOpenRace }: Props) {
  const [query, setQuery] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [category, setCategory] = useState<SearchCategory>('all')
  const [showHistory, setShowHistory] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const historyRef = useRef<HTMLDivElement>(null)
  const { history, addHistory, clearHistory } = useSearchHistory()

  // 検索バー外クリックで履歴ドロップダウンを閉じる
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (historyRef.current && !historyRef.current.contains(e.target as Node) &&
          inputRef.current && !inputRef.current.contains(e.target as Node)) {
        setShowHistory(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const enabled = searchTerm.length > 0
  const searchHorse = category === 'all' || category === 'horse'
  const searchJockey = category === 'all' || category === 'jockey'
  const searchTrainerQ = category === 'all' || category === 'trainer'
  const searchRaceQ = category === 'all' || category === 'race'

  const { data: horses, isLoading: hl } = useQuery({ queryKey: ['search-horse', searchTerm], queryFn: () => searchHorses(searchTerm), enabled: enabled && searchHorse })
  const { data: jockeys, isLoading: jl } = useQuery({ queryKey: ['search-jockey', searchTerm], queryFn: () => searchJockeys(searchTerm), enabled: enabled && searchJockey })
  const { data: trainers, isLoading: tl } = useQuery({ queryKey: ['search-trainer', searchTerm], queryFn: () => searchTrainers(searchTerm), enabled: enabled && searchTrainerQ })
  const { data: races, isLoading: rll } = useQuery({ queryKey: ['search-race', searchTerm], queryFn: () => searchRaces(searchTerm), enabled: enabled && searchRaceQ })

  // 検索実行＋履歴保存
  const doSearch = () => {
    const trimmed = query.trim()
    if (trimmed) {
      setSearchTerm(trimmed)
      addHistory(trimmed)
      setShowHistory(false)
    }
  }

  // 履歴アイテムクリックで再検索
  const doHistorySearch = (q: string) => {
    setQuery(q)
    setSearchTerm(q)
    addHistory(q)
    setShowHistory(false)
  }

  const isLoading = hl || jl || tl || rll
  const hasResults = (horses?.length ?? 0) + (jockeys?.length ?? 0) + (trainers?.length ?? 0) + (races?.length ?? 0) > 0

  const CATS: { key: SearchCategory; label: string; icon: string }[] = [
    { key: 'all', label: 'すべて', icon: '🔍' },
    { key: 'horse', label: '馬', icon: '🐴' },
    { key: 'jockey', label: '騎手', icon: '🧑' },
    { key: 'trainer', label: '調教師', icon: '👔' },
    { key: 'race', label: 'レース', icon: '🏇' },
  ]

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-1">🔍 検索</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">馬名・騎手名・調教師名・レース名で横断検索</p>
      </div>

      {/* 検索バー + 履歴ドロップダウン */}
      <div className="relative mb-4">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') doSearch() }}
            onFocus={() => { if (history.length > 0) setShowHistory(true) }}
            placeholder="検索キーワードを入力（例: ドウデュース、ルメール、天皇賞）"
            className="flex-1 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-xl px-4 py-3 text-gray-900 dark:text-white text-sm placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
          />
          <button onClick={doSearch}
            className="px-6 py-3 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-500 transition-colors">
            検索
          </button>
        </div>

        {/* 検索履歴ドロップダウン */}
        {showHistory && history.length > 0 && (
          <div
            ref={historyRef}
            className="absolute top-full left-0 right-16 mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg z-50 overflow-hidden"
          >
            <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-gray-700">
              <span className="text-xs text-gray-500">検索履歴</span>
              <button
                onClick={() => { clearHistory(); setShowHistory(false) }}
                className="text-xs text-red-500 dark:text-red-400 hover:text-red-600 dark:hover:text-red-300 transition-colors"
              >
                履歴クリア
              </button>
            </div>
            {history.map((h, i) => (
              <button
                key={i}
                onClick={() => doHistorySearch(h)}
                className="w-full text-left px-4 py-2.5 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors flex items-center gap-2"
              >
                <span className="text-gray-400 dark:text-gray-500 text-xs">🕐</span>
                {h}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* カテゴリフィルター */}
      <div className="flex gap-1 mb-6">
        {CATS.map(c => (
          <button key={c.key} onClick={() => setCategory(c.key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              category === c.key ? 'bg-emerald-600 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-200 dark:hover:bg-gray-700'
            }`}>{c.icon} {c.label}</button>
        ))}
      </div>

      {isLoading && <div className="text-gray-500 text-center py-8">検索中...</div>}

      {searchTerm && !isLoading && !hasResults && (
        <EmptyState
          icon="🔍"
          title={`「${searchTerm}」に該当する結果がありません`}
          description="別のキーワードで検索するか、カテゴリフィルターを変更してみてください。"
        />
      )}

      <div className="space-y-6">
        {/* === 馬の結果 === */}
        {horses && horses.length > 0 && (
          <section>
            <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
              <span className="w-1 h-4 bg-emerald-500 rounded-full" />
              🐴 馬 <span className="text-xs text-gray-500 font-normal">{horses.length}件</span>
            </h3>
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
              <table className="w-full text-sm">
                <thead><tr className="text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  <th className="px-4 py-2 text-left">馬名</th>
                  <th className="px-3 py-2 text-center">性</th>
                  <th className="px-3 py-2 text-left">父</th>
                  <th className="px-3 py-2 text-right">成績</th>
                  <th className="px-3 py-2 text-right">賞金</th>
                </tr></thead>
                <tbody>
                  {horses.map((h: any) => (
                    <tr key={h.id} className="border-t border-gray-100 dark:border-gray-700/50 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/30"
                      onClick={() => onOpenHorse(h.id, h.name)}>
                      <td className="px-4 py-2.5"><span className="text-emerald-600 dark:text-emerald-400 font-medium">{h.name}</span></td>
                      <td className="px-3 py-2.5 text-center text-gray-500 dark:text-gray-400">{SEX_L[h.sex] ?? '-'}</td>
                      <td className="px-3 py-2.5 text-gray-500 dark:text-gray-400">{h.father ?? '-'}</td>
                      <td className="px-3 py-2.5 text-right text-gray-700 dark:text-gray-300">{h.total_wins ?? 0}勝/{h.total_races ?? 0}戦</td>
                      <td className="px-3 py-2.5 text-right text-gray-500 dark:text-gray-400">
                        {h.total_earnings ? (h.total_earnings >= 10000 ? `${(h.total_earnings / 10000).toFixed(1)}億` : `${h.total_earnings.toLocaleString()}万`) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* === 騎手の結果 === */}
        {jockeys && jockeys.length > 0 && (
          <section>
            <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
              <span className="w-1 h-4 bg-blue-500 rounded-full" />
              🧑 騎手 <span className="text-xs text-gray-500 font-normal">{jockeys.length}件</span>
            </h3>
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
              <table className="w-full text-sm">
                <thead><tr className="text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  <th className="px-4 py-2 text-left">騎手名</th>
                  <th className="px-3 py-2 text-center">所属</th>
                  <th className="px-3 py-2 text-right">勝利数</th>
                  <th className="px-3 py-2 text-right">出走数</th>
                  <th className="px-3 py-2 text-right">勝率</th>
                </tr></thead>
                <tbody>
                  {jockeys.map((j: any) => (
                    <tr key={j.id} className="border-t border-gray-100 dark:border-gray-700/50 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/30"
                      onClick={() => onOpenJockey?.(j.id, j.name)}>
                      <td className="px-4 py-2.5"><span className="text-blue-600 dark:text-blue-400 font-medium">{j.name}</span></td>
                      <td className="px-3 py-2.5 text-center">
                        {j.belong && <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">{j.belong}</span>}
                      </td>
                      <td className="px-3 py-2.5 text-right text-gray-700 dark:text-gray-300">{j.total_1st}勝</td>
                      <td className="px-3 py-2.5 text-right text-gray-500 dark:text-gray-400">{j.total_races}戦</td>
                      <td className="px-3 py-2.5 text-right">
                        <span className={j.win_rate >= 15 ? 'text-emerald-600 dark:text-emerald-400 font-bold' : 'text-gray-500 dark:text-gray-400'}>{j.win_rate}%</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* === 調教師の結果 === */}
        {trainers && trainers.length > 0 && (
          <section>
            <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
              <span className="w-1 h-4 bg-purple-500 rounded-full" />
              👔 調教師 <span className="text-xs text-gray-500 font-normal">{trainers.length}件</span>
            </h3>
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
              <table className="w-full text-sm">
                <thead><tr className="text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  <th className="px-4 py-2 text-left">調教師名</th>
                  <th className="px-3 py-2 text-center">所属</th>
                  <th className="px-3 py-2 text-right">勝利数</th>
                  <th className="px-3 py-2 text-right">出走数</th>
                  <th className="px-3 py-2 text-right">勝率</th>
                </tr></thead>
                <tbody>
                  {trainers.map((t: any) => (
                    <tr key={t.id} className="border-t border-gray-100 dark:border-gray-700/50 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/30"
                      onClick={() => onOpenTrainer?.(t.id, t.name)}>
                      <td className="px-4 py-2.5"><span className="text-purple-600 dark:text-purple-400 font-medium">{t.name}</span></td>
                      <td className="px-3 py-2.5 text-center">
                        {t.belong && <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">{t.belong}</span>}
                      </td>
                      <td className="px-3 py-2.5 text-right text-gray-700 dark:text-gray-300">{t.total_1st}勝</td>
                      <td className="px-3 py-2.5 text-right text-gray-500 dark:text-gray-400">{t.total_races}戦</td>
                      <td className="px-3 py-2.5 text-right">
                        <span className={t.win_rate >= 12 ? 'text-emerald-600 dark:text-emerald-400 font-bold' : 'text-gray-500 dark:text-gray-400'}>{t.win_rate}%</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* === レースの結果 === */}
        {races && races.length > 0 && (
          <section>
            <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
              <span className="w-1 h-4 bg-yellow-500 rounded-full" />
              🏇 レース <span className="text-xs text-gray-500 font-normal">{races.length}件</span>
            </h3>
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
              <table className="w-full text-sm">
                <thead><tr className="text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  <th className="px-4 py-2 text-left">レース名</th>
                  <th className="px-3 py-2 text-center">日付</th>
                  <th className="px-3 py-2 text-center">場</th>
                  <th className="px-3 py-2 text-center">距離</th>
                  <th className="px-3 py-2 text-center">頭数</th>
                </tr></thead>
                <tbody>
                  {races.map((r: any) => (
                    <tr key={r.race_key} className="border-t border-gray-100 dark:border-gray-700/50 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/30"
                      onClick={() => onOpenRace?.(r.race_key, `${VENUE[r.venue_code] ?? ''}${r.race_num}R ${r.race_name ?? ''}`)}>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          {r.grade != null && GRADE_L[r.grade] && (
                            <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${GRADE_C[r.grade] ?? 'bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300'}`}>{GRADE_L[r.grade]}</span>
                          )}
                          <span className="text-yellow-600 dark:text-yellow-400 font-medium">{r.race_name ?? `${r.race_num}R`}</span>
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-center text-gray-500 dark:text-gray-400">{r.race_date}</td>
                      <td className="px-3 py-2.5 text-center text-gray-500 dark:text-gray-400">{VENUE[r.venue_code] ?? r.venue_code}</td>
                      <td className="px-3 py-2.5 text-center text-gray-500 dark:text-gray-400">{TRACK_L[r.track_type]}{r.distance}m</td>
                      <td className="px-3 py-2.5 text-center text-gray-500 dark:text-gray-400">{r.horse_count ?? '-'}頭</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>

      {!searchTerm && (
        <div className="text-center text-gray-400 dark:text-gray-600 py-16">
          <div className="text-4xl mb-3 opacity-30">🔍</div>
          <div className="text-sm text-gray-500">キーワードを入力して検索</div>
          <div className="text-xs text-gray-400 dark:text-gray-500 mt-2">馬名・騎手名・調教師名・レース名に対応</div>
        </div>
      )}
    </div>
  )
}
