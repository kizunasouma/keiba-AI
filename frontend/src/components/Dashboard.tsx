/**
 * ダッシュボード — レースカードグリッド表示（案B方式）
 * 開催日選択 → 場ごとにレースカードを並べる
 */
import { useState, useMemo, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchRaces, fetchUpcomingFavorites } from '../api/client'
import ErrorBanner from './ErrorBanner'
import EmptyState from './EmptyState'

const VENUE: Record<string, string> = {
  '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
  '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉',
}
const TRACK_L: Record<number, string> = { 1: '芝', 2: 'ダ', 3: '障' }
const COND_L: Record<number, string> = { 1: '良', 2: '稍', 3: '重', 4: '不' }
const GRADE_L: Record<number, string> = { 1: 'G1', 2: 'G2', 3: 'G3', 4: '重賞', 5: 'OP', 6: 'L' }
const GRADE_C: Record<number, string> = {
  1: 'bg-yellow-400 text-yellow-900', 2: 'bg-red-400 text-white', 3: 'bg-green-400 text-white',
  4: 'bg-blue-400 text-white', 5: 'bg-gray-400 text-white', 6: 'bg-purple-400 text-white',
}
const DAY_N = ['日', '月', '火', '水', '木', '金', '土']

interface Props {
  onOpenRace: (raceKey: string, title?: string) => void
}
interface Race {
  race_key: string; race_name: string | null; race_date: string; venue_code: string
  race_num: number; grade: number | null; distance: number; track_type: number
  horse_count: number | null; is_handicap: boolean; is_female_only: boolean
  track_cond: number | null
  start_time?: string | null  // 発走時刻（例: "11:00"）
}

// 競馬開催週: 土曜〜日曜のペアで1週とする
function raceWeekRange(d: Date): [Date, Date] {
  const day = d.getDay()
  // 今日が日曜(0)なら前日の土曜が週の開始
  // 今日が土曜(6)ならその日が週の開始
  // 平日(1-5)なら次の土曜が週の開始
  let sat: Date
  if (day === 6) {
    sat = new Date(d)
  } else if (day === 0) {
    sat = new Date(d); sat.setDate(d.getDate() - 1)
  } else {
    sat = new Date(d); sat.setDate(d.getDate() + (6 - day))
  }
  const sun = new Date(sat); sun.setDate(sat.getDate() + 1)
  return [sat, sun]
}
function addDays(d: Date, n: number) { const r = new Date(d); r.setDate(d.getDate() + n); return r }
function toStr(d: Date) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}
function todayStr() { return toStr(new Date()) }

type WeekTab = 'prev2' | 'prev' | 'this' | 'next' | 'latest'

/** お気に入り出走予定バナー */
function FavoriteUpcomingBanner({ onOpenRace }: { onOpenRace: (raceKey: string, title?: string) => void }) {
  const [dismissed, setDismissed] = useState(false)
  const { data: upcoming } = useQuery<any[]>({
    queryKey: ['favorites-upcoming'],
    queryFn: fetchUpcomingFavorites,
    retry: 0, // APIエラー時は静かに失敗
    staleTime: 60_000,
  })

  // 非表示条件: 閉じた / データなし / エラー
  if (dismissed || !upcoming || upcoming.length === 0) return null

  return (
    <div className="mx-6 mt-4 bg-emerald-50 dark:bg-emerald-600/20 border border-emerald-300 dark:border-emerald-500/40 rounded-xl px-4 py-3 flex items-center gap-3">
      <span className="text-emerald-500 dark:text-emerald-400 shrink-0">⭐</span>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-emerald-700 dark:text-emerald-300 mb-0.5">お気に入り馬の出走予定</div>
        <div className="flex flex-wrap gap-2">
          {upcoming.map((u: any) => (
            <button
              key={u.race_key}
              onClick={() => onOpenRace(u.race_key, `${u.venue}${u.race_num}R ${u.race_name ?? ''}`)}
              className="text-xs text-emerald-700 dark:text-emerald-200 hover:text-emerald-900 dark:hover:text-white bg-emerald-200/50 dark:bg-emerald-700/40 hover:bg-emerald-200 dark:hover:bg-emerald-700/60 px-2 py-1 rounded-lg transition-colors"
            >
              {u.horse_name ?? '不明'}（{u.race_date?.slice(5)} {u.venue}{u.race_num}R）
            </button>
          ))}
        </div>
      </div>
      {/* 閉じるボタン */}
      <button
        onClick={() => setDismissed(true)}
        className="text-emerald-500 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-white text-lg shrink-0 transition-colors"
        title="閉じる"
      >
        ×
      </button>
    </div>
  )
}

export default function Dashboard({ onOpenRace }: Props) {
  // DB最新レース日付を取得して「最新データ」タブに使用
  const { data: latestRaces } = useQuery<Race[]>({
    queryKey: ['dashboard-latest-check'],
    queryFn: () => fetchRaces({ limit: 1 }),
    retry: 0,
    staleTime: 300_000,
  })
  const latestDate = latestRaces?.[0]?.race_date ? new Date(latestRaces[0].race_date + 'T00:00:00') : null

  // 今週にデータがなければ自動的に「最新データ」タブを選択
  const [weekTab, setWeekTab] = useState<WeekTab>('this')
  const [autoSwitched, setAutoSwitched] = useState(false)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)

  const weeks = useMemo(() => {
    const [thisSat, thisSun] = raceWeekRange(new Date())
    // DB最新日付の週を計算
    const latestD = latestDate ?? new Date()
    const [latestSat, latestSun] = raceWeekRange(latestD)
    return {
      prev2: { sat: addDays(thisSat, -14), sun: addDays(thisSat, -13), label: '2週前' },
      prev: { sat: addDays(thisSat, -7), sun: addDays(thisSat, -6), label: '前週' },
      this: { sat: thisSat, sun: thisSun, label: '今週' },
      next: { sat: addDays(thisSat, 7), sun: addDays(thisSat, 8), label: '来週' },
      latest: { sat: latestSat, sun: latestSun, label: '最新データ' },
    }
  }, [latestDate])

  const w = weeks[weekTab]

  const { data: allRaces, isLoading, isError, error, refetch } = useQuery<Race[]>({
    queryKey: ['dashboard-races', toStr(w.sat), toStr(w.sun)],
    queryFn: () => fetchRaces({ date_from: toStr(w.sat), date_to: toStr(w.sun), limit: 1000 }),
    retry: 1,
  })

  // 今週にデータがなく、DB最新データがある場合は自動的に「最新データ」タブに切り替え
  useEffect(() => {
    if (!autoSwitched && weekTab === 'this' && allRaces && allRaces.length === 0 && latestDate) {
      setWeekTab('latest')
      setAutoSwitched(true)
    }
  }, [allRaces, autoSwitched, weekTab, latestDate])

  // 土日のみ表示（競馬開催日）
  const raceDates = useMemo(() => {
    const dates = [...new Set(allRaces?.map(r => r.race_date) ?? [])].sort()
    return dates.filter(d => {
      const day = new Date(d + 'T00:00:00').getDay()
      return day === 0 || day === 6 // 日曜 or 土曜
    })
  }, [allRaces])
  const activeDate = selectedDate && raceDates.includes(selectedDate) ? selectedDate
    : raceDates.find(d => d === todayStr()) ?? raceDates[raceDates.length - 1] ?? null
  const dayRaces = useMemo(() => (allRaces ?? []).filter(r => r.race_date === activeDate), [allRaces, activeDate])

  // 場ごとにグルーピング
  const grouped = useMemo(() => {
    const map = new Map<string, Race[]>()
    for (const r of dayRaces) {
      if (!map.has(r.venue_code)) map.set(r.venue_code, [])
      map.get(r.venue_code)!.push(r)
    }
    // 場内をレース番号順にソート
    for (const [, races] of map) races.sort((a, b) => a.race_num - b.race_num)
    return map
  }, [dayRaces])

  // 重賞を抽出
  const gradeRaces = dayRaces.filter(r => r.grade != null && r.grade <= 5)

  return (
    <div>
      {/* お気に入り馬の出走通知バナー */}
      <FavoriteUpcomingBanner onOpenRace={onOpenRace} />

      {/* 週タブ + 日付選択 */}
      {/* 週タブ: ボーダーを明確化 */}
      <div className="sticky top-0 z-30 bg-white/95 dark:bg-gray-900/95 backdrop-blur border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center px-6 py-2 gap-2">
          {/* 週タブ */}
          {(['prev2', 'prev', 'this', 'next'] as WeekTab[]).map(wt => {
            const ws = weeks[wt]
            const satD = ws.sat
            const dateLabel = `${satD.getMonth() + 1}/${satD.getDate()}`
            return (
              <button key={wt} onClick={() => { setWeekTab(wt); setSelectedDate(null) }}
                className={`px-4 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  weekTab === wt ? 'bg-emerald-600 text-white' : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}>
                {ws.label}
                <span className={`ml-1 text-[10px] ${weekTab === wt ? 'text-emerald-200' : 'text-gray-400 dark:text-gray-600'}`}>{dateLabel}</span>
              </button>
            )
          })}
          <div className="w-px h-5 bg-gray-200 dark:bg-gray-700 mx-2" />
          {/* 開催日ボタン */}
          {raceDates.map(d => {
            const dt = new Date(d + 'T00:00:00')
            const isActive = d === activeDate
            const isSat = dt.getDay() === 6
            const isSun = dt.getDay() === 0
            const cnt = (allRaces ?? []).filter(r => r.race_date === d).length
            return (
              <button key={d} onClick={() => setSelectedDate(d)}
                className={`px-3 py-1.5 rounded-lg text-xs transition-colors ${
                  isActive ? 'bg-emerald-600 text-white font-bold shadow' :
                  isSun ? 'text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30' :
                  isSat ? 'text-blue-500 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30' :
                  'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'
                }`}>
                {dt.getMonth() + 1}/{dt.getDate()}({DAY_N[dt.getDay()]})
                <span className={`ml-1 text-[10px] ${isActive ? 'text-emerald-200' : 'text-gray-400 dark:text-gray-600'}`}>{cnt}R</span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="px-6 py-5">
        {isLoading && <div className="text-center text-gray-500 py-20">読み込み中...</div>}

        {/* エラー表示 */}
        {isError && !isLoading && (
          <div className="py-8">
            <ErrorBanner
              message={error instanceof Error ? error.message : 'レースデータの取得に失敗しました'}
              onRetry={() => refetch()}
            />
          </div>
        )}

        {!isLoading && !isError && dayRaces.length === 0 && (
          <EmptyState
            icon="🏇"
            title="この週の開催データなし"
            description="選択した週にはレースが登録されていません。別の週を選択するか、データの取り込みを確認してください。"
          />
        )}

        {/* 重賞ハイライト */}
        {gradeRaces.length > 0 && (
          <div className="mb-8">
            <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${Math.min(gradeRaces.length, 3)}, 1fr)` }}>
              {gradeRaces.map(race => {
                const vn = VENUE[race.venue_code] ?? race.venue_code
                return (
                  <div key={race.race_key}
                    onClick={() => onOpenRace(race.race_key, `${vn}${race.race_num}R ${race.race_name ?? ''}`)}
                    className="bg-gradient-to-br from-white dark:from-gray-800 to-emerald-50 dark:to-emerald-900/40 border border-emerald-300 dark:border-emerald-700/50 rounded-2xl p-5 cursor-pointer hover:border-emerald-500 transition-all hover:shadow-lg hover:shadow-emerald-200/50 dark:hover:shadow-emerald-900/30 animate-fade-in card-hover">
                    <div className="flex items-center gap-2 mb-2">
                      {race.grade != null && GRADE_L[race.grade] && (
                        <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${GRADE_C[race.grade]}`}>{GRADE_L[race.grade]}</span>
                      )}
                      <span className="text-xs text-gray-500 dark:text-gray-400">{vn} {race.race_num}R</span>
                    </div>
                    <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-1">{race.race_name || `${vn}${race.race_num}R`}</h3>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {/* 発走時刻 */}
                      {race.start_time && <span className="text-emerald-400 font-medium">{race.start_time}</span>}
                      {race.start_time && ' · '}
                      {TRACK_L[race.track_type]}{race.distance}m
                      {race.track_cond ? ` · ${COND_L[race.track_cond]}` : ''}
                      {race.horse_count ? ` · ${race.horse_count}頭` : ''}
                      {race.is_handicap ? ' · ハンデ' : ''}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* 場ごとのレースカード */}
        {[...grouped.entries()].map(([vc, races]) => {
          const vn = VENUE[vc] ?? vc
          return (
            <div key={vc} className="mb-8">
              <h2 className="text-sm font-bold text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                <span className="w-1 h-4 bg-emerald-500 rounded-full" />
                {vn}競馬場
                <span className="text-xs text-gray-400 dark:text-gray-600 font-normal">{races.length}レース</span>
              </h2>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
                {races.map(race => {
                  const isGrade = race.grade != null && race.grade <= 5
                  return (
                    <div key={race.race_key}
                      onClick={() => onOpenRace(race.race_key, `${vn}${race.race_num}R ${race.race_name ?? ''}`)}
                      className={`rounded-xl p-3 cursor-pointer transition-all border animate-fade-in card-hover ${
                        isGrade
                          ? 'bg-white dark:bg-gray-800 border-emerald-300 dark:border-emerald-800 hover:border-emerald-500 hover:shadow-lg hover:shadow-emerald-200/30 dark:hover:shadow-emerald-900/20'
                          : 'bg-white/60 dark:bg-gray-800/60 border-gray-200 dark:border-gray-700/50 hover:border-gray-300 dark:hover:border-gray-600 hover:bg-white dark:hover:bg-gray-800'
                      }`}>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-gray-500">
                          {race.race_num}R
                          {/* 発走時刻 */}
                          {race.start_time && <span className="ml-1 text-gray-400">{race.start_time}</span>}
                        </span>
                        <div className="flex gap-1">
                          {race.is_female_only && <span className="text-[9px] px-1 rounded bg-pink-100 dark:bg-pink-900/50 text-pink-600 dark:text-pink-400">♀</span>}
                          {race.is_handicap && <span className="text-[9px] px-1 rounded bg-orange-100 dark:bg-orange-900/50 text-orange-600 dark:text-orange-400">H</span>}
                          {race.grade != null && GRADE_L[race.grade] && (
                            <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold ${GRADE_C[race.grade]}`}>{GRADE_L[race.grade]}</span>
                          )}
                        </div>
                      </div>
                      <div className="text-sm font-medium text-gray-700 dark:text-gray-200 truncate mb-1">
                        {race.race_name || `${race.race_num}R`}
                      </div>
                      <div className="text-[10px] text-gray-500">
                        {TRACK_L[race.track_type]}{race.distance}m
                        {race.track_cond ? ` ${COND_L[race.track_cond]}` : ''}
                        {race.horse_count ? ` · ${race.horse_count}頭` : ''}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
