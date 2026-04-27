/**
 * オッズ推移グラフコンポーネント
 * odds_snapshotsのデータをrechartsで表示する
 */
import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchOddsTimeline } from '../api/client'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer
} from 'recharts'

const COLORS = [
  '#10b981', '#3b82f6', '#ef4444', '#f59e0b', '#8b5cf6',
  '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1',
  '#14b8a6', '#e11d48', '#a855f7', '#0ea5e9', '#22c55e',
  '#eab308', '#d946ef', '#f43f5e',
]

const SNAPSHOT_ORDER = ['前日', '当日朝', '当日昼', '締切直前', '確定']

interface Props {
  raceKey: string
}

export default function OddsChart({ raceKey }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ['odds-timeline', raceKey],
    queryFn: () => fetchOddsTimeline(raceKey),
  })

  // スナップショットを馬番×時点のマトリクスに変換
  const { chartData, horseNums } = useMemo(() => {
    if (!data?.snapshots || data.snapshots.length === 0) {
      return { chartData: [], horseNums: [] }
    }

    // ユニークな馬番とスナップショット種別を取得
    const nums = [...new Set(data.snapshots.map((s: any) => s.horse_num))].sort((a: number, b: number) => a - b)
    const types = [...new Set(data.snapshots.map((s: any) => s.snapshot_label))]
    // スナップショット種別をソート
    types.sort((a, b) => {
      const ia = SNAPSHOT_ORDER.indexOf(a)
      const ib = SNAPSHOT_ORDER.indexOf(b)
      return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
    })

    // チャートデータ構築
    const rows = types.map(type => {
      const row: any = { name: type }
      for (const num of nums) {
        const snap = data.snapshots.find((s: any) => s.horse_num === num && s.snapshot_label === type)
        if (snap?.odds_win) {
          row[`馬${num}`] = snap.odds_win
        }
      }
      return row
    })

    return { chartData: rows, horseNums: nums }
  }, [data])

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700 animate-pulse-soft">
        <div className="h-64 flex items-center justify-center text-gray-400">読み込み中...</div>
      </div>
    )
  }

  if (chartData.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
        <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 mb-2">オッズ推移</h3>
        <div className="h-32 flex items-center justify-center text-gray-400 text-sm">
          オッズ推移データなし
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border border-gray-200 dark:border-gray-700 animate-fade-in">
      <h3 className="text-sm font-bold text-gray-700 dark:text-gray-300 mb-4">オッズ推移</h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData} margin={{ top: 5, right: 30, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
          <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#9ca3af' }} />
          <YAxis tick={{ fontSize: 12, fill: '#9ca3af' }} />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1f2937',
              border: '1px solid #374151',
              borderRadius: '8px',
              fontSize: '12px',
            }}
            labelStyle={{ color: '#e5e7eb' }}
          />
          <Legend wrapperStyle={{ fontSize: '11px' }} />
          {horseNums.slice(0, 18).map((num: number, i: number) => (
            <Line
              key={num}
              type="monotone"
              dataKey={`馬${num}`}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={2}
              dot={{ r: 3 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
