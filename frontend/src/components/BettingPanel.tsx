/**
 * 買い目計算パネル — フォーメーション / ボックス / ながし
 * RaceDetail ページ内のタブとして表示する
 */
import { useState, useCallback } from 'react'
import { calcFormation, calcBox, calcNagashi, getExportUrl } from '../api/client'

// --- 型定義 ---
interface EntryItem {
  horse_num: number
  horse_name: string | null
  odds_win: number | null
}

interface Props {
  entries: EntryItem[]
  raceKey: string
}

/** 計算モード */
type CalcMode = 'formation' | 'box' | 'nagashi'

/** 馬券種別 */
const BET_TYPES = ['馬連', 'ワイド', '馬単', '三連複', '三連単'] as const
type BetType = typeof BET_TYPES[number]

/** 三連系の馬券かどうか */
function isTripleBet(bt: BetType): boolean {
  return bt === '三連複' || bt === '三連単'
}

/** API レスポンス型 */
interface CalcResult {
  combinations: string[]
  count: number
  total_cost: number
}

// --- メインコンポーネント ---
export default function BettingPanel({ entries, raceKey }: Props) {
  // 計算モード・馬券種別
  const [mode, setMode] = useState<CalcMode>('formation')
  const [betType, setBetType] = useState<BetType>('馬連')

  // フォーメーション用: 1着/2着/3着
  const [first, setFirst] = useState<Set<number>>(new Set())
  const [second, setSecond] = useState<Set<number>>(new Set())
  const [third, setThird] = useState<Set<number>>(new Set())

  // ボックス用
  const [boxSel, setBoxSel] = useState<Set<number>>(new Set())

  // ながし用: 軸馬・相手馬
  const [axis, setAxis] = useState<Set<number>>(new Set())
  const [partners, setPartners] = useState<Set<number>>(new Set())

  // 金額・結果
  const [amount, setAmount] = useState(100)
  const [result, setResult] = useState<CalcResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  // 馬番リスト（ソート済み）
  const horseNums = entries.map(e => e.horse_num).sort((a, b) => a - b)

  // 馬名マップ
  const nameMap = new Map(entries.map(e => [e.horse_num, e.horse_name]))

  /** チェックボックスのトグル */
  const toggle = useCallback((set: Set<number>, setter: React.Dispatch<React.SetStateAction<Set<number>>>, num: number) => {
    setter(prev => {
      const next = new Set(prev)
      next.has(num) ? next.delete(num) : next.add(num)
      return next
    })
  }, [])

  /** 選択状態をすべてクリア */
  const clearAll = useCallback(() => {
    setFirst(new Set())
    setSecond(new Set())
    setThird(new Set())
    setBoxSel(new Set())
    setAxis(new Set())
    setPartners(new Set())
    setResult(null)
    setError(null)
  }, [])

  /** 計算実行 */
  const handleCalc = async () => {
    setError(null)
    setResult(null)
    setLoading(true)
    try {
      let data: CalcResult
      if (mode === 'formation') {
        // フォーメーション計算
        const payload: { bet_type: string; first: number[]; second: number[]; third?: number[]; amount?: number } = {
          bet_type: betType,
          first: [...first],
          second: [...second],
          amount,
        }
        if (isTripleBet(betType)) {
          payload.third = [...third]
        }
        data = await calcFormation(payload)
      } else if (mode === 'box') {
        // ボックス計算
        data = await calcBox({
          bet_type: betType,
          horses: [...boxSel],
          amount,
        })
      } else {
        // ながし計算
        data = await calcNagashi({
          bet_type: betType,
          axis: [...axis],
          partners: [...partners],
          amount,
        })
      }
      setResult(data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '計算に失敗しました'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  /** 組み合わせをクリップボードにコピー */
  const handleCopy = async () => {
    if (!result) return
    const text = result.combinations.join('\n')
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // --- チェックボックス行の描画 ---
  const renderCheckboxRow = (
    label: string,
    selected: Set<number>,
    setter: React.Dispatch<React.SetStateAction<Set<number>>>,
  ) => (
    <div className="flex items-start gap-2 mb-2">
      <span className="text-xs text-gray-500 dark:text-gray-400 font-bold w-10 pt-1 shrink-0">{label}</span>
      <div className="flex flex-wrap gap-1.5">
        {horseNums.map(num => (
          <label
            key={num}
            className="flex items-center gap-1 cursor-pointer select-none bg-gray-50 dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 rounded px-1.5 py-1 text-xs transition-colors"
            title={nameMap.get(num) ?? undefined}
          >
            <input
              type="checkbox"
              checked={selected.has(num)}
              onChange={() => toggle(selected, setter, num)}
              className="accent-emerald-500 w-3.5 h-3.5"
            />
            <span className="font-bold text-gray-700 dark:text-gray-200">{num}</span>
          </label>
        ))}
      </div>
    </div>
  )

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 space-y-4">

      {/* --- モードタブ --- */}
      <div className="flex gap-1">
        {([
          { key: 'formation' as CalcMode, label: 'フォーメーション' },
          { key: 'box' as CalcMode, label: 'ボックス' },
          { key: 'nagashi' as CalcMode, label: 'ながし' },
        ]).map(item => (
          <button
            key={item.key}
            onClick={() => { setMode(item.key); clearAll() }}
            className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
              mode === item.key
                ? 'bg-emerald-500 text-white'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* --- 馬券種別セレクタ --- */}
      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-500 dark:text-gray-400 font-bold">馬券種別</label>
        <select
          value={betType}
          onChange={e => { setBetType(e.target.value as BetType); setResult(null) }}
          className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
        >
          {BET_TYPES.map(bt => (
            <option key={bt} value={bt}>{bt}</option>
          ))}
        </select>
      </div>

      {/* --- 馬番選択UI --- */}
      <div className="space-y-1">
        {mode === 'formation' && (
          <>
            {renderCheckboxRow('1着', first, setFirst)}
            {renderCheckboxRow('2着', second, setSecond)}
            {/* 三連系の場合のみ3着行を表示 */}
            {isTripleBet(betType) && renderCheckboxRow('3着', third, setThird)}
          </>
        )}

        {mode === 'box' && (
          renderCheckboxRow('選択', boxSel, setBoxSel)
        )}

        {mode === 'nagashi' && (
          <>
            {renderCheckboxRow('軸馬', axis, setAxis)}
            {renderCheckboxRow('相手', partners, setPartners)}
          </>
        )}
      </div>

      {/* --- 金額入力 + 計算ボタン --- */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1">
          <label className="text-xs text-gray-500 dark:text-gray-400 font-bold">1点あたり</label>
          <input
            type="number"
            min={100}
            step={100}
            value={amount}
            onChange={e => setAmount(Number(e.target.value))}
            className="w-24 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 rounded-lg px-2 py-1 text-sm text-right focus:outline-none focus:ring-2 focus:ring-emerald-300"
          />
          <span className="text-xs text-gray-400">円</span>
        </div>
        <button
          onClick={handleCalc}
          disabled={loading}
          className="px-4 py-1.5 bg-emerald-500 hover:bg-emerald-600 disabled:bg-emerald-300 text-white text-sm font-medium rounded-lg transition-colors"
        >
          {loading ? '計算中...' : '計算'}
        </button>
        <button
          onClick={clearAll}
          className="px-3 py-1.5 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-500 dark:text-gray-400 text-sm rounded-lg transition-colors"
        >
          クリア
        </button>
      </div>

      {/* --- エラー表示 --- */}
      {error && (
        <div className="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {/* --- 計算結果 --- */}
      {result && (
        <div className="space-y-3">
          {/* サマリー */}
          <div className="flex items-center gap-4 text-sm">
            <span className="text-gray-500 dark:text-gray-400">
              点数: <span className="font-bold text-gray-800 dark:text-gray-200">{result.count}</span>点
            </span>
            <span className="text-gray-500 dark:text-gray-400">
              合計: <span className="font-bold text-gray-800 dark:text-gray-200">{result.total_cost.toLocaleString()}</span>円
            </span>
          </div>

          {/* 組み合わせ一覧（スクロール） */}
          <div className="border border-gray-200 dark:border-gray-600 rounded-lg max-h-48 overflow-y-auto bg-gray-50 dark:bg-gray-700 p-2">
            {result.combinations.length > 0 ? (
              <ul className="text-xs text-gray-700 dark:text-gray-200 font-mono space-y-0.5">
                {result.combinations.map((combo, i) => (
                  <li key={i} className="px-1 py-0.5 hover:bg-gray-100 dark:hover:bg-gray-600 rounded">
                    {combo}
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-xs text-gray-400 dark:text-gray-500 text-center py-2">組み合わせなし</div>
            )}
          </div>

          {/* コピー + CSVダウンロード */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleCopy}
              className="px-3 py-1.5 bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-medium rounded-lg transition-colors"
            >
              {copied ? 'コピーしました' : 'コピー'}
            </button>
            <a
              href={getExportUrl(raceKey)}
              target="_blank"
              rel="noopener noreferrer"
              className="px-3 py-1.5 border border-emerald-500 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-900/30 text-xs font-medium rounded-lg transition-colors"
            >
              CSVダウンロード
            </a>
          </div>
        </div>
      )}
    </div>
  )
}
