/**
 * AI予想専用画面 — 期待値ランキング・推奨買い目・モデル情報
 * バックエンドの予測APIを活用して、レースを横断した予想一覧を表示
 */
import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchRaces, fetchPredictions, fetchEntries, fetchBacktestSummary } from '../api/client'
import { toFullWidth } from '../utils/format'

interface Props {
  onOpenRace: (raceKey: string, title?: string) => void
}

const VENUE: Record<string, string> = {
  '05': '東京', '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉',
  '01': '札幌', '02': '函館', '03': '福島', '04': '新潟',
}
const TRACK_L: Record<number, string> = { 1: '芝', 2: 'ダ', 3: '障' }

function toStr(d: Date) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}
function todayStr() { return toStr(new Date()) }
function addDays(d: Date, n: number) { const r = new Date(d); r.setDate(d.getDate() + n); return r }

export default function AIPredictionView({ onOpenRace }: Props) {
  const [selectedDate, setSelectedDate] = useState(todayStr())

  // 週の土日を取得
  const weekDates = useMemo(() => {
    const t = new Date()
    const day = t.getDay()
    const sat = addDays(t, day === 0 ? -1 : 6 - day)
    const sun = addDays(sat, 1)
    const prevSat = addDays(sat, -7)
    const prevSun = addDays(prevSat, 1)
    const nextSat = addDays(sat, 7)
    const nextSun = addDays(nextSat, 1)
    return [prevSat, prevSun, sat, sun, nextSat, nextSun].map(toStr)
  }, [])

  // その日のレースを取得
  const { data: races } = useQuery<any[]>({
    queryKey: ['ai-races', selectedDate],
    queryFn: () => fetchRaces({ race_date: selectedDate, limit: 100 }),
  })

  // 全レースの予測を並行取得
  const raceKeys = races?.map(r => r.race_key) ?? []
  const predQueries = useQuery({
    queryKey: ['ai-all-preds', selectedDate, raceKeys.join(',')],
    queryFn: async () => {
      if (raceKeys.length === 0) return []
      const results = await Promise.allSettled(
        raceKeys.map(async rk => {
          const pred = await fetchPredictions(rk)
          const race = races!.find(r => r.race_key === rk)
          return { raceKey: rk, race, predictions: pred }
        })
      )
      return results
        .filter((r): r is PromiseFulfilledResult<any> => r.status === 'fulfilled')
        .map(r => r.value)
    },
    enabled: raceKeys.length > 0,
  })

  // 全レース横断で期待値ランキング
  const allPredictions = useMemo(() => {
    if (!predQueries.data) return []
    const items: any[] = []
    for (const { raceKey, race, predictions } of predQueries.data) {
      if (!predictions?.predictions) continue
      const vn = VENUE[race?.venue_code] ?? ''
      for (const p of predictions.predictions) {
        items.push({
          ...p,
          raceKey,
          raceLabel: `${vn}${race?.race_num}R`,
          raceName: race?.race_name,
          distance: race?.distance,
          trackType: race?.track_type,
        })
      }
    }
    // 総合スコア = √勝率 × (1 + EV) でソート
    // 勝率のルートを取ることで人気馬と穴馬のバランスを取る
    return items.sort((a, b) => {
      const scoreA = Math.sqrt(a.win_prob ?? 0) * (1 + Math.max(a.expected_value ?? 0, 0))
      const scoreB = Math.sqrt(b.win_prob ?? 0) * (1 + Math.max(b.expected_value ?? 0, 0))
      return scoreB - scoreA
    })
  }, [predQueries.data])

  // EV+の馬だけ
  const evPlus = allPredictions.filter(p => (p.expected_value ?? -999) > 0)

  // レースごとの推奨買い目
  const raceBets = useMemo(() => {
    if (!predQueries.data) return []
    return predQueries.data
      .filter(d => d.predictions?.model_available)
      .map(({ raceKey, race, predictions }) => {
        const vn = VENUE[race?.venue_code] ?? ''
        const sorted = [...(predictions.predictions || [])].sort((a: any, b: any) => b.expected_value - a.expected_value)
        const top3 = sorted.slice(0, 3)
        const evPositive = sorted.filter((p: any) => (p.expected_value ?? -999) > 0)
        return {
          raceKey,
          label: `${vn}${race?.race_num}R`,
          name: race?.race_name,
          distance: race?.distance,
          trackType: race?.track_type,
          grade: race?.grade,
          top3,
          evPositive,
          bestEV: top3[0]?.expected_value ?? -1,
        }
      })
      .sort((a, b) => b.bestEV - a.bestEV)
  }, [predQueries.data])

  const DAY_N = ['日', '月', '火', '水', '木', '金', '土']
  const GRADE_L: Record<number, string> = { 1: 'G1', 2: 'G2', 3: 'G3', 4: '重賞', 5: 'OP' }
  const GRADE_C: Record<number, string> = { 1: 'bg-yellow-400 text-yellow-900', 2: 'bg-red-400 text-white', 3: 'bg-green-400 text-white', 5: 'bg-gray-400 text-white' }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* ヘッダー */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-1">🤖 AI予想</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">AIモデルの予測に基づく期待値分析・推奨買い目</p>
      </div>

      {/* 日付選択 */}
      <div className="flex gap-2 mb-6">
        {weekDates.map(d => {
          const dt = new Date(d + 'T00:00:00')
          const isActive = d === selectedDate
          return (
            <button key={d} onClick={() => setSelectedDate(d)}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                isActive ? 'bg-emerald-600 text-white font-bold' :
                'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 bg-gray-100/50 dark:bg-gray-800/50'
              }`}>
              {dt.getMonth() + 1}/{dt.getDate()}({DAY_N[dt.getDay()]})
            </button>
          )
        })}
      </div>

      {!races || races.length === 0 ? (
        <div className="text-center text-gray-500 py-20">この日のレースデータなし</div>
      ) : (
        <div className="space-y-8">

          {/* === 期待値ランキング TOP20 === */}
          <section>
            <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
              <span className="w-1 h-5 bg-emerald-500 rounded-full" />
              期待値ランキング TOP20
            </h2>
            {predQueries.isLoading && (
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-12 text-center">
                <svg className="w-8 h-8 animate-spin text-emerald-500 mx-auto mb-3" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                <div className="text-sm text-gray-500 dark:text-gray-400">AI予測を計算中... ({races.length}レース)</div>
                <div className="text-xs text-gray-400 mt-1">初回は時間がかかる場合があります</div>
              </div>
            )}
            {!predQueries.isLoading && allPredictions.length === 0 && (
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 text-center text-gray-400">
                予測データなし。「AI推奨生成」ボタンで生成してください。
              </div>
            )}
            {!predQueries.isLoading && allPredictions.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
             <div className="overflow-x-auto">
              <table className="min-w-[900px] w-full text-sm">
                <thead>
                  <tr className="text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/40">
                    <th className="px-3 py-2 text-left">#</th>
                    <th className="px-3 py-2 text-left">レース</th>
                    <th className="px-3 py-2 text-center">馬番</th>
                    <th className="px-3 py-2 text-left">馬名</th>
                    <th className="px-3 py-2 text-left">騎手</th>
                    <th className="px-3 py-2 text-right">単勝</th>
                    <th className="px-3 py-2 text-right">勝率</th>
                    <th className="px-3 py-2 text-right">期待値</th>
                    <th className="px-3 py-2 text-right">実力EV</th>
                    <th className="px-3 py-2 text-right">購入額</th>
                    <th className="px-3 py-2 text-center">推奨</th>
                    <th className="px-3 py-2 text-left">AI見解</th>
                  </tr>
                </thead>
                <tbody>
                  {allPredictions.slice(0, 20).map((p, i) => (
                    <tr key={`${p.raceKey}-${p.horse_num}`}
                      className={`border-t border-gray-100 dark:border-gray-700/50 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/30 ${i < 3 ? 'bg-emerald-50 dark:bg-emerald-900/20' : ''}`}
                      onClick={() => onOpenRace(p.raceKey, `${p.raceLabel} ${p.raceName ?? ''}`)}>
                      <td className="px-3 py-2 text-gray-500 font-bold">{i + 1}</td>
                      <td className="px-3 py-2">
                        <div className="text-gray-700 dark:text-gray-300">{p.raceLabel}</div>
                        <div className="text-[10px] text-gray-500">{p.raceName} {TRACK_L[p.trackType]}{p.distance}m</div>
                      </td>
                      <td className="px-3 py-2 text-center font-bold text-gray-900 dark:text-white">{p.horse_num}</td>
                      <td className="px-3 py-2 text-gray-700 dark:text-gray-200">{toFullWidth(p.horse_name) || `${p.horse_num}番`}</td>
                      <td className="px-3 py-2 text-gray-500 dark:text-gray-400 text-xs">{p.jockey_name}</td>
                      <td className="px-3 py-2 text-right text-gray-500 dark:text-gray-400">{p.odds_win?.toFixed(1) ?? '-'}</td>
                      <td className="px-3 py-2 text-right font-medium">{(p.win_prob * 100).toFixed(1)}%</td>
                      <td className={`px-3 py-2 text-right font-bold ${(p.expected_value ?? -999) >= 0 ? 'text-emerald-400' : 'text-gray-500'}`}>
                        {(p.expected_value ?? -999) >= 0 ? '+' : ''}{(p.expected_value ?? 0).toFixed(3)}
                      </td>
                      <td className={`px-3 py-2 text-right text-xs ${p.ev_no_odds >= 0 ? 'text-blue-400' : 'text-gray-500 dark:text-gray-600'}`}>
                        {p.ev_no_odds != null ? `${p.ev_no_odds >= 0 ? '+' : ''}${p.ev_no_odds.toFixed(3)}` : '-'}
                      </td>
                      <td className="px-3 py-2 text-right">
                        {p.betting_plan ? (
                          <span className="font-bold text-emerald-500">{p.betting_plan.bet_amount.toLocaleString()}円</span>
                        ) : <span className="text-gray-400">-</span>}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {(p.expected_value ?? -999) > 0.2 ? <span className="text-emerald-400 font-bold">◎</span> :
                         (p.expected_value ?? -999) > 0 ? <span className="text-emerald-300">○</span> :
                         <span className="text-gray-500 dark:text-gray-600">-</span>}
                      </td>
                      <td className="px-3 py-2 text-left text-xs text-gray-600 dark:text-gray-400 max-w-[300px] truncate" title={p.ai_comment || ''}>
                        {p.ai_comment || '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
             </div>
            </div>
            )}
          </section>

          {/* === レース別 推奨買い目 === */}
          <section>
            <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
              <span className="w-1 h-5 bg-blue-500 rounded-full" />
              レース別 推奨買い目
            </h2>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {raceBets.slice(0, 12).map(rb => (
                <div key={rb.raceKey}
                  className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 cursor-pointer hover:border-emerald-500 dark:hover:border-emerald-600 transition-colors"
                  onClick={() => onOpenRace(rb.raceKey, `${rb.label} ${rb.name ?? ''}`)}>
                  <div className="flex items-center gap-2 mb-3">
                    {rb.grade != null && GRADE_L[rb.grade] && (
                      <span className={`text-[10px] px-2 py-0.5 rounded font-bold ${GRADE_C[rb.grade] ?? 'bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300'}`}>{GRADE_L[rb.grade]}</span>
                    )}
                    <span className="text-sm font-bold text-gray-900 dark:text-white">{rb.label} {rb.name}</span>
                    <span className="text-xs text-gray-500 ml-auto">{TRACK_L[rb.trackType]}{rb.distance}m</span>
                  </div>

                  {/* TOP3 */}
                  <div className="flex gap-3 mb-3">
                    {rb.top3.map((p: any, i: number) => (
                      <div key={p.horse_num} className={`flex-1 rounded-lg p-2 text-center ${i === 0 ? 'bg-emerald-50 dark:bg-emerald-900/40 border border-emerald-300 dark:border-emerald-700/50' : 'bg-gray-100 dark:bg-gray-700/50'}`}>
                        <div className={`text-sm font-bold ${i === 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-400'}`}>
                          {['◎', '○', '▲'][i]}
                        </div>
                        <div className="text-gray-900 dark:text-white font-bold">{p.horse_num}番</div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{toFullWidth(p.horse_name) || `${p.horse_num}番`}</div>
                        <div className="text-xs font-bold mt-0.5">
                          <span className={(p.expected_value ?? -999) >= 0 ? 'text-emerald-400' : 'text-gray-500'}>
                            EV{(p.expected_value ?? -999) >= 0 ? '+' : ''}{(p.expected_value ?? 0).toFixed(2)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* 買い目提案 */}
                  {rb.evPositive.length > 0 && (
                    <div className="text-xs text-gray-500 dark:text-gray-400 space-y-0.5 border-t border-gray-200 dark:border-gray-700 pt-2">
                      <div><span className="text-gray-400 dark:text-gray-500">単勝:</span> <span className="text-gray-900 dark:text-white font-medium">{rb.evPositive[0]?.horse_num}番</span></div>
                      {rb.evPositive.length >= 2 && (
                        <div><span className="text-gray-400 dark:text-gray-500">馬連:</span> <span className="text-gray-900 dark:text-white font-medium">{rb.evPositive.slice(0, 2).map((p: any) => p.horse_num).sort((a: number, b: number) => a - b).join('-')}</span></div>
                      )}
                      {rb.evPositive.length >= 3 && (
                        <div><span className="text-gray-400 dark:text-gray-500">三連複:</span> <span className="text-gray-900 dark:text-white font-medium">{rb.evPositive.slice(0, 3).map((p: any) => p.horse_num).sort((a: number, b: number) => a - b).join('-')}</span></div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* === サマリー統計 === */}
          <section>
            <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
              <span className="w-1 h-5 bg-yellow-500 rounded-full" />
              本日のAIサマリー
            </h2>
            <div className="grid grid-cols-4 gap-4">
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
                <div className="text-3xl font-bold text-gray-900 dark:text-white">{races?.length ?? 0}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">対象レース</div>
              </div>
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
                <div className="text-3xl font-bold text-emerald-600 dark:text-emerald-400">{evPlus.length}</div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">EV+の馬</div>
              </div>
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
                <div className="text-3xl font-bold text-blue-600 dark:text-blue-400">
                  {evPlus.length > 0 ? `+${(evPlus.reduce((s, p) => s + p.expected_value, 0) / evPlus.length).toFixed(2)}` : '-'}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">平均期待値</div>
              </div>
              <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
                <div className="text-3xl font-bold text-yellow-600 dark:text-yellow-400">
                  {evPlus.length > 0 ? `${(evPlus[0]?.odds_win ?? 0).toFixed(1)}倍` : '-'}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">最高EV馬のオッズ</div>
              </div>
            </div>
          </section>

          {/* === 回収率バックテスト === */}
          <BacktestSection />

          {/* === レース別ケリー基準（自動計算） === */}
          <KellyAutoSection raceBets={raceBets} />
        </div>
      )}
    </div>
  )
}

/** 回収率バックテストセクション */
function BacktestSection() {
  // 今週の土曜を計算
  const getThisWeekSat = () => {
    const t = new Date()
    const d = t.getDay()
    const sat = new Date(t)
    if (d === 6) { /* 土曜 */ }
    else if (d === 0) sat.setDate(t.getDate() - 1)
    else sat.setDate(t.getDate() + (6 - d))
    return sat
  }
  const fmt = (d: Date) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
  const thisSat = getThisWeekSat()
  const thisSun = new Date(thisSat); thisSun.setDate(thisSat.getDate() + 1)

  const [dateFrom, setDateFrom] = useState(fmt(thisSat))
  const [dateTo, setDateTo] = useState(fmt(thisSun))
  const [days, setDays] = useState(7)
  const [useCustom, setUseCustom] = useState(true)
  const [sortKey, setSortKey] = useState<string>('profit')
  const [sortAsc, setSortAsc] = useState(false)

  const { data: bt, isLoading } = useQuery({
    queryKey: ['backtest', days, dateFrom, dateTo, useCustom],
    queryFn: () => useCustom
      ? fetchBacktestSummary(365, 0, 'kelly', dateFrom, dateTo)
      : fetchBacktestSummary(days),
  })
  const toggleSort = (key: string) => {
    if (sortKey === key) setSortAsc(!sortAsc)
    else { setSortKey(key); setSortAsc(false) }
  }
  const sortedHistory = (bt?.bet_history ?? []).slice().sort((a: any, b: any) => {
    const va = a[sortKey] ?? 0, vb = b[sortKey] ?? 0
    return sortAsc ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1)
  })

  // プリセット適用
  const applyPreset = (d: number) => { setUseCustom(false); setDays(d) }
  const applyCustom = (from: string, to: string) => {
    setDateFrom(from); setDateTo(to); setUseCustom(true)
  }

  return (
    <section>
      <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
        <span className="w-1 h-5 bg-purple-500 rounded-full" />
        回収率バックテスト
      </h2>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <button onClick={() => applyCustom(fmt(thisSat), fmt(thisSun))}
          className={`px-3 py-1 text-xs rounded ${useCustom && dateFrom === fmt(thisSat) ? 'bg-purple-600 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700'}`}>
          今週
        </button>
        {[7, 30, 90].map(d => (
          <button key={d} onClick={() => applyPreset(d)}
            className={`px-3 py-1 text-xs rounded ${!useCustom && days === d ? 'bg-purple-600 text-white' : 'bg-gray-100 dark:bg-gray-800 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700'}`}>
            過去{d}日
          </button>
        ))}
        <div className="flex items-center gap-1 ml-2 text-xs text-gray-500">
          <input type="date" value={dateFrom}
            onChange={e => applyCustom(e.target.value, dateTo)}
            className="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 text-xs" />
          <span>〜</span>
          <input type="date" value={dateTo}
            onChange={e => applyCustom(dateFrom, e.target.value)}
            className="px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 text-xs" />
        </div>
      </div>
      {isLoading ? (
        <div className="text-gray-500 text-center py-8">計算中...</div>
      ) : bt ? (
        <div className="space-y-4">
          <div className="grid grid-cols-5 gap-3">
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
              <div className="text-2xl font-bold text-gray-900 dark:text-white">{bt.total_bets}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">購入点数</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
              <div className="text-2xl font-bold text-gray-900 dark:text-white">¥{bt.total_invest?.toLocaleString()}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">投資額</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
              <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">¥{bt.total_return?.toLocaleString()}</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">回収額</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
              <div className={`text-2xl font-bold ${bt.roi >= 100 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>{bt.roi}%</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">回収率</div>
            </div>
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center">
              <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">{bt.hit_rate}%</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">的中率</div>
            </div>
          </div>

          {/* 日別グラフ */}
          {bt.daily && bt.daily.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">日別損益</div>
              <div className="flex items-end gap-1 h-24">
                {bt.daily.map((d: any, i: number) => {
                  const pnl = d.ret - d.invest
                  const maxAbs = Math.max(...bt.daily.map((x: any) => Math.abs(x.ret - x.invest)), 1)
                  const h = Math.abs(pnl) / maxAbs * 100
                  return (
                    <div key={i} className="flex-1 flex flex-col items-center justify-end h-full" title={`${d.date}: ${pnl >= 0 ? '+' : ''}${pnl}円`}>
                      <div className={`w-full rounded-t ${pnl >= 0 ? 'bg-emerald-500' : 'bg-red-500'}`}
                        style={{ height: `${Math.max(h, 2)}%` }} />
                    </div>
                  )
                })}
              </div>
              <div className="flex justify-between text-[9px] text-gray-500 dark:text-gray-600 mt-1">
                <span>{bt.daily[0]?.date}</span>
                <span>{bt.daily[bt.daily.length - 1]?.date}</span>
              </div>
            </div>
          )}

          {/* 的中履歴テーブル */}
          {bt.bet_history && bt.bet_history.length > 0 && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
              <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between">
                <span className="text-xs font-bold text-gray-700 dark:text-gray-200">購入履歴（直近{bt.bet_history.length}件）</span>
                <span className="text-[10px] text-gray-400">的中={bt.bet_history.filter((h: any) => h.hit).length}件</span>
              </div>
              <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-gray-50 dark:bg-gray-700/40">
                    <tr className="text-gray-400 border-b border-gray-200 dark:border-gray-600">
                      {[
                        { key: 'race_date', label: '日付', align: 'text-left' },
                        { key: 'race_label', label: 'レース', align: 'text-left' },
                        { key: 'bet_type', label: '券種', align: 'text-center' },
                        { key: 'combination', label: '組合せ', align: 'text-center' },
                        { key: 'odds', label: 'オッズ', align: 'text-right' },
                        { key: 'bet_amount', label: '購入額', align: 'text-right' },
                        { key: 'finish_order', label: '結果', align: 'text-center' },
                        { key: 'payout', label: '払戻', align: 'text-right' },
                        { key: 'profit', label: '損益', align: 'text-right' },
                      ].map(col => (
                        <th key={col.key}
                          className={`px-3 py-2 ${col.align} cursor-pointer hover:text-gray-600 dark:hover:text-gray-200 select-none`}
                          onClick={() => toggleSort(col.key)}>
                          {col.label}{sortKey === col.key ? (sortAsc ? ' ▲' : ' ▼') : ''}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sortedHistory.map((h: any, i: number) => {
                      const typeColor: Record<string, string> = {
                        '単勝': 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300',
                        '複勝': 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300',
                        '馬連': 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300',
                      }
                      return (
                        <tr key={i} className={`border-t border-gray-100 dark:border-gray-700 ${h.hit ? 'bg-emerald-50 dark:bg-emerald-900/10' : ''}`}>
                          <td className="px-3 py-1.5 text-gray-500">{h.race_date?.slice(5)}</td>
                          <td className="px-3 py-1.5">
                            <span className="text-gray-700 dark:text-gray-200 font-medium">{h.race_label}</span>
                            {h.race_name && <span className="ml-1 text-gray-400 text-[10px]">{h.race_name}</span>}
                          </td>
                          <td className="px-3 py-1.5 text-center">
                            <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${typeColor[h.bet_type] || 'bg-gray-100 dark:bg-gray-700 text-gray-500'}`}>
                              {h.bet_type}
                            </span>
                          </td>
                          <td className="px-3 py-1.5 text-center font-bold font-mono">{h.combination}</td>
                          <td className="px-3 py-1.5 text-right text-gray-500">{h.odds?.toFixed(1)}</td>
                          <td className="px-3 py-1.5 text-right">{h.bet_amount?.toLocaleString()}</td>
                          <td className={`px-3 py-1.5 text-center font-bold ${h.hit ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-400'}`}>
                            {h.hit ? '的中' : `${h.finish_order}着`}
                          </td>
                          <td className="px-3 py-1.5 text-right">
                            {h.hit ? <span className="text-emerald-600 dark:text-emerald-400 font-bold">¥{h.payout?.toLocaleString()}</span> : '-'}
                          </td>
                          <td className={`px-3 py-1.5 text-right font-bold ${h.profit > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-500'}`}>
                            {h.profit > 0 ? '+' : ''}{h.profit?.toLocaleString()}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      ) : null}
    </section>
  )
}

/** レース別ケリー基準 自動計算セクション */
function KellyAutoSection({ raceBets }: { raceBets: any[] }) {
  // 各レースの推奨馬にケリー基準を自動適用
  const kellyData = raceBets
    .filter(rb => rb.evPositive.length > 0)
    .map(rb => {
      const best = rb.top3[0]
      if (!best) return null
      const p = best.win_prob
      const o = best.odds_win ?? 0
      if (p <= 0 || o <= 1) return null
      const b = o - 1
      const q = 1 - p
      const kelly = Math.max(0, (p * b - q) / b)
      const halfKelly = kelly / 2
      const ev = p * o - 1
      return {
        ...rb,
        horseName: best.horse_name,
        horseNum: best.horse_num,
        winProb: p,
        odds: o,
        ev,
        kelly,
        halfKelly,
      }
    })
    .filter(Boolean)
    .sort((a: any, b: any) => b.kelly - a.kelly)

  if (kellyData.length === 0) return null

  return (
    <section>
      <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
        <span className="w-1 h-5 bg-orange-500 rounded-full" />
        レース別 ケリー基準（自動計算）
        <span className="text-xs text-gray-500 font-normal ml-2">EV+のレースのみ表示</span>
      </h2>
      {/* ケリー基準テーブル: 横スクロール対応 */}
      <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
       <div className="overflow-x-auto">
        <table className="min-w-[750px] w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/40">
              <th className="px-3 py-2 text-left">レース</th>
              <th className="px-3 py-2 text-center">推奨馬</th>
              <th className="px-3 py-2 text-right">勝率</th>
              <th className="px-3 py-2 text-right">オッズ</th>
              <th className="px-3 py-2 text-right">期待値</th>
              <th className="px-3 py-2 text-right">ケリー比率</th>
              <th className="px-3 py-2 text-right">ハーフケリー</th>
              <th className="px-3 py-2 text-center">資金10万の場合</th>
            </tr>
          </thead>
          <tbody>
            {kellyData.map((d: any) => (
              <tr key={d.raceKey} className="border-t border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/20">
                <td className="px-3 py-2">
                  <div className="text-gray-700 dark:text-gray-300 font-medium">{d.label}</div>
                  <div className="text-[10px] text-gray-500">{d.name}</div>
                </td>
                <td className="px-3 py-2 text-center">
                  <span className="text-gray-900 dark:text-white font-bold">{d.horseNum}番</span>
                  {d.horseName && <span className="text-xs text-gray-600 dark:text-gray-300 ml-1">{d.horseName}</span>}
                </td>
                <td className="px-3 py-2 text-right">{(d.winProb * 100).toFixed(1)}%</td>
                <td className="px-3 py-2 text-right text-gray-500 dark:text-gray-400">{d.odds.toFixed(1)}</td>
                <td className={`px-3 py-2 text-right font-bold ${d.ev >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {d.ev >= 0 ? '+' : ''}{d.ev.toFixed(3)}
                </td>
                <td className="px-3 py-2 text-right text-orange-400 font-bold">{(d.kelly * 100).toFixed(1)}%</td>
                <td className="px-3 py-2 text-right text-blue-400">{(d.halfKelly * 100).toFixed(1)}%</td>
                <td className="px-3 py-2 text-center text-yellow-400 font-medium">
                  ¥{Math.round(d.halfKelly * 100000).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
       </div>
        <div className="px-3 py-2 text-[10px] text-gray-500 border-t border-gray-200 dark:border-gray-700">
          ケリー基準: f=(p×b-q)/b。ハーフケリー=リスク半減の推奨比率。資金10万円あたりの推奨賭け金を表示。
        </div>
      </div>
    </section>
  )
}
