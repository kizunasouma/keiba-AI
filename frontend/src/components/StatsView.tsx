/**
 * 統計DB画面 — 種牡馬別/母父別/枠番別/人気別成績 + データマイニング
 * バックエンドの /stats/* エンドポイントを使用
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchSireStats, fetchBmsStats, fetchFrameStats, fetchPopularityStats, fetchMiningStats } from '../api/client'

const TRACK_OPT = [{ v: undefined, l: '全体' }, { v: 1, l: '芝' }, { v: 2, l: 'ダート' }]
const VENUE_OPT = [
  { v: '', l: '全場' }, { v: '05', l: '東京' }, { v: '06', l: '中山' }, { v: '09', l: '阪神' },
  { v: '08', l: '京都' }, { v: '07', l: '中京' }, { v: '04', l: '新潟' },
  { v: '01', l: '札幌' }, { v: '02', l: '函館' }, { v: '03', l: '福島' }, { v: '10', l: '小倉' },
]
const COND_OPT = [{ v: undefined, l: '全' }, { v: 1, l: '良' }, { v: 2, l: '稍' }, { v: 3, l: '重' }, { v: 4, l: '不' }]

type Tab = 'sire' | 'bms' | 'frame' | 'popularity' | 'mining'

function StatTable<T extends Record<string, unknown>>({ data, columns }: { data: T[]; columns: { key: string; label: string; align?: string; fmt?: (v: unknown) => string | React.ReactNode }[] }) {
  if (!data || data.length === 0) return <div className="text-gray-500 text-sm py-8 text-center">データなし</div>
  return (
    /* 統計テーブル: 横スクロール対応 */
    <div className="overflow-x-auto">
    <table className="min-w-[500px] w-full text-sm">
      <thead>
        <tr className="text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
          {columns.map(c => <th key={c.key} className={`px-3 py-2 ${c.align === 'right' ? 'text-right' : c.align === 'center' ? 'text-center' : 'text-left'}`}>{c.label}</th>)}
        </tr>
      </thead>
      <tbody>
        {/* テーブル行: 交互色で視認性向上 */}
        {data.map((row, i) => (
          <tr key={i} className={`border-t border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/20 ${i % 2 === 0 ? '' : 'bg-gray-50 dark:bg-gray-800/40'}`}>
            {columns.map(c => (
              <td key={c.key} className={`px-3 py-2 ${c.align === 'right' ? 'text-right' : c.align === 'center' ? 'text-center' : ''}`}>
                {c.fmt ? c.fmt(row[c.key]) : row[c.key]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  )
}

export default function StatsView() {
  const [tab, setTab] = useState<Tab>('sire')
  const [trackFilter, setTrackFilter] = useState<number | undefined>(undefined)
  const [venueFilter, setVenueFilter] = useState<string>('')
  // データマイニング用
  const [mTrack, setMTrack] = useState<number | undefined>(undefined)
  const [mDistMin, setMDistMin] = useState<string>('')
  const [mDistMax, setMDistMax] = useState<string>('')
  const [mVenue, setMVenue] = useState<string>('')
  const [mCond, setMCond] = useState<number | undefined>(undefined)
  const [mFrame, setMFrame] = useState<string>('')
  const [mPopMax, setMPopMax] = useState<string>('')
  const [mCorner4Max, setMCorner4Max] = useState<string>('')
  const [mSire, setMSire] = useState<string>('')
  const [mResult, setMResult] = useState<Record<string, unknown>[] | null>(null)
  const [mLoading, setMLoading] = useState(false)

  const { data: sireData } = useQuery({ queryKey: ['stats-sire', trackFilter], queryFn: () => fetchSireStats({ track_type: trackFilter, limit: 50 }), enabled: tab === 'sire' })
  const { data: bmsData } = useQuery({ queryKey: ['stats-bms', trackFilter], queryFn: () => fetchBmsStats({ track_type: trackFilter, limit: 50 }), enabled: tab === 'bms' })
  const { data: frameData } = useQuery({ queryKey: ['stats-frame', venueFilter, trackFilter], queryFn: () => fetchFrameStats({ venue_code: venueFilter || undefined, track_type: trackFilter }), enabled: tab === 'frame' })
  const { data: popData } = useQuery({ queryKey: ['stats-pop'], queryFn: () => fetchPopularityStats(), enabled: tab === 'popularity' })

  const doMining = async () => {
    setMLoading(true)
    try {
      const params: Record<string, unknown> = {}
      if (mTrack) params.track_type = mTrack
      if (mDistMin) params.distance_min = Number(mDistMin)
      if (mDistMax) params.distance_max = Number(mDistMax)
      if (mVenue) params.venue_code = mVenue
      if (mCond) params.track_cond = mCond
      if (mFrame) params.frame_num = Number(mFrame)
      if (mPopMax) params.popularity_max = Number(mPopMax)
      if (mCorner4Max) params.corner4_max = Number(mCorner4Max)
      if (mSire) params.sire = mSire
      const result = await fetchMiningStats(params)
      setMResult(result)
    } finally {
      setMLoading(false)
    }
  }

  const fmtRate = (v: unknown) => v != null ? <span className={Number(v) >= 15 ? 'text-emerald-600 dark:text-emerald-400 font-bold' : ''}>{String(v)}%</span> : '-'

  const TABS: { key: Tab; label: string; icon: string }[] = [
    { key: 'sire', label: '種牡馬別', icon: '🐎' },
    { key: 'bms', label: '母父別', icon: '🧬' },
    { key: 'frame', label: '枠番別', icon: '🔢' },
    { key: 'popularity', label: '人気別', icon: '📈' },
    { key: 'mining', label: 'データマイニング', icon: '⛏' },
  ]

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-1">📊 統計データベース</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">蓄積されたレースデータの統計分析</p>
      </div>

      {/* タブ */}
      <div className="flex gap-1 mb-6 border-b border-gray-200 dark:border-gray-700 pb-1">
        {TABS.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded-t-lg text-sm font-medium transition-colors ${
              tab === t.key ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white border border-gray-200 dark:border-gray-700 border-b-white dark:border-b-gray-900 -mb-px' : 'text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
            }`}>{t.icon} {t.label}</button>
        ))}
      </div>

      {/* === 種牡馬別 === */}
      {tab === 'sire' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center gap-2">
            <span className="text-sm text-gray-500 dark:text-gray-400">コース:</span>
            {TRACK_OPT.map(o => (
              <button key={String(o.v)} onClick={() => setTrackFilter(o.v)}
                className={`px-3 py-1 text-xs rounded ${trackFilter === o.v ? 'bg-emerald-600 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400'}`}>{o.l}</button>
            ))}
          </div>
          <StatTable data={sireData ?? []} columns={[
            { key: 'sire', label: '種牡馬' },
            { key: 'runs', label: '出走', align: 'right' },
            { key: 'wins', label: '勝利', align: 'right' },
            { key: 'top2', label: '連対', align: 'right' },
            { key: 'top3', label: '複勝', align: 'right' },
            { key: 'win_rate', label: '勝率', align: 'right', fmt: fmtRate },
          ]} />
        </div>
      )}

      {/* === 母父別 === */}
      {tab === 'bms' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center gap-2">
            <span className="text-sm text-gray-500 dark:text-gray-400">コース:</span>
            {TRACK_OPT.map(o => (
              <button key={String(o.v)} onClick={() => setTrackFilter(o.v)}
                className={`px-3 py-1 text-xs rounded ${trackFilter === o.v ? 'bg-emerald-600 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400'}`}>{o.l}</button>
            ))}
          </div>
          <StatTable data={bmsData ?? []} columns={[
            { key: 'bms', label: '母父' },
            { key: 'runs', label: '出走', align: 'right' },
            { key: 'wins', label: '勝利', align: 'right' },
            { key: 'top3', label: '複勝', align: 'right' },
            { key: 'win_rate', label: '勝率', align: 'right', fmt: fmtRate },
          ]} />
        </div>
      )}

      {/* === 枠番別 === */}
      {tab === 'frame' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center gap-3 flex-wrap">
            <span className="text-sm text-gray-500 dark:text-gray-400">コース:</span>
            {TRACK_OPT.map(o => (
              <button key={String(o.v)} onClick={() => setTrackFilter(o.v)}
                className={`px-3 py-1 text-xs rounded ${trackFilter === o.v ? 'bg-emerald-600 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400'}`}>{o.l}</button>
            ))}
            <span className="text-sm text-gray-500 dark:text-gray-400 ml-4">場:</span>
            <select value={venueFilter} onChange={e => setVenueFilter(e.target.value)}
              className="bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs rounded px-2 py-1 border-none">
              {VENUE_OPT.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
            </select>
          </div>
          {/* 枠番をビジュアル表示 */}
          <div className="p-4">
            <div className="grid grid-cols-8 gap-3">
              {(frameData ?? []).map((f: Record<string, unknown>) => {
                const WAKU_BG: Record<number, string> = {
                  1:'bg-white dark:bg-gray-200 text-gray-800 border border-gray-300',2:'bg-gray-800 text-white border border-gray-600',3:'bg-red-500 text-white',4:'bg-blue-500 text-white',
                  5:'bg-yellow-400 text-gray-800',6:'bg-green-500 text-white',7:'bg-orange-500 text-white',8:'bg-pink-500 text-white'
                }
                const rate = f.runs > 0 ? (f.wins / f.runs * 100) : 0
                return (
                  <div key={f.frame} className="text-center">
                    <div className={`w-12 h-12 rounded-lg flex items-center justify-center text-xl font-bold mx-auto mb-2 ${WAKU_BG[f.frame] ?? 'bg-gray-600'}`}>{f.frame}</div>
                    <div className="text-lg font-bold text-gray-900 dark:text-white">{rate.toFixed(1)}%</div>
                    <div className="text-[10px] text-gray-500">{f.wins}勝/{f.runs}走</div>
                    <div className="text-[10px] text-gray-500">複{f.runs > 0 ? (f.top3 / f.runs * 100).toFixed(1) : 0}%</div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* === 人気別 === */}
      {tab === 'popularity' && (
        <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="p-4">
            {/* 棒グラフ風表示 */}
            <div className="space-y-2">
              {(popData ?? []).map((p: Record<string, unknown>) => {
                const winRate = p.runs > 0 ? p.wins / p.runs * 100 : 0
                const top3Rate = p.runs > 0 ? p.top3 / p.runs * 100 : 0
                return (
                  <div key={p.popularity} className="flex items-center gap-3">
                    <div className="w-12 text-right text-sm font-bold text-gray-700 dark:text-gray-300">{p.popularity}人気</div>
                    <div className="flex-1">
                      <div className="flex gap-1 h-6">
                        <div className="bg-emerald-500 rounded-sm" style={{ width: `${winRate}%` }} title={`勝率 ${winRate.toFixed(1)}%`} />
                        <div className="bg-emerald-200 dark:bg-emerald-800 rounded-sm" style={{ width: `${top3Rate - winRate}%` }} title={`複勝率 ${top3Rate.toFixed(1)}%`} />
                      </div>
                    </div>
                    <div className="w-20 text-right text-xs text-gray-500 dark:text-gray-400">{winRate.toFixed(1)}% / {top3Rate.toFixed(1)}%</div>
                    <div className="w-16 text-right text-xs text-gray-500 dark:text-gray-400">{p.avg_odds?.toFixed(1) ?? '-'}倍</div>
                    <div className="w-16 text-right text-xs text-gray-400 dark:text-gray-600">{p.runs}走</div>
                  </div>
                )
              })}
            </div>
            <div className="flex gap-4 mt-3 text-[10px] text-gray-500">
              <span className="flex items-center gap-1"><span className="w-3 h-3 bg-emerald-500 rounded-sm" /> 勝率</span>
              <span className="flex items-center gap-1"><span className="w-3 h-3 bg-emerald-200 dark:bg-emerald-800 rounded-sm" /> 複勝率(差分)</span>
            </div>
          </div>
        </div>
      )}

      {/* === データマイニング === */}
      {tab === 'mining' && (
        <div className="space-y-4">
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4">
            <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 mb-3">条件を指定して検索</h3>
            <div className="grid grid-cols-4 gap-3 text-xs">
              {/* コース */}
              <div>
                <label className="text-gray-500 block mb-1">コース</label>
                <div className="flex gap-1">
                  {TRACK_OPT.map(o => (
                    <button key={String(o.v)} onClick={() => setMTrack(o.v)}
                      className={`px-2 py-1 rounded ${mTrack === o.v ? 'bg-emerald-600 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400'}`}>{o.l}</button>
                  ))}
                </div>
              </div>
              {/* 距離 */}
              <div>
                <label className="text-gray-500 block mb-1">距離(m)</label>
                <div className="flex gap-1">
                  <input value={mDistMin} onChange={e => setMDistMin(e.target.value)} placeholder="下限" className="w-16 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded px-2 py-1 border-none" />
                  <span className="text-gray-500">〜</span>
                  <input value={mDistMax} onChange={e => setMDistMax(e.target.value)} placeholder="上限" className="w-16 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded px-2 py-1 border-none" />
                </div>
              </div>
              {/* 場 */}
              <div>
                <label className="text-gray-500 block mb-1">競馬場</label>
                <select value={mVenue} onChange={e => setMVenue(e.target.value)} className="bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded px-2 py-1 border-none w-full">
                  {VENUE_OPT.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
                </select>
              </div>
              {/* 馬場 */}
              <div>
                <label className="text-gray-500 block mb-1">馬場状態</label>
                <div className="flex gap-1">
                  {COND_OPT.map(o => (
                    <button key={String(o.v)} onClick={() => setMCond(o.v)}
                      className={`px-2 py-1 rounded ${mCond === o.v ? 'bg-emerald-600 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400'}`}>{o.l}</button>
                  ))}
                </div>
              </div>
              {/* 枠番 */}
              <div>
                <label className="text-gray-500 block mb-1">枠番</label>
                <input value={mFrame} onChange={e => setMFrame(e.target.value)} placeholder="1〜8" className="w-16 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded px-2 py-1 border-none" />
              </div>
              {/* 人気上限 */}
              <div>
                <label className="text-gray-500 block mb-1">人気（〜N番人気）</label>
                <input value={mPopMax} onChange={e => setMPopMax(e.target.value)} placeholder="例:3" className="w-16 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded px-2 py-1 border-none" />
              </div>
              {/* 4角通過順 */}
              <div>
                <label className="text-gray-500 block mb-1">4角通過順（〜N番手）</label>
                <input value={mCorner4Max} onChange={e => setMCorner4Max(e.target.value)} placeholder="例:5" className="w-16 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded px-2 py-1 border-none" />
              </div>
              {/* 父馬 */}
              <div>
                <label className="text-gray-500 block mb-1">父馬名</label>
                <input value={mSire} onChange={e => setMSire(e.target.value)} placeholder="部分一致" className="w-full bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded px-2 py-1 border-none" />
              </div>
            </div>
            <button onClick={doMining} disabled={mLoading}
              className="mt-4 px-6 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-500 disabled:opacity-50 transition-colors">
              {mLoading ? '検索中...' : '⛏ 検索'}
            </button>
          </div>

          {/* 結果 */}
          {mResult && (
            <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6">
              <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 mb-4">検索結果</h3>
              {mResult.total_runs === 0 ? (
                <div className="text-gray-500 text-center py-8">該当データなし</div>
              ) : (
                <div className="grid grid-cols-4 gap-6">
                  <div className="text-center">
                    <div className="text-3xl font-bold text-gray-900 dark:text-white">{mResult.total_runs.toLocaleString()}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">出走数</div>
                  </div>
                  <div className="text-center">
                    <div className="text-3xl font-bold text-emerald-600 dark:text-emerald-400">{mResult.win_rate}%</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">勝率（{mResult.wins}勝）</div>
                  </div>
                  <div className="text-center">
                    <div className="text-3xl font-bold text-blue-600 dark:text-blue-400">{mResult.top3_rate}%</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">複勝率（{mResult.top3}回）</div>
                  </div>
                  <div className="text-center">
                    <div className="text-3xl font-bold text-yellow-600 dark:text-yellow-400">{mResult.avg_odds ?? '-'}倍</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">平均オッズ</div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
