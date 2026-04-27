/**
 * 調教師プロフィールページ — 条件別成績・直近成績を表示
 */
import { useState, useMemo, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchTrainer, fetchTrainerStats, fetchTrainerRecent } from '../api/client'
import ErrorBanner from './ErrorBanner'
import EmptyState from './EmptyState'

// --- 型定義 ---
interface Props {
  trainerId: number
  onBack?: () => void
  onTitleReady?: (title: string) => void
}

interface TrainerInfo {
  id: number
  name: string
  name_kana: string
  belong: string
  total_1st: number
  total_races: number
  win_rate: number
}

interface StatRow {
  label: string
  runs: number
  wins: number
  top3: number
}

interface TrainerStatsData {
  by_track: StatRow[]
  by_distance: StatRow[]
  by_venue: StatRow[]
}

interface RecentDay {
  date: string
  runs: number
  wins: number
  top3: number
}

// --- 所属バッジの色分け ---
function belongColor(belong: string): string {
  if (belong.includes('美浦')) return 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300'
  if (belong.includes('栗東')) return 'bg-orange-100 dark:bg-orange-900/50 text-orange-700 dark:text-orange-300'
  return 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
}

// --- 成績テーブルコンポーネント ---
function StatsTable({ title, rows }: { title: string; rows: StatRow[] }) {
  if (rows.length === 0) {
    return (
      <div className="mb-4">
        <h4 className="text-xs font-bold text-gray-500 mb-2">{title}</h4>
        <div className="text-xs text-gray-400">データなし</div>
      </div>
    )
  }
  return (
    <div className="mb-4">
      <h4 className="text-xs font-bold text-gray-500 mb-2">{title}</h4>
      {/* 条件別成績テーブル: 横スクロール対応 */}
      <div className="overflow-x-auto">
      <table className="min-w-[500px] w-full text-sm">
        <thead>
          <tr className="text-gray-400 text-xs border-b border-gray-100 dark:border-gray-700">
            <th className="px-3 py-2 text-left">条件</th>
            <th className="px-3 py-2 text-right">出走数</th>
            <th className="px-3 py-2 text-right">勝利</th>
            <th className="px-3 py-2 text-right">複勝</th>
            <th className="px-3 py-2 text-right">勝率%</th>
            <th className="px-3 py-2 text-right">複勝率%</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const winRate = r.runs > 0 ? (r.wins / r.runs) * 100 : 0
            const top3Rate = r.runs > 0 ? (r.top3 / r.runs) * 100 : 0
            return (
              <tr key={r.label} className="border-t border-gray-50 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                <td className="px-3 py-2 text-gray-700 dark:text-gray-200 font-medium">{r.label}</td>
                <td className="px-3 py-2 text-right text-gray-600 dark:text-gray-300 tabular-nums">{r.runs}</td>
                <td className="px-3 py-2 text-right text-gray-600 dark:text-gray-300 tabular-nums">{r.wins}</td>
                <td className="px-3 py-2 text-right text-gray-600 dark:text-gray-300 tabular-nums">{r.top3}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  <span className={winRate >= 20 ? 'text-emerald-600 font-bold' : winRate >= 10 ? 'text-gray-700 dark:text-gray-200' : 'text-gray-400'}>
                    {winRate.toFixed(1)}
                  </span>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  <span className={top3Rate >= 40 ? 'text-emerald-600 font-bold' : top3Rate >= 25 ? 'text-gray-700 dark:text-gray-200' : 'text-gray-400'}>
                    {top3Rate.toFixed(1)}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      </div>
    </div>
  )
}

// --- メインコンポーネント ---
export default function TrainerDetail({ trainerId, onBack, onTitleReady }: Props) {
  const [tab, setTab] = useState<'stats' | 'recent'>('stats')

  // データ取得
  const { data: trainer, isLoading: tl, isError: tErr, refetch: refetchTrainer } = useQuery<TrainerInfo>({
    queryKey: ['trainer', trainerId],
    queryFn: () => fetchTrainer(trainerId),
    retry: 1,
  })
  const { data: stats, isLoading: sl } = useQuery<TrainerStatsData>({
    queryKey: ['trainerStats', trainerId],
    queryFn: () => fetchTrainerStats(trainerId),
  })
  const { data: recent, isLoading: rcl } = useQuery<RecentDay[]>({
    queryKey: ['trainerRecent', trainerId],
    queryFn: () => fetchTrainerRecent(trainerId, 90),
  })

  // タブタイトル更新
  useEffect(() => {
    if (trainer?.name && onTitleReady) onTitleReady(trainer.name)
  }, [trainer?.name, onTitleReady])

  // 直近30日/90日の集計
  const recentSummary = useMemo(() => {
    if (!recent || recent.length === 0) return null
    const now = new Date()
    const d30 = new Date(now.getTime() - 30 * 86400000)
    const d90 = new Date(now.getTime() - 90 * 86400000)

    const last30 = recent.filter((r) => new Date(r.date) >= d30)
    const last90 = recent.filter((r) => new Date(r.date) >= d90)

    const agg = (rows: RecentDay[]) => {
      const runs = rows.reduce((s, r) => s + r.runs, 0)
      const wins = rows.reduce((s, r) => s + r.wins, 0)
      const top3 = rows.reduce((s, r) => s + r.top3, 0)
      return { runs, wins, top3 }
    }
    return { last30: agg(last30), last90: agg(last90) }
  }, [recent])

  // ローディング
  if (tl || sl || rcl) {
    return <div className="flex items-center justify-center h-full text-gray-400">読み込み中...</div>
  }
  if (tErr) {
    return <div className="p-5"><ErrorBanner message="調教師情報の取得に失敗しました" onRetry={() => refetchTrainer()} /></div>
  }
  if (!trainer) {
    return <div className="p-5"><EmptyState icon="👔" title="調教師情報なし" description="指定された調教師のデータが存在しません。" /></div>
  }

  return (
    <div className="max-w-4xl mx-auto p-5 space-y-4">

      {/* 戻るボタン */}
      <button
        onClick={onBack}
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-emerald-600 transition-colors"
      >
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        戻る
      </button>

      {/* ヘッダー: 名前 + 所属バッジ */}
      <div>
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-bold text-gray-800 dark:text-gray-100">{trainer.name}</h2>
          <span className={`px-2 py-0.5 text-xs font-bold rounded ${belongColor(trainer.belong)}`}>
            {trainer.belong}
          </span>
        </div>
        {trainer.name_kana && (
          <div className="text-sm text-gray-400 mt-0.5">{trainer.name_kana}</div>
        )}
      </div>

      {/* サマリーカード */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-200 dark:border-gray-700 shadow-sm">
          <div className="text-xs text-gray-400 mb-1">通算出走数</div>
          <div className="text-2xl font-bold text-gray-800 dark:text-gray-100 tabular-nums">{trainer.total_races.toLocaleString()}</div>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-200 dark:border-gray-700 shadow-sm">
          <div className="text-xs text-gray-400 mb-1">通算勝利数</div>
          <div className="text-2xl font-bold text-emerald-600 tabular-nums">{trainer.total_1st.toLocaleString()}</div>
        </div>
        <div className="bg-white dark:bg-gray-800 rounded-xl p-4 border border-gray-200 dark:border-gray-700 shadow-sm">
          <div className="text-xs text-gray-400 mb-1">勝率</div>
          <div className="text-2xl font-bold text-gray-800 dark:text-gray-100 tabular-nums">
            {(trainer.win_rate * 100).toFixed(1)}
            <span className="text-sm text-gray-400 ml-0.5">%</span>
          </div>
        </div>
      </div>

      {/* タブ切替 */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        {([
          { key: 'stats' as const, label: '条件別成績' },
          { key: 'recent' as const, label: '直近成績' },
        ]).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t.key
                ? 'border-emerald-500 text-emerald-600'
                : 'border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ====== 条件別成績タブ ====== */}
      {tab === 'stats' && stats && (
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-5 shadow-sm space-y-2">
          <StatsTable title="コース別（芝/ダート）" rows={stats.by_track} />
          <StatsTable title="距離別" rows={stats.by_distance} />
          <StatsTable title="競馬場別" rows={stats.by_venue} />
        </div>
      )}

      {/* ====== 直近成績タブ ====== */}
      {tab === 'recent' && (
        <div className="space-y-4">

          {/* 直近30日/90日サマリー */}
          {recentSummary && (
            <div className="grid grid-cols-2 gap-3">
              {([
                { label: '直近30日', data: recentSummary.last30 },
                { label: '直近90日', data: recentSummary.last90 },
              ]).map((period) => {
                const winRate = period.data.runs > 0 ? (period.data.wins / period.data.runs) * 100 : 0
                const top3Rate = period.data.runs > 0 ? (period.data.top3 / period.data.runs) * 100 : 0
                return (
                  <div key={period.label} className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm">
                    <div className="text-xs font-bold text-gray-500 mb-3">{period.label}</div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <div className="text-xs text-gray-400">出走数</div>
                        <div className="text-lg font-bold text-gray-800 dark:text-gray-100 tabular-nums">{period.data.runs}</div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-400">勝利</div>
                        <div className="text-lg font-bold text-emerald-600 tabular-nums">{period.data.wins}</div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-400">勝率</div>
                        <div className={`text-lg font-bold tabular-nums ${winRate >= 15 ? 'text-emerald-600' : 'text-gray-700 dark:text-gray-200'}`}>
                          {winRate.toFixed(1)}%
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-400">複勝率</div>
                        <div className={`text-lg font-bold tabular-nums ${top3Rate >= 35 ? 'text-emerald-600' : 'text-gray-700 dark:text-gray-200'}`}>
                          {top3Rate.toFixed(1)}%
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {/* 日別成績一覧 */}
          {recent && recent.length > 0 ? (
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm">
              <div className="px-5 py-3 border-b border-gray-100 dark:border-gray-700">
                <h4 className="text-xs font-bold text-gray-500">日別成績（直近90日）</h4>
              </div>
              {/* 日別成績テーブル: 横スクロール対応 */}
              <div className="overflow-x-auto">
              <table className="min-w-[450px] w-full text-sm">
                <thead>
                  <tr className="text-gray-400 text-xs border-b border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/40">
                    <th className="px-4 py-2 text-left">日付</th>
                    <th className="px-4 py-2 text-right">出走数</th>
                    <th className="px-4 py-2 text-right">勝利</th>
                    <th className="px-4 py-2 text-right">複勝圏</th>
                    <th className="px-4 py-2 text-right">勝率%</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((r) => {
                    const wr = r.runs > 0 ? (r.wins / r.runs) * 100 : 0
                    return (
                      <tr key={r.date} className="border-t border-gray-50 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                        <td className="px-4 py-2 text-gray-600 dark:text-gray-300">{r.date}</td>
                        <td className="px-4 py-2 text-right text-gray-600 dark:text-gray-300 tabular-nums">{r.runs}</td>
                        <td className="px-4 py-2 text-right tabular-nums">
                          <span className={r.wins > 0 ? 'text-emerald-600 font-bold' : 'text-gray-400'}>{r.wins}</span>
                        </td>
                        <td className="px-4 py-2 text-right tabular-nums">
                          <span className={r.top3 > 0 ? 'text-gray-700 dark:text-gray-200' : 'text-gray-400'}>{r.top3}</span>
                        </td>
                        <td className="px-4 py-2 text-right tabular-nums">
                          <span className={wr >= 20 ? 'text-emerald-600 font-bold' : 'text-gray-500'}>
                            {wr.toFixed(1)}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              </div>
            </div>
          ) : (
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-8 text-center text-gray-400">
              直近の成績データなし
            </div>
          )}
        </div>
      )}
    </div>
  )
}
