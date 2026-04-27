/**
 * 騎手プロフィール — 条件別成績・直近成績・調教師コンビ成績を表示
 */
import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  fetchJockey,
  fetchJockeyStats,
  fetchJockeyRecent,
  fetchJockeyCombo,
} from '../api/client'
import ErrorBanner from './ErrorBanner'
import EmptyState from './EmptyState'

// --- 型定義 ---
interface Props {
  jockeyId: number
  onBack?: () => void
  onTitleReady?: (title: string) => void
}

interface JockeyInfo {
  id: number
  name: string
  name_kana: string
  birth_date: string
  belong: string
  total_1st: number
  total_2nd: number
  total_3rd: number
  total_races: number
  win_rate: number
  top3_rate: number
}

interface StatRow {
  label: string
  runs: number
  wins: number
  top3: number
}

interface JockeyStatsData {
  by_track: StatRow[]
  by_distance: StatRow[]
  by_venue: StatRow[]
  by_grade: StatRow[]
}

interface RecentDay {
  date: string
  runs: number
  wins: number
  top3: number
}

interface ComboRow {
  trainer_name: string
  trainer_id: number
  runs: number
  wins: number
  top3: number
}

type TabKey = 'stats' | 'recent' | 'combo'

// --- 勝率計算ユーティリティ ---
function pct(n: number, d: number): string {
  if (d === 0) return '-'
  return ((n / d) * 100).toFixed(1)
}

// --- 条件別成績テーブル ---
function StatsTable({ title, rows }: { title: string; rows: StatRow[] }) {
  if (!rows || rows.length === 0) {
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
          <tr className="text-gray-400 text-xs border-b border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/40">
            <th className="px-3 py-1.5 text-left">条件</th>
            <th className="px-3 py-1.5 text-right">出走</th>
            <th className="px-3 py-1.5 text-right">勝利</th>
            <th className="px-3 py-1.5 text-right">3着内</th>
            <th className="px-3 py-1.5 text-right">勝率%</th>
            <th className="px-3 py-1.5 text-right">複勝率%</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-t border-gray-50 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 dark:bg-gray-700/40 transition-colors">
              <td className="px-3 py-1.5 text-gray-700 dark:text-gray-200 font-medium">{r.label}</td>
              <td className="px-3 py-1.5 text-right text-gray-600 dark:text-gray-300 tabular-nums">{r.runs}</td>
              <td className="px-3 py-1.5 text-right text-gray-600 dark:text-gray-300 tabular-nums">{r.wins}</td>
              <td className="px-3 py-1.5 text-right text-gray-600 dark:text-gray-300 tabular-nums">{r.top3}</td>
              <td className="px-3 py-1.5 text-right tabular-nums">
                <span className={Number(pct(r.wins, r.runs)) >= 20 ? 'text-emerald-600 font-bold' : 'text-gray-600 dark:text-gray-300'}>
                  {pct(r.wins, r.runs)}
                </span>
              </td>
              <td className="px-3 py-1.5 text-right tabular-nums">
                <span className={Number(pct(r.top3, r.runs)) >= 40 ? 'text-emerald-600 font-bold' : 'text-gray-600 dark:text-gray-300'}>
                  {pct(r.top3, r.runs)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  )
}

// --- メインコンポーネント ---
export default function JockeyDetail({ jockeyId, onBack, onTitleReady }: Props) {
  const [tab, setTab] = useState<TabKey>('stats')

  // データ取得
  const { data: jockey, isLoading: jl, isError: jErr, refetch: refetchJockey } = useQuery<JockeyInfo>({
    queryKey: ['jockey', jockeyId],
    queryFn: () => fetchJockey(jockeyId),
    retry: 1,
  })
  const { data: stats, isLoading: sl } = useQuery<JockeyStatsData>({
    queryKey: ['jockeyStats', jockeyId],
    queryFn: () => fetchJockeyStats(jockeyId),
  })
  const { data: recent, isLoading: rl } = useQuery<RecentDay[]>({
    queryKey: ['jockeyRecent', jockeyId],
    queryFn: () => fetchJockeyRecent(jockeyId, 90),
  })
  const { data: combo, isLoading: cl } = useQuery<ComboRow[]>({
    queryKey: ['jockeyCombo', jockeyId],
    queryFn: () => fetchJockeyCombo(jockeyId),
  })

  // タブタイトル更新
  useEffect(() => {
    if (jockey?.name && onTitleReady) onTitleReady(jockey.name)
  }, [jockey?.name, onTitleReady])

  // ローディング
  if (jl) {
    return <div className="flex items-center justify-center h-full text-gray-400">読み込み中...</div>
  }
  if (jErr) {
    return <div className="p-5"><ErrorBanner message="騎手情報の取得に失敗しました" onRetry={() => refetchJockey()} /></div>
  }
  if (!jockey) {
    return <div className="p-5"><EmptyState icon="🧑" title="騎手情報なし" description="指定された騎手のデータが存在しません。" /></div>
  }

  // 直近成績の集計（30日/90日）
  const calcCumulative = (days: number) => {
    if (!recent || recent.length === 0) return { runs: 0, wins: 0, top3: 0 }
    const cutoff = new Date()
    cutoff.setDate(cutoff.getDate() - days)
    const cutoffStr = cutoff.toISOString().slice(0, 10)
    return recent
      .filter((d) => d.date >= cutoffStr)
      .reduce(
        (acc, d) => ({
          runs: acc.runs + d.runs,
          wins: acc.wins + d.wins,
          top3: acc.top3 + d.top3,
        }),
        { runs: 0, wins: 0, top3: 0 }
      )
  }

  const last30 = calcCumulative(30)
  const last90 = calcCumulative(90)

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

      {/* ヘッダー: 名前・所属・生年月日 */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-bold text-gray-800 dark:text-gray-100">{jockey.name}</h2>
          {jockey.belong && (
            <span className="px-2.5 py-0.5 text-xs font-medium rounded-full bg-emerald-100 dark:bg-emerald-900/50 text-emerald-700 dark:text-emerald-300">
              {jockey.belong}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 mt-1 text-sm text-gray-500">
          {jockey.name_kana && <span>{jockey.name_kana}</span>}
          {jockey.birth_date && <span>生年月日: {jockey.birth_date}</span>}
        </div>
      </div>

      {/* サマリーカード */}
      <div className="grid grid-cols-3 gap-3">
        {/* 通算出走数 */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-4 text-center">
          <div className="text-xs text-gray-400 mb-1">通算出走</div>
          <div className="text-2xl font-bold text-gray-800 dark:text-gray-100">{jockey.total_races.toLocaleString()}</div>
          <div className="text-xs text-gray-400 mt-1">
            {jockey.total_1st}-{jockey.total_2nd}-{jockey.total_3rd}
          </div>
        </div>
        {/* 勝率 */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-4 text-center">
          <div className="text-xs text-gray-400 mb-1">勝率</div>
          <div className={`text-2xl font-bold ${jockey.win_rate >= 15 ? 'text-emerald-600' : 'text-gray-800 dark:text-gray-100'}`}>
            {(jockey.win_rate).toFixed(1)}%
          </div>
        </div>
        {/* 複勝率 */}
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-4 text-center">
          <div className="text-xs text-gray-400 mb-1">複勝率</div>
          <div className={`text-2xl font-bold ${jockey.top3_rate >= 35 ? 'text-emerald-600' : 'text-gray-800 dark:text-gray-100'}`}>
            {(jockey.top3_rate).toFixed(1)}%
          </div>
        </div>
      </div>

      {/* タブ切替 */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        {([
          { key: 'stats' as TabKey, label: '条件別成績' },
          { key: 'recent' as TabKey, label: '直近成績' },
          { key: 'combo' as TabKey, label: 'コンビ成績' },
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
      {tab === 'stats' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
          {sl ? (
            <div className="text-sm text-gray-400 text-center py-4">読み込み中...</div>
          ) : stats ? (
            <>
              <StatsTable title="トラック別" rows={stats.by_track} />
              <StatsTable title="距離別" rows={stats.by_distance} />
              <StatsTable title="競馬場別" rows={stats.by_venue} />
              <StatsTable title="グレード別" rows={stats.by_grade} />
            </>
          ) : (
            <div className="text-sm text-gray-400 text-center py-4">条件別成績データなし</div>
          )}
        </div>
      )}

      {/* ====== 直近成績タブ ====== */}
      {tab === 'recent' && (
        <div className="space-y-4">
          {/* 直近30日/90日の集計サマリー */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-4">
              <div className="text-xs font-bold text-gray-500 mb-2">直近30日</div>
              <div className="flex items-baseline gap-3">
                <span className="text-lg font-bold text-gray-800 dark:text-gray-100">{last30.runs}走</span>
                <span className="text-sm text-gray-500">
                  {last30.wins}勝 / 3着内{last30.top3}回
                </span>
              </div>
              <div className="flex gap-4 mt-1 text-xs text-gray-500">
                <span>勝率 <b className={Number(pct(last30.wins, last30.runs)) >= 20 ? 'text-emerald-600' : 'text-gray-700 dark:text-gray-200'}>{pct(last30.wins, last30.runs)}%</b></span>
                <span>複勝率 <b className={Number(pct(last30.top3, last30.runs)) >= 40 ? 'text-emerald-600' : 'text-gray-700 dark:text-gray-200'}>{pct(last30.top3, last30.runs)}%</b></span>
              </div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-4">
              <div className="text-xs font-bold text-gray-500 mb-2">直近90日</div>
              <div className="flex items-baseline gap-3">
                <span className="text-lg font-bold text-gray-800 dark:text-gray-100">{last90.runs}走</span>
                <span className="text-sm text-gray-500">
                  {last90.wins}勝 / 3着内{last90.top3}回
                </span>
              </div>
              <div className="flex gap-4 mt-1 text-xs text-gray-500">
                <span>勝率 <b className={Number(pct(last90.wins, last90.runs)) >= 20 ? 'text-emerald-600' : 'text-gray-700 dark:text-gray-200'}>{pct(last90.wins, last90.runs)}%</b></span>
                <span>複勝率 <b className={Number(pct(last90.top3, last90.runs)) >= 40 ? 'text-emerald-600' : 'text-gray-700 dark:text-gray-200'}>{pct(last90.top3, last90.runs)}%</b></span>
              </div>
            </div>
          </div>

          {/* 日別リスト */}
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
            <h4 className="text-xs font-bold text-gray-500 mb-3">日別成績（直近90日）</h4>
            {rl ? (
              <div className="text-sm text-gray-400 text-center py-4">読み込み中...</div>
            ) : recent && recent.length > 0 ? (
              <div className="space-y-1">
                {recent.map((d) => (
                  <div
                    key={d.date}
                    className="flex items-center gap-3 px-3 py-1.5 rounded hover:bg-gray-50 dark:hover:bg-gray-700 dark:bg-gray-700/40 transition-colors text-sm"
                  >
                    <span className="text-gray-500 tabular-nums w-24">{d.date}</span>
                    <span className="text-gray-700 dark:text-gray-200 tabular-nums">{d.runs}走</span>
                    <span className={`tabular-nums ${d.wins > 0 ? 'text-emerald-600 font-bold' : 'text-gray-400'}`}>
                      {d.wins}勝
                    </span>
                    <span className={`tabular-nums ${d.top3 > 0 ? 'text-amber-600' : 'text-gray-400'}`}>
                      3着内{d.top3}
                    </span>
                    {/* 勝率バー */}
                    <div className="flex-1 bg-gray-100 dark:bg-gray-700 rounded-full h-2">
                      <div
                        className="h-full rounded-full bg-emerald-300"
                        style={{ width: `${d.runs > 0 ? (d.wins / d.runs) * 100 : 0}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-gray-400 text-center py-4">直近成績データなし</div>
            )}
          </div>
        </div>
      )}

      {/* ====== コンビ成績タブ ====== */}
      {tab === 'combo' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
          <h4 className="text-xs font-bold text-gray-500 mb-3">調教師コンビ成績</h4>
          {cl ? (
            <div className="text-sm text-gray-400 text-center py-4">読み込み中...</div>
          ) : combo && combo.length > 0 ? (
            /* コンビ成績テーブル: 横スクロール対応 */
            <div className="overflow-x-auto">
            <table className="min-w-[450px] w-full text-sm">
              <thead>
                <tr className="text-gray-400 text-xs border-b border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/40">
                  <th className="px-3 py-1.5 text-left">調教師</th>
                  <th className="px-3 py-1.5 text-right">出走</th>
                  <th className="px-3 py-1.5 text-right">勝利</th>
                  <th className="px-3 py-1.5 text-right">3着内</th>
                  <th className="px-3 py-1.5 text-right">勝率%</th>
                </tr>
              </thead>
              <tbody>
                {combo.map((c) => (
                  <tr key={c.trainer_id} className="border-t border-gray-50 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 dark:bg-gray-700/40 transition-colors">
                    <td className="px-3 py-1.5 text-gray-700 dark:text-gray-200 font-medium">{c.trainer_name}</td>
                    <td className="px-3 py-1.5 text-right text-gray-600 dark:text-gray-300 tabular-nums">{c.runs}</td>
                    <td className="px-3 py-1.5 text-right text-gray-600 dark:text-gray-300 tabular-nums">{c.wins}</td>
                    <td className="px-3 py-1.5 text-right text-gray-600 dark:text-gray-300 tabular-nums">{c.top3}</td>
                    <td className="px-3 py-1.5 text-right tabular-nums">
                      <span className={Number(pct(c.wins, c.runs)) >= 20 ? 'text-emerald-600 font-bold' : 'text-gray-600 dark:text-gray-300'}>
                        {pct(c.wins, c.runs)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          ) : (
            <div className="text-sm text-gray-400 text-center py-4">コンビ成績データなし</div>
          )}
        </div>
      )}
    </div>
  )
}
