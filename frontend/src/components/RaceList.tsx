/**
 * レース一覧 — 当週/前週/来週タブ + 開催日ボタン + フィルター
 */
import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchRaces } from '../api/client'

const VENUE: Record<string, string> = {
  '01': '札幌', '02': '函館', '03': '福島', '04': '新潟',
  '05': '東京', '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉',
}
const TRACK_L: Record<number, string> = { 1: '芝', 2: 'ダ', 3: '障' }
const GRADE_L: Record<number, string> = { 1: 'G1', 2: 'G2', 3: 'G3', 4: '重賞', 5: 'OP', 6: 'L' }
/* グレードバッジ色（ダークモード対応） */
const GRADE_C: Record<number, string> = {
  1: 'bg-yellow-500 text-yellow-900', 2: 'bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-300', 3: 'bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300',
  4: 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300', 5: 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300', 6: 'bg-purple-100 dark:bg-purple-900/50 text-purple-700 dark:text-purple-300',
}
const COND_L: Record<number, string> = { 1: '良', 2: '稍', 3: '重', 4: '不' }
const DAY_N = ['日', '月', '火', '水', '木', '金', '土']

interface Props { selectedRaceKey: string | null; onSelect: (raceKey: string) => void }
interface Race {
  race_key: string; race_name: string | null; race_date: string; venue_code: string
  race_num: number; grade: number | null; distance: number; track_type: number
  horse_count: number | null; is_handicap: boolean; is_female_only: boolean
  track_cond: number | null
}

// --- 週の計算ユーティリティ ---
function today() { return new Date() }
function toStr(d: Date) { return d.toISOString().slice(0, 10) }
function todayStr() { return toStr(today()) }

/** 指定日の週の月曜と日曜を返す */
function weekRange(d: Date): [Date, Date] {
  const day = d.getDay()
  const diff = day === 0 ? -6 : 1 - day // 月曜起点
  const mon = new Date(d); mon.setDate(d.getDate() + diff)
  const sun = new Date(mon); sun.setDate(mon.getDate() + 6)
  return [mon, sun]
}

function addDays(d: Date, n: number): Date {
  const r = new Date(d); r.setDate(d.getDate() + n); return r
}

function fmtShort(s: string): string {
  const d = new Date(s + 'T00:00:00')
  return `${d.getMonth() + 1}/${d.getDate()}(${DAY_N[d.getDay()]})`
}

function fmtWeekLabel(mon: Date, sun: Date): string {
  return `${mon.getMonth() + 1}/${mon.getDate()} 〜 ${sun.getMonth() + 1}/${sun.getDate()}`
}

type WeekTab = 'prev2' | 'prev' | 'this' | 'next'

export default function RaceList({ selectedRaceKey, onSelect }: Props) {
  const [weekTab, setWeekTab] = useState<WeekTab>('this')
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [venueFilter, setVenueFilter] = useState<string | null>(null)
  const [showFilter, setShowFilter] = useState(false)
  const [trackType, setTrackType] = useState<number | null>(null)
  const [condFilter, setCondFilter] = useState<number | null>(null)
  const [handicapOnly, setHandicapOnly] = useState(false)
  const [femaleOnly, setFemaleOnly] = useState(false)
  const [raceName, setRaceName] = useState('')

  // 週の日付範囲を計算
  const weeks = useMemo(() => {
    const t = today()
    const [thisMon, thisSun] = weekRange(t)
    return {
      prev2: { mon: addDays(thisMon, -14), sun: addDays(thisMon, -8), label: '2週前' },
      prev:  { mon: addDays(thisMon, -7),  sun: addDays(thisMon, -1), label: '前週' },
      this:  { mon: thisMon,               sun: thisSun,              label: '今週' },
      next:  { mon: addDays(thisSun, 1),   sun: addDays(thisSun, 7),  label: '来週' },
    }
  }, [])

  const activeWeek = weeks[weekTab]

  // API: 選択週のレースを取得
  const { data: allRaces, isLoading, isError } = useQuery<Race[]>({
    queryKey: ['races-week', toStr(activeWeek.mon), toStr(activeWeek.sun), raceName],
    queryFn: () => fetchRaces({
      date_from: toStr(activeWeek.mon),
      date_to: toStr(activeWeek.sun),
      race_name: raceName || undefined,
      limit: 1000,
    }),
  })

  // 開催日一覧（この週内）
  const raceDates = useMemo(() =>
    [...new Set(allRaces?.map(r => r.race_date) ?? [])].sort(),
  [allRaces])

  // 選択中の日付（デフォルト: 今日があればその日、なければ最新の土日）
  const activeDate = selectedDate && raceDates.includes(selectedDate)
    ? selectedDate
    : raceDates.find(d => d === todayStr()) ?? raceDates[raceDates.length - 1] ?? null

  // 選択日のレース
  const dayRaces = useMemo(() =>
    (allRaces ?? []).filter(r => r.race_date === activeDate),
  [allRaces, activeDate])

  // 競馬場一覧
  const venues = useMemo(() =>
    [...new Set(dayRaces.map(r => r.venue_code))].sort(),
  [dayRaces])

  // フィルタ適用
  let filtered = dayRaces
  if (venueFilter) filtered = filtered.filter(r => r.venue_code === venueFilter)
  if (trackType) filtered = filtered.filter(r => r.track_type === trackType)
  if (condFilter) filtered = filtered.filter(r => r.track_cond === condFilter)
  if (handicapOnly) filtered = filtered.filter(r => r.is_handicap)
  if (femaleOnly) filtered = filtered.filter(r => r.is_female_only)
  filtered = [...filtered].sort((a, b) =>
    a.venue_code !== b.venue_code ? a.venue_code.localeCompare(b.venue_code) : a.race_num - b.race_num
  )

  // 場ごとにグルーピング
  const grouped = useMemo(() => {
    const map = new Map<string, Race[]>()
    for (const r of filtered) {
      const key = r.venue_code
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(r)
    }
    return map
  }, [filtered])

  return (
    <div className="flex flex-col h-full text-sm">

      {/* === 週タブ（ダークモード対応） === */}
      <div className="grid grid-cols-4 border-b border-gray-200 dark:border-gray-700">
        {(['prev2', 'prev', 'this', 'next'] as WeekTab[]).map(w => (
          <button key={w} onClick={() => { setWeekTab(w); setSelectedDate(null); setVenueFilter(null) }}
            className={`py-2 text-center text-xs font-medium transition-colors border-b-2 ${
              weekTab === w
                ? 'border-emerald-500 text-emerald-600 bg-emerald-50 dark:bg-emerald-900/30'
                : 'border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800'
            }`}>
            {weeks[w].label}
          </button>
        ))}
      </div>

      {/* === 週の日付表示 + 開催日ボタン === */}
      {/* 週の日付表示（ダークモード対応） */}
      <div className="px-3 pt-2 pb-1 border-b border-gray-200 dark:border-gray-700">
        <div className="text-[10px] text-gray-400 mb-1.5">{fmtWeekLabel(activeWeek.mon, activeWeek.sun)}</div>
        {raceDates.length > 0 ? (
          <div className="flex gap-1 pb-1.5 overflow-x-auto">
            {raceDates.map(d => {
              const isActive = d === activeDate
              const isToday = d === todayStr()
              const dt = new Date(d + 'T00:00:00')
              const isSat = dt.getDay() === 6
              const isSun = dt.getDay() === 0
              const cnt = (allRaces ?? []).filter(r => r.race_date === d).length
              return (
                <button key={d}
                  onClick={() => { setSelectedDate(d); setVenueFilter(null) }}
                  className={`flex flex-col items-center px-3 py-1.5 rounded-lg text-xs min-w-[56px] transition-colors ${
                    isActive ? 'bg-emerald-500 text-white shadow' :
                    isToday ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 ring-1 ring-emerald-400' :
                    isSun ? 'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30' :
                    isSat ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/30' :
                    'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                  }`}>
                  <span className="font-bold leading-tight">{dt.getMonth() + 1}/{dt.getDate()}</span>
                  <span className={`text-[10px] leading-tight ${isActive ? 'text-white/80' : ''}`}>
                    {DAY_N[dt.getDay()]} · {cnt}R
                  </span>
                </button>
              )
            })}
          </div>
        ) : !isLoading ? (
          <div className="text-xs text-gray-400 pb-2">この週の開催なし</div>
        ) : null}
      </div>

      {/* === 競馬場タブ === */}
      {/* 競馬場タブ（ダークモード対応） */}
      {venues.length > 1 && (
        <div className="flex gap-1 px-3 py-1.5 border-b border-gray-200 dark:border-gray-700 overflow-x-auto">
          <button onClick={() => setVenueFilter(null)}
            className={`px-2 py-0.5 text-xs rounded-full whitespace-nowrap ${
              !venueFilter ? 'bg-emerald-500 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
            }`}>全場</button>
          {venues.map(v => (
            <button key={v} onClick={() => setVenueFilter(v)}
              className={`px-2 py-0.5 text-xs rounded-full whitespace-nowrap ${
                venueFilter === v ? 'bg-emerald-500 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
              }`}>{VENUE[v] ?? v}</button>
          ))}
        </div>
      )}

      {/* === フィルター === */}
      {/* フィルター（ダークモード対応） */}
      <div className="px-3 py-1 border-b border-gray-200 dark:border-gray-700">
        <button onClick={() => setShowFilter(!showFilter)}
          className="text-[10px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 flex items-center gap-0.5">
          <svg className={`w-2.5 h-2.5 transition-transform ${showFilter ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
          絞り込み
        </button>
        {showFilter && (
          <div className="mt-1.5 space-y-1.5 pb-1.5">
            <input type="text" placeholder="レース名検索..." value={raceName}
              onChange={(e) => setRaceName(e.target.value)}
              className="w-full bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 rounded px-2 py-0.5 text-xs placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-emerald-400" />
            <div className="flex gap-1">
              {([null, 1, 2] as (number | null)[]).map(t => (
                <button key={String(t)} onClick={() => setTrackType(t)}
                  className={`px-2 py-0.5 text-[10px] rounded ${trackType === t ? 'bg-emerald-500 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400'}`}>
                  {t === null ? '全' : TRACK_L[t]}
                </button>
              ))}
            </div>
            <div className="flex gap-1">
              {([null, 1, 2, 3, 4] as (number | null)[]).map(c => (
                <button key={String(c)} onClick={() => setCondFilter(c)}
                  className={`px-2 py-0.5 text-[10px] rounded ${condFilter === c ? 'bg-emerald-500 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400'}`}>
                  {c === null ? '全' : COND_L[c]}
                </button>
              ))}
            </div>
            <div className="flex gap-3 text-[10px] text-gray-600 dark:text-gray-400">
              <label className="flex items-center gap-0.5">
                <input type="checkbox" checked={handicapOnly} onChange={e => setHandicapOnly(e.target.checked)} className="accent-emerald-500 w-3 h-3" /> ハンデ
              </label>
              <label className="flex items-center gap-0.5">
                <input type="checkbox" checked={femaleOnly} onChange={e => setFemaleOnly(e.target.checked)} className="accent-emerald-500 w-3 h-3" /> 牝馬限定
              </label>
            </div>
          </div>
        )}
      </div>

      {/* === レース一覧 === */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && <div className="p-4 text-xs text-gray-400">読み込み中...</div>}
        {isError && <div className="p-4 text-xs text-red-500">データ取得エラー</div>}

        {!isLoading && filtered.length === 0 && activeDate && (
          <div className="p-4 text-xs text-gray-400">レースなし</div>
        )}

        {/* 場ごとにセクション表示 */}
        {[...grouped.entries()].map(([vc, races]) => (
          <div key={vc}>
            {/* 場ヘッダー（全場表示時のみ） */}
            {!venueFilter && grouped.size > 1 && (
              <div className="px-3 py-1 bg-gray-50 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700 sticky top-0 z-10">
                <span className="text-[10px] font-bold text-gray-500 dark:text-gray-400">{VENUE[vc] ?? vc}</span>
              </div>
            )}
            {races.map(race => {
              const isSelected = race.race_key === selectedRaceKey
              const vn = VENUE[race.venue_code] ?? race.venue_code
              return (
                <button key={race.race_key} onClick={() => onSelect(race.race_key)}
                  className={`w-full text-left px-3 py-2 border-b border-gray-100 dark:border-gray-700 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 transition-colors ${
                    isSelected ? 'bg-emerald-50 dark:bg-emerald-900/20 border-l-[3px] border-l-emerald-500' : ''
                  }`}>
                  <div className="flex items-center justify-between mb-0.5">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] text-gray-400 w-8">{race.race_num}R</span>
                      <span className="text-xs font-medium text-gray-700 dark:text-gray-200 truncate">
                        {race.race_name || `${vn}${race.race_num}R`}
                      </span>
                    </div>
                    <div className="flex items-center gap-0.5 shrink-0">
                      {race.is_female_only && <span className="text-[9px] px-1 py-0.5 rounded bg-pink-100 dark:bg-pink-900/40 text-pink-600 dark:text-pink-400">♀</span>}
                      {race.is_handicap && <span className="text-[9px] px-1 py-0.5 rounded bg-orange-100 dark:bg-orange-900/40 text-orange-600 dark:text-orange-400">H</span>}
                      {race.grade != null && GRADE_L[race.grade] && (
                        <span className={`text-[9px] px-1 py-0.5 rounded font-bold ${GRADE_C[race.grade]}`}>
                          {GRADE_L[race.grade]}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-[10px] text-gray-400 pl-8">
                    {TRACK_L[race.track_type]}{race.distance}m
                    {race.track_cond ? ` · ${COND_L[race.track_cond]}` : ''}
                    {race.horse_count ? ` · ${race.horse_count}頭` : ''}
                  </div>
                </button>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
