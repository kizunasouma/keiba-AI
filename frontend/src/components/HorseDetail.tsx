/**
 * 馬カルテ — 馬プロフィール・全戦績・条件別成績・体重推移・血統を表示
 */
import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toFullWidth } from '../utils/format'
import {
  fetchHorse,
  fetchHorseResults,
  fetchHorseStats,
  fetchHorseWeightHistory,
  fetchFavorites,
  addFavorite,
  removeFavorite,
} from '../api/client'
import ErrorBanner from './ErrorBanner'
import EmptyState from './EmptyState'

// --- 型 ---
interface Props {
  horseId: number
  onBack?: () => void
  onTitleReady?: (title: string) => void
}

interface HorseInfo {
  name: string
  birth_date: string | null
  sex: number | null
  pedigree: {
    father: string | null
    mother: string | null
    mother_father: string | null
    father_father?: string | null
    father_mother?: string | null
    mother_mother?: string | null
  } | null
  producer: string | null
  area: string | null
  owner: string | null
  total_wins: number | null
  total_races: number | null
  total_earnings: number | null
}

interface RaceResult {
  race_date: string
  venue: string
  race_name: string | null
  distance: number
  track: string
  cond: string
  frame_num: number | null
  horse_num: number | null
  finish_order: number | null
  finish_time: number | null
  last_3f: number | null
  weight_carry: number | null
  horse_weight: number | null
  weight_diff: number | null
  odds_win: number | null
  popularity: number | null
  jockey_name: string | null
  corner_text: string | null
}

interface StatRow {
  label: string
  runs: number
  wins: number
  top3: number
}

interface HorseStatsData {
  by_track: StatRow[]
  by_distance: StatRow[]
  by_condition: StatRow[]
  by_venue: StatRow[]
}

interface WeightEntry {
  race_date: string
  weight: number
  diff: number | null
  finish_order: number | null
}

// --- 定数 ---
const SEX_L: Record<number, string> = { 1: '牡', 2: '牝', 3: '騸' }

type TabKey = 'results' | 'stats' | 'weight' | 'pedigree'

// --- ユーティリティ ---
/** タイム表示（ミリ秒 → m:ss.f） */
function fmtTime(v: number | null) {
  if (!v) return '-'
  return `${Math.floor(v / 1000)}:${String(Math.floor((v % 1000) / 10)).padStart(2, '0')}.${v % 10}`
}

/** 上がり3F表示（整数×0.1 → ss.f） */
function fmt3f(v: number | null) {
  return v ? (v / 10).toFixed(1) : '-'
}

/** 賞金表示 */
function fmtEarnings(v: number | null) {
  if (!v) return '-'
  const man = v / 100
  if (man >= 10000) return `${(man / 10000).toFixed(1)}億円`
  return `${man.toLocaleString()}万円`
}

/** 勝率・複勝率の算出 */
function pct(n: number, d: number) {
  if (d === 0) return '0.0'
  return ((n / d) * 100).toFixed(1)
}

// --- メインコンポーネント ---
export default function HorseDetail({ horseId, onBack, onTitleReady }: Props) {
  const [tab, setTab] = useState<TabKey>('results')

  // API取得
  const { data: horse, isLoading: hl, isError: he, refetch: refetchHorse } = useQuery<HorseInfo>({
    queryKey: ['horse', horseId],
    queryFn: () => fetchHorse(horseId),
    retry: 1,
  })
  const { data: results, isLoading: rl } = useQuery<RaceResult[]>({
    queryKey: ['horseResults', horseId],
    queryFn: () => fetchHorseResults(horseId),
    retry: 1,
  })
  const { data: stats } = useQuery<HorseStatsData>({
    queryKey: ['horseStats', horseId],
    queryFn: () => fetchHorseStats(horseId),
  })
  const { data: weightHistory } = useQuery<WeightEntry[]>({
    queryKey: ['horseWeight', horseId],
    queryFn: () => fetchHorseWeightHistory(horseId),
  })

  // お気に入り機能（フックは条件分岐の前に全て呼ぶ）
  const qc = useQueryClient()
  const { data: favList } = useQuery({ queryKey: ['favorites'], queryFn: fetchFavorites, retry: false })
  const isFav = (favList ?? []).some((f: any) => f.horse_id === horseId)
  const addFavMut = useMutation({
    mutationFn: () => addFavorite({ horse_id: horseId, horse_name: horse?.name ?? '' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['favorites'] }),
  })
  const removeFavMut = useMutation({
    mutationFn: () => removeFavorite(horseId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['favorites'] }),
  })

  // タブタイトル更新
  useEffect(() => {
    if (horse?.name && onTitleReady) onTitleReady(toFullWidth(horse.name))
  }, [horse?.name, onTitleReady])

  // ローディング
  if (hl || rl) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        読み込み中...
      </div>
    )
  }
  if (he) {
    return (
      <div className="p-5">
        <ErrorBanner message="馬情報の取得に失敗しました" onRetry={() => refetchHorse()} />
      </div>
    )
  }
  if (!horse) {
    return (
      <div className="p-5">
        <EmptyState icon="🐴" title="馬情報が見つかりません" description="指定された馬のデータが存在しません。" />
      </div>
    )
  }

  const totalRaces = horse.total_races ?? 0
  const totalWins = horse.total_wins ?? 0
  const winRate = totalRaces > 0 ? ((totalWins / totalRaces) * 100).toFixed(1) : '0.0'

  const tabs: { key: TabKey; label: string }[] = [
    { key: 'results', label: '全戦績' },
    { key: 'stats', label: '条件別成績' },
    { key: 'weight', label: '体重推移' },
    { key: 'pedigree', label: '血統' },
  ]

  return (
    <div className="max-w-6xl mx-auto p-5 space-y-4">

      {/* ヘッダー: 馬名・基本情報 + お気に入りボタン */}
      <div className="flex items-center gap-3">
        <h2 className="text-2xl font-bold text-gray-800 dark:text-gray-100">{toFullWidth(horse.name)}</h2>
        <button
          onClick={() => isFav ? removeFavMut.mutate() : addFavMut.mutate()}
          className={`text-xl transition-colors ${isFav ? 'text-yellow-400 hover:text-yellow-300' : 'text-gray-400 hover:text-yellow-400'}`}
          title={isFav ? 'お気に入り解除' : 'お気に入り登録'}>
          {isFav ? '★' : '☆'}
        </button>
        {/* 印刷ボタン */}
        <button
          onClick={() => window.print()}
          className="text-gray-400 hover:text-emerald-500 text-xs ml-auto transition-colors print:hidden"
          title="印刷"
        >
          🖨 印刷
        </button>
      </div>
      <div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-sm text-gray-500 dark:text-gray-400">
          {horse.sex != null && <span>{SEX_L[horse.sex] ?? '不明'}</span>}
          {horse.birth_date && <span>{horse.birth_date}生</span>}
          {horse.producer && <span>生産: {horse.producer}</span>}
          {horse.area && <span>{horse.area}</span>}
          {horse.owner && <span>馬主: {horse.owner}</span>}
        </div>
      </div>

      {/* 血統カード（簡易3行） */}
      {horse.pedigree && (
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm">
          <h3 className="text-xs font-bold text-gray-400 mb-3">血統</h3>
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-3">
              <span className="w-16 text-xs text-gray-400 text-right shrink-0">父</span>
              <span className="font-medium text-gray-700 dark:text-gray-200">{horse.pedigree.father ?? '-'}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="w-16 text-xs text-gray-400 text-right shrink-0">母</span>
              <span className="font-medium text-gray-700 dark:text-gray-200">{horse.pedigree.mother ?? '-'}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="w-16 text-xs text-gray-400 text-right shrink-0">母父</span>
              <span className="font-medium text-gray-700 dark:text-gray-200">{horse.pedigree.mother_father ?? '-'}</span>
            </div>
          </div>
        </div>
      )}

      {/* 成績サマリー */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm text-center">
          <div className="text-xs text-gray-400 mb-1">通算成績</div>
          <div className="text-lg font-bold text-gray-800 dark:text-gray-100">
            {totalWins}-{totalRaces - totalWins}
          </div>
          <div className="text-xs text-gray-400">{totalRaces}戦{totalWins}勝</div>
        </div>
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm text-center">
          <div className="text-xs text-gray-400 mb-1">勝率</div>
          <div className="text-lg font-bold text-emerald-600">{winRate}%</div>
        </div>
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm text-center">
          <div className="text-xs text-gray-400 mb-1">総賞金</div>
          <div className="text-lg font-bold text-gray-800 dark:text-gray-100">
            {fmtEarnings(horse.total_earnings)}
          </div>
        </div>
      </div>

      {/* タブ */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t.key
                ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
                : 'border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ====== 全戦績タブ ====== */}
      {tab === 'results' && (
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm">
          {results && results.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-[900px] w-full text-sm">
                <thead>
                  {/* 戦績テーブルヘッダー（ダークモード対応） */}
                  <tr className="text-gray-400 text-xs border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/40">
                    <th className="px-2 py-2 text-left">日付</th>
                    <th className="px-2 py-2 text-left">場</th>
                    <th className="px-2 py-2 text-left">レース名</th>
                    <th className="px-2 py-2 text-center">距離</th>
                    <th className="px-2 py-2 text-center">馬場</th>
                    <th className="px-1 py-2 text-center">枠</th>
                    <th className="px-1 py-2 text-center">番</th>
                    <th className="px-1 py-2 text-center">着順</th>
                    <th className="px-2 py-2 text-right">タイム</th>
                    <th className="px-2 py-2 text-right">上3F</th>
                    <th className="px-1 py-2 text-center">斤量</th>
                    <th className="px-2 py-2 text-center">体重</th>
                    <th className="px-2 py-2 text-right">単勝</th>
                    <th className="px-1 py-2 text-center">人気</th>
                    <th className="px-2 py-2 text-left">騎手</th>
                    <th className="px-2 py-2 text-left">通過</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((r, i) => (
                    <tr
                      key={i}
                      className={`border-t border-gray-100 dark:border-gray-700 ${
                        r.finish_order === 1
                          ? 'bg-amber-50 dark:bg-amber-900/20'
                          : r.finish_order != null && r.finish_order <= 3
                          ? 'bg-gray-50/50 dark:bg-gray-700/30'
                          : ''
                      }`}
                    >
                      <td className="px-2 py-1.5 text-gray-500 dark:text-gray-400 whitespace-nowrap">{r.race_date}</td>
                      <td className="px-2 py-1.5 text-gray-600 dark:text-gray-300">{r.venue}</td>
                      <td className="px-2 py-1.5 text-gray-700 dark:text-gray-200 truncate max-w-[140px]">
                        {r.race_name || '-'}
                      </td>
                      <td className="px-2 py-1.5 text-center text-gray-600 dark:text-gray-300 whitespace-nowrap">
                        {r.track}{r.distance}
                      </td>
                      <td className="px-2 py-1.5 text-center text-gray-500 dark:text-gray-400">{r.cond}</td>
                      <td className="px-1 py-1.5 text-center text-gray-500 dark:text-gray-400">{r.frame_num ?? '-'}</td>
                      <td className="px-1 py-1.5 text-center text-gray-500 dark:text-gray-400">{r.horse_num ?? '-'}</td>
                      <td className="px-1 py-1.5 text-center">
                        <span
                          className={`font-bold ${
                            r.finish_order === 1
                              ? 'text-amber-600'
                              : r.finish_order != null && r.finish_order <= 3
                              ? 'text-emerald-600'
                              : 'text-gray-500'
                          }`}
                        >
                          {r.finish_order ?? '-'}
                        </span>
                      </td>
                      <td className="px-2 py-1.5 text-right text-gray-500 dark:text-gray-400 tabular-nums">
                        {fmtTime(r.finish_time)}
                      </td>
                      <td className="px-2 py-1.5 text-right text-gray-500 dark:text-gray-400 tabular-nums">
                        {fmt3f(r.last_3f)}
                      </td>
                      <td className="px-1 py-1.5 text-center text-gray-500 dark:text-gray-400">
                        {r.weight_carry ?? '-'}
                      </td>
                      <td className="px-2 py-1.5 text-center text-gray-500 dark:text-gray-400 whitespace-nowrap">
                        {r.horse_weight ?? '-'}
                        {r.weight_diff != null && r.weight_diff !== 0 && (
                          <span
                            className={
                              r.weight_diff > 0 ? 'text-red-500' : 'text-blue-500'
                            }
                          >
                            ({r.weight_diff > 0 ? '+' : ''}
                            {r.weight_diff})
                          </span>
                        )}
                      </td>
                      <td className="px-2 py-1.5 text-right text-gray-500 dark:text-gray-400">
                        {r.odds_win ? r.odds_win.toFixed(1) : '-'}
                      </td>
                      <td className="px-1 py-1.5 text-center text-gray-500 dark:text-gray-400">
                        {r.popularity ?? '-'}
                      </td>
                      <td className="px-2 py-1.5 text-gray-500 dark:text-gray-400 truncate max-w-[80px]">
                        {r.jockey_name ?? '-'}
                      </td>
                      <td className="px-2 py-1.5 text-gray-400 text-xs whitespace-nowrap">
                        {r.corner_text ?? '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-8 text-center text-gray-400 dark:text-gray-500">戦績データなし</div>
          )}
        </div>
      )}

      {/* ====== 条件別成績タブ ====== */}
      {tab === 'stats' && stats && (
        <div className="space-y-4">
          {([
            { key: 'by_track' as const, title: 'トラック別' },
            { key: 'by_distance' as const, title: '距離別' },
            { key: 'by_condition' as const, title: '馬場状態別' },
            { key: 'by_venue' as const, title: '競馬場別' },
          ]).map(({ key, title }) => {
            const rows = stats[key]
            if (!rows || rows.length === 0) return null
            return (
              <div
                key={key}
                className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm"
              >
                <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700/40 border-b border-gray-100 dark:border-gray-700">
                  <h4 className="text-xs font-bold text-gray-500 dark:text-gray-400">{title}</h4>
                </div>
                {/* 条件別成績テーブル: 横スクロール対応 */}
                <div className="overflow-x-auto">
                <table className="min-w-[500px] w-full text-sm">
                  <thead>
                    <tr className="text-gray-400 text-xs border-b border-gray-100 dark:border-gray-700">
                      <th className="px-4 py-2 text-left">条件</th>
                      <th className="px-3 py-2 text-center">出走</th>
                      <th className="px-3 py-2 text-center">勝利</th>
                      <th className="px-3 py-2 text-center">複勝</th>
                      <th className="px-3 py-2 text-right">勝率</th>
                      <th className="px-3 py-2 text-right">複勝率</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, i) => (
                      <tr key={i} className="border-t border-gray-50 dark:border-gray-700">
                        <td className="px-4 py-2 text-gray-700 dark:text-gray-200 font-medium">{row.label}</td>
                        <td className="px-3 py-2 text-center text-gray-600 dark:text-gray-300">{row.runs}</td>
                        <td className="px-3 py-2 text-center text-gray-600 dark:text-gray-300">{row.wins}</td>
                        <td className="px-3 py-2 text-center text-gray-600 dark:text-gray-300">{row.top3}</td>
                        <td className="px-3 py-2 text-right">
                          <span
                            className={
                              row.wins > 0 ? 'text-emerald-600 dark:text-emerald-400 font-bold' : 'text-gray-400'
                            }
                          >
                            {pct(row.wins, row.runs)}%
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right">
                          <span
                            className={
                              row.top3 > 0 ? 'text-blue-600 dark:text-blue-400 font-bold' : 'text-gray-400'
                            }
                          >
                            {pct(row.top3, row.runs)}%
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              </div>
            )
          })}
          {/* データ無しの場合 */}
          {(!stats.by_track?.length &&
            !stats.by_distance?.length &&
            !stats.by_condition?.length &&
            !stats.by_venue?.length) && (
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-8 text-center text-gray-400">
              条件別成績データなし
            </div>
          )}
        </div>
      )}

      {/* ====== 体重推移タブ ====== */}
      {tab === 'weight' && (
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-5 shadow-sm">
          <h4 className="text-xs font-bold text-gray-500 mb-4">体重推移</h4>
          {weightHistory && weightHistory.length > 0 ? (() => {
            // チャート用の最小・最大を算出
            const weights = weightHistory.map(w => w.weight)
            const minW = Math.min(...weights)
            const maxW = Math.max(...weights)
            const range = maxW - minW || 10 // 差が0の場合のフォールバック
            const chartHeight = 200 // px

            return (
              <div>
                {/* バーチャート */}
                <div className="flex items-end gap-1 overflow-x-auto pb-2" style={{ height: chartHeight + 40 }}>
                  {weightHistory.map((w, i) => {
                    // バーの高さ: 最小値でも20%は表示
                    const normalized = (w.weight - minW) / range
                    const barHeight = Math.max(chartHeight * 0.2, chartHeight * (0.2 + 0.8 * normalized))
                    // 着順に応じた色
                    /* バーの色（ダークモード対応: gray-300は暗い背景で見えにくいためgray-400/500を使用） */
                    const barColor =
                      w.finish_order === 1
                        ? 'bg-amber-400'
                        : w.finish_order != null && w.finish_order <= 3
                        ? 'bg-emerald-400'
                        : 'bg-gray-300 dark:bg-gray-500'

                    return (
                      <div
                        key={i}
                        className="flex flex-col items-center shrink-0"
                        style={{ minWidth: 36 }}
                      >
                        {/* 体重値 */}
                        <div className="text-[10px] text-gray-500 mb-1 whitespace-nowrap">
                          {w.weight}
                          {w.diff != null && w.diff !== 0 && (
                            <span className={w.diff > 0 ? 'text-red-500' : 'text-blue-500'}>
                              {w.diff > 0 ? '+' : ''}
                              {w.diff}
                            </span>
                          )}
                        </div>
                        {/* バー */}
                        <div
                          className={`w-5 rounded-t ${barColor}`}
                          style={{ height: barHeight }}
                          title={`${w.race_date} ${w.weight}kg ${w.finish_order ?? '-'}着`}
                        />
                        {/* 日付 */}
                        <div className="text-[9px] text-gray-400 mt-1 whitespace-nowrap">
                          {w.race_date.slice(5)}
                        </div>
                        {/* 着順 */}
                        <div
                          className={`text-[10px] font-bold ${
                            w.finish_order === 1
                              ? 'text-amber-600'
                              : w.finish_order != null && w.finish_order <= 3
                              ? 'text-emerald-600'
                              : 'text-gray-400'
                          }`}
                        >
                          {w.finish_order ?? '-'}着
                        </div>
                      </div>
                    )
                  })}
                </div>
                {/* 範囲ラベル */}
                <div className="flex justify-between text-xs text-gray-400 mt-2 px-1">
                  <span>最小: {minW}kg</span>
                  <span>最大: {maxW}kg</span>
                  <span>差: {maxW - minW}kg</span>
                </div>
              </div>
            )
          })() : (
            <div className="text-center text-gray-400 py-8">体重データなし</div>
          )}
        </div>
      )}

      {/* ====== 血統タブ ====== */}
      {tab === 'pedigree' && (
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-5 shadow-sm">
          <h4 className="text-xs font-bold text-gray-500 mb-4">血統表</h4>
          {horse.pedigree ? (
            <div className="grid grid-cols-3 gap-3">
              {/* 父系 */}
              <div className="space-y-3">
                <div className="bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
                  <div className="text-[10px] text-blue-400 mb-1">父</div>
                  <div className="font-bold text-blue-800 dark:text-blue-200 text-sm">
                    {horse.pedigree.father ?? '-'}
                  </div>
                </div>
                {horse.pedigree.father_father && (
                  <div className="bg-blue-50/50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800/50 rounded-lg p-3 ml-4">
                    <div className="text-[10px] text-blue-300 mb-1">父父</div>
                    <div className="text-sm text-blue-700 dark:text-blue-300">
                      {horse.pedigree.father_father}
                    </div>
                  </div>
                )}
                {horse.pedigree.father_mother && (
                  <div className="bg-pink-50/50 dark:bg-pink-900/20 border border-pink-100 dark:border-pink-800/50 rounded-lg p-3 ml-4">
                    <div className="text-[10px] text-pink-300 mb-1">父母</div>
                    <div className="text-sm text-pink-700 dark:text-pink-300">
                      {horse.pedigree.father_mother}
                    </div>
                  </div>
                )}
              </div>
              {/* 本馬 */}
              <div className="flex items-center justify-center">
                <div className="bg-emerald-50 dark:bg-emerald-900/30 border-2 border-emerald-300 dark:border-emerald-700 rounded-xl p-4 text-center w-full">
                  <div className="text-[10px] text-emerald-400 mb-1">本馬</div>
                  <div className="font-bold text-emerald-800 dark:text-emerald-200 text-lg">{toFullWidth(horse.name)}</div>
                  {horse.sex != null && (
                    <div className="text-xs text-emerald-500 mt-1">
                      {SEX_L[horse.sex] ?? ''}
                    </div>
                  )}
                </div>
              </div>
              {/* 母系 */}
              <div className="space-y-3">
                <div className="bg-pink-50 dark:bg-pink-900/30 border border-pink-200 dark:border-pink-800 rounded-lg p-3">
                  <div className="text-[10px] text-pink-400 mb-1">母</div>
                  <div className="font-bold text-pink-800 dark:text-pink-200 text-sm">
                    {horse.pedigree.mother ?? '-'}
                  </div>
                </div>
                <div className="bg-blue-50/50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800/50 rounded-lg p-3 ml-4">
                  <div className="text-[10px] text-blue-300 mb-1">母父</div>
                  <div className="text-sm text-blue-700 dark:text-blue-300">
                    {horse.pedigree.mother_father ?? '-'}
                  </div>
                </div>
                {horse.pedigree.mother_mother && (
                  <div className="bg-pink-50/50 dark:bg-pink-900/20 border border-pink-100 dark:border-pink-800/50 rounded-lg p-3 ml-4">
                    <div className="text-[10px] text-pink-300 mb-1">母母</div>
                    <div className="text-sm text-pink-700 dark:text-pink-300">
                      {horse.pedigree.mother_mother}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="text-center text-gray-400 py-8">血統データなし</div>
          )}
        </div>
      )}
    </div>
  )
}
