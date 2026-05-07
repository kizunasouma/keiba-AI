/**
 * レース詳細 — TARGET出馬表の全機能を補完するUI
 * AI予測サマリー → 出馬表 → 分析（ラップ/脚質/枠番/上がり3F） → 買い目 → 払戻
 */
import { useState, useEffect, Fragment, useCallback } from 'react'
import { getExportUrl } from '../api/client'
import { useRaceData, type RaceTab } from '../hooks/useRaceData'
import BettingPanel from './BettingPanel'
import ErrorBanner from './ErrorBanner'
import EmptyState from './EmptyState'
import OddsChart from './OddsChart'
import { toFullWidth } from '../utils/format'

// --- 型 ---
interface Props {
  raceKey: string
  onNavigateHorse?: (horseId: number, name?: string | null) => void
  onNavigateJockey?: (jockeyId: number, name?: string | null) => void
  onNavigateTrainer?: (trainerId: number, name?: string | null) => void
  onTitleReady?: (title: string) => void
}
interface RaceInfo {
  race_key: string; race_name: string | null; race_date: string; venue_code: string
  race_num: number; grade: number | null; distance: number; track_type: number
  track_dir: number | null; weather: number | null; track_cond: number | null
  horse_count: number | null; is_handicap: boolean; is_female_only: boolean
  prize_1st: number | null
  start_time?: string | null  // 発走時刻（例: "11:00"）
}
interface PredictionItem {
  entry_id: number; horse_num: number; horse_name: string | null
  jockey_name: string | null; odds_win: number | null
  win_prob: number; expected_value: number
  win_prob_no_odds?: number | null; ev_no_odds?: number | null
  recommendation: string
}
interface PredictionResponse {
  race_key: string; model_available: boolean; predictions: PredictionItem[]; message: string | null
}
interface TrainingData {
  training_date: string; weeks_before: number | null; course_type: string | null
  distance: number | null; lap_time: number | null; last_3f: number | null
  last_1f: number | null; rank: string | null; note: string | null
}
interface PastRace {
  race_date: string; race_name: string | null; venue: string; distance: number
  track: string; cond: string; horse_count: number | null; grade: number | null
  horse_num: number; popularity: number | null; finish_order: number | null
  finish_time: number | null; last_3f: number | null; weight_carry: number | null
  horse_weight: number | null; weight_diff: number | null; odds_win: number | null
  margin: string | null; corner_text: string | null; speed_index: number | null
  jockey_name: string | null; running_style: string | null
}
interface Entry {
  horse_num: number; frame_num: number; horse_name: string | null
  horse_name_eng: string | null; horse_id: number | null
  jockey_name: string | null; jockey_id: number | null
  trainer_name: string | null; trainer_id: number | null
  age: number | null; sex: number | null; weight_carry: number | null
  horse_weight: number | null; weight_diff: number | null
  odds_win: number | null; odds_place_min: number | null; odds_place_max: number | null
  popularity: number | null; finish_order: number | null; finish_time: number | null
  last_3f: number | null; margin: string | null; margin_text?: string | null; corner_text: string | null
  speed_index: number | null; abnormal_code: number | null
  father: string | null; mother_father: string | null; mother_name: string | null
  running_style: string | null; jockey_change: boolean; is_foreign_jockey: boolean
  interval_days: number | null; total_wins: number | null; total_races: number | null
  total_record: string | null; total_earnings: number | null
  past_races: PastRace[]; training: TrainingData[]
}
interface LapData {
  race_key: string; distance: number
  laps: { order: number; time: number }[]
  pace_analysis: { first_3f: number; last_3f: number; pci: number; pace_label: string } | null
}
interface PayoutData {
  race_key: string; payouts: Record<string, { combination: string; payout: number; popularity: number | null }[]>
}

// --- 定数 ---
const WAKU_BG: Record<number, string> = {
  1: 'bg-white dark:bg-gray-200 border border-gray-300 text-gray-800', 2: 'bg-gray-800 text-white', 3: 'bg-red-500 text-white',
  4: 'bg-blue-600 text-white', 5: 'bg-yellow-400 text-yellow-900', 6: 'bg-green-600 text-white',
  7: 'bg-orange-500 text-white', 8: 'bg-pink-500 text-white',
}
const SEX_L: Record<number, string> = { 1: '牡', 2: '牝', 3: '騸' }
const TRACK_L: Record<number, string> = { 1: '芝', 2: 'ダート', 3: '障害' }
const WEATHER_L: Record<number, string> = { 1: '晴', 2: '曇', 3: '小雨', 4: '雨', 5: '小雪', 6: '雪' }
const COND_L: Record<number, string> = { 1: '良', 2: '稍重', 3: '重', 4: '不良' }
const DIR_L: Record<number, string> = { 1: '右', 2: '左', 3: '直' }
const VENUE: Record<string, string> = {
  '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
  '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉',
}
/** 場名短縮マッピング（過去走横展開用） */
const VENUE_SHORT: Record<string, string> = {
  '札幌': '札', '函館': '函', '福島': '福', '新潟': '新', '東京': '東',
  '中山': '中', '中京': '京', '京都': '都', '阪神': '阪', '小倉': '小',
}
/** 調教評価の色マッピング */
const TRAINING_RATING_COLOR: Record<string, string> = {
  S: 'bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400',
  A: 'bg-orange-100 dark:bg-orange-900/40 text-orange-600 dark:text-orange-400',
  B: 'bg-green-100 dark:bg-green-900/40 text-green-600 dark:text-green-400',
  C: 'bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400',
  D: 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500',
}
const MARKS = ['◎', '○', '▲', '△', '☆'] as const
const STYLE_COLOR: Record<string, string> = {
  '逃': 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300', '先': 'bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300',
  '差': 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300', '追': 'bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300',
}
/* ペースカラー（ダークモード対応） */
const PACE_COLOR: Record<string, string> = { H: 'text-red-600 dark:text-red-400', M: 'text-gray-600 dark:text-gray-300', S: 'text-blue-600 dark:text-blue-400' }
const PACE_LABEL: Record<string, string> = { H: 'ハイ', M: 'ミドル', S: 'スロー' }
/** 異常区分コードに対応するラベル */
const ABNORMAL_L: Record<number, string> = { 1: '取消', 2: '除外', 3: '中止', 4: '失格' }
/** 調教AI評価レスポンス型 */
interface TrainingRatingItem {
  horse_num: number; rating: string; score: number
  course?: string; training_date?: string; last_3f?: number; last_1f?: number
}
interface TrainingRatingResponse {
  race_key: string; ratings: TrainingRatingItem[]
}
type SortKey = 'number' | 'odds' | 'ai_ev' | 'popularity' | 'finish'

// --- 予測ファクター評価の型と算出ロジック ---
/** ファクター評価ランク */
type FactorRank = 'S' | 'A' | 'B' | 'C' | 'D' | '-'

/** 各馬のファクター評価 */
interface FactorEvaluation {
  bloodline: FactorRank   // 血統評価
  training: FactorRank    // 調教評価
  recent: FactorRank      // 直近成績
  course: FactorRank      // コース適性
  pace: FactorRank        // 展開適性
}

/** ファクターランクの色設定（ダークモード対応） */
const FACTOR_RANK_COLOR: Record<FactorRank, { text: string; bg: string; bar: string }> = {
  S: { text: 'text-white',           bg: 'bg-red-600',          bar: 'bg-red-500' },
  A: { text: 'text-white',           bg: 'bg-amber-500',        bar: 'bg-amber-400' },
  B: { text: 'text-white',           bg: 'bg-emerald-600',      bar: 'bg-emerald-500' },
  C: { text: 'text-white',           bg: 'bg-sky-600',          bar: 'bg-sky-500' },
  D: { text: 'text-white',           bg: 'bg-gray-500',         bar: 'bg-gray-400' },
  '-': { text: 'text-gray-400 dark:text-gray-500', bg: 'bg-gray-200 dark:bg-gray-700', bar: 'bg-gray-300' },
}

/** ファクターごとのコメント生成 */
function factorComment(type: string, rank: FactorRank, e: any): string {
  const r = rank
  switch (type) {
    case 'bloodline':
      if (r === 'S') return '血統的に最適。馬場・距離ともに高適性'
      if (r === 'A') return '血統適性あり。条件に合う'
      if (r === 'B') return '血統は平均的。特筆なし'
      if (r === 'C') return '血統面でやや不安'
      if (r === 'D') return '血統的に合わない条件'
      return 'データ不足'
    case 'training':
      if (r === 'S') return '調教抜群。仕上がり万全'
      if (r === 'A') return '好調教。動き良好'
      if (r === 'B') return '調教は普通。平均的な仕上がり'
      if (r === 'C') return '調教やや物足りない'
      if (r === 'D') return '調教評価低い。状態面に不安'
      return '調教データなし'
    case 'recent':
      if (r === 'S') return '絶好調。直近3走で連勝級の成績'
      if (r === 'A') return '好調。安定して上位に来ている'
      if (r === 'B') return '普通。掲示板前後の成績'
      if (r === 'C') return '不調気味。着順が下がっている'
      if (r === 'D') return '大敗続き。巻き返しは困難'
      return '出走歴なし'
    case 'course':
      if (r === 'S') return '同条件で高勝率。コース巧者'
      if (r === 'A') return '同距離・同コースの実績あり'
      if (r === 'B') return 'コース適性は平均的'
      if (r === 'C') return '同条件での好走歴少ない'
      if (r === 'D') return '未経験の条件。不安大きい'
      return 'データ不足'
    case 'pace':
      if (r === 'S') return '脚質と展開が噛み合う。理想的'
      if (r === 'A') return '展開向き。持ち味を出せる'
      if (r === 'B') return '展開は読みにくいが対応可能'
      if (r === 'C') return '展開不向き。位置取りに不安'
      if (r === 'D') return '展開が大きく不利。厳しい'
      return '展開予想不能'
    default: return ''
  }
}

/** ファクターランクを数値スコア(0-100)に変換 */
function rankToScore(rank: FactorRank): number {
  switch (rank) {
    case 'S': return 95
    case 'A': return 75
    case 'B': return 55
    case 'C': return 35
    case 'D': return 15
    default: return 0
  }
}

/** 勝率(0.0〜1.0)からランクを算出 */
function rateToRank(rate: number): FactorRank {
  if (rate >= 0.3) return 'S'
  if (rate >= 0.2) return 'A'
  if (rate >= 0.1) return 'B'
  if (rate >= 0.05) return 'C'
  return 'D'
}

/** 偏差値からランクを算出 */
function deviationToRank(score: number): FactorRank {
  if (score >= 65) return 'S'
  if (score >= 58) return 'A'
  if (score >= 50) return 'B'
  if (score >= 42) return 'C'
  return 'D'
}

/** 総合ランクを算出（各ファクターの加重平均） */
function calcOverallRank(ev: FactorEvaluation): FactorRank {
  const factors: { rank: FactorRank; weight: number }[] = [
    { rank: ev.bloodline, weight: 1.0 },
    { rank: ev.training, weight: 1.2 },
    { rank: ev.recent, weight: 1.5 },
    { rank: ev.course, weight: 1.0 },
    { rank: ev.pace, weight: 0.8 },
  ]
  const valid = factors.filter(f => f.rank !== '-')
  if (valid.length === 0) return '-'
  const totalW = valid.reduce((a, f) => a + f.weight, 0)
  const avg = valid.reduce((a, f) => a + rankToScore(f.rank) * f.weight, 0) / totalW
  if (avg >= 80) return 'S'
  if (avg >= 60) return 'A'
  if (avg >= 45) return 'B'
  if (avg >= 30) return 'C'
  return 'D'
}

/**
 * 各馬のファクター評価を算出する
 * エントリデータと調教評価APIデータからフロントエンドで計算
 */
function calcFactorEvaluation(
  entry: Entry,
  trItem: TrainingRatingItem | undefined,
  raceInfo: RaceInfo,
  paceLabel: string | null,
): FactorEvaluation {
  // --- 血統評価 ---
  // 過去走データから同一馬場種別・距離帯での成績を元に推定
  let bloodline: FactorRank = '-'
  if (entry.past_races && entry.past_races.length > 0 && entry.father) {
    const trackStr = TRACK_L[raceInfo.track_type] || ''
    // 同馬場タイプの過去走成績から血統適性を推定
    const sameTrackRaces = entry.past_races.filter(r => r.track === trackStr)
    if (sameTrackRaces.length >= 2) {
      const avgFinish = sameTrackRaces.reduce((a, r) => a + (r.finish_order ?? 10), 0) / sameTrackRaces.length
      // 平均着順を偏差値風に変換（着順1位=70、5位=50、10位=30）
      const deviation = Math.max(0, 70 - (avgFinish - 1) * 5)
      bloodline = deviationToRank(deviation)
    } else if (entry.past_races.length >= 3) {
      // 同馬場データ不足: 全過去走から推定
      const avgFinish = entry.past_races.slice(0, 5).reduce((a, r) => a + (r.finish_order ?? 10), 0) / Math.min(entry.past_races.length, 5)
      const deviation = Math.max(0, 65 - (avgFinish - 1) * 4)
      bloodline = deviationToRank(deviation)
    }
  }

  // --- 調教評価 ---
  // TrainingRating APIの偏差値スコアから直接算出
  let training: FactorRank = '-'
  if (trItem) {
    training = deviationToRank(trItem.score)
  }

  // --- 直近成績 ---
  // 過去走から平均着順と勝数を計算
  let recent: FactorRank = '-'
  if (entry.past_races && entry.past_races.length > 0) {
    const recentRaces = entry.past_races.slice(0, 3)
    const avgFinish = recentRaces.reduce((a, r) => a + (r.finish_order ?? 10), 0) / recentRaces.length
    const winCount = recentRaces.filter(r => r.finish_order === 1).length
    // 勝利ボーナス付きの偏差値変換
    const deviation = Math.max(0, 70 - (avgFinish - 1) * 5) + winCount * 5
    recent = deviationToRank(Math.min(deviation, 80))
  }

  // --- コース適性 ---
  // 同距離帯(±200m)・同トラック種別の過去走勝率
  let course: FactorRank = '-'
  if (entry.past_races && entry.past_races.length > 0) {
    const trackStr = TRACK_L[raceInfo.track_type] || ''
    const dist = raceInfo.distance
    const sameCondRaces = entry.past_races.filter(r =>
      r.track === trackStr && Math.abs(r.distance - dist) <= 200
    )
    if (sameCondRaces.length >= 2) {
      const winRate = sameCondRaces.filter(r => r.finish_order === 1).length / sameCondRaces.length
      const top3Rate = sameCondRaces.filter(r => r.finish_order != null && r.finish_order <= 3).length / sameCondRaces.length
      // 勝率とTOP3率の加重平均で評価
      const combined = winRate * 0.6 + top3Rate * 0.4
      course = rateToRank(combined)
    } else {
      // データ不足: 同トラックのみで判定
      const sameTrack = entry.past_races.filter(r => r.track === trackStr)
      if (sameTrack.length >= 3) {
        const top3Rate = sameTrack.filter(r => r.finish_order != null && r.finish_order <= 3).length / sameTrack.length
        course = rateToRank(top3Rate * 0.8)
      }
    }
  }

  // --- 展開適性 ---
  // 脚質とレースペースの相性から判定
  let pace: FactorRank = '-'
  // 脚質: running_styleがなければ過去走のcorner_4から推定
  let style = entry.running_style
  if (!style && entry.past_races && entry.past_races.length > 0) {
    const recentCorner4 = entry.past_races.slice(0, 3)
      .map(r => r.corner_4 ?? r.corner_text?.split(',').pop()?.trim())
      .filter(c => c != null)
      .map(c => typeof c === 'string' ? parseInt(c) : c)
      .filter(c => !isNaN(c) && c > 0)
    if (recentCorner4.length > 0) {
      const avg = recentCorner4.reduce((a: number, b: number) => a + b, 0) / recentCorner4.length
      style = avg <= 2 ? '逃' : avg <= 4 ? '先' : avg <= 7 ? '差' : '追'
    }
  }
  if (style && paceLabel) {
    const compatMap: Record<string, Record<string, FactorRank>> = {
      'H': { '逃': 'D', '先': 'C', '差': 'A', '追': 'S' },
      'M': { '逃': 'B', '先': 'B', '差': 'B', '追': 'B' },
      'S': { '逃': 'S', '先': 'A', '差': 'C', '追': 'D' },
    }
    pace = compatMap[paceLabel]?.[style] ?? 'B'
  } else if (style) {
    // ペース不明: 脚質から中間評価（先行・差しは平均的に有利）
    pace = style === '先' ? 'B' : style === '差' ? 'B' : style === '逃' ? 'C' : 'C'
  } else {
    // 脚質も不明: 初出走馬等
    pace = 'C'
  }

  return { bloodline, training, recent, course, pace }
}

/** ファクターランクバッジ表示コンポーネント */
function FactorBadge({ rank, size = 'sm' }: { rank: FactorRank; size?: 'sm' | 'lg' }) {
  const c = FACTOR_RANK_COLOR[rank]
  const cls = size === 'lg'
    ? `inline-flex items-center justify-center w-8 h-8 rounded-lg text-sm font-bold ${c.text} ${c.bg}`
    : `inline-flex items-center justify-center w-5 h-5 rounded text-[10px] font-bold ${c.text} ${c.bg}`
  return <span className={cls}>{rank}</span>
}

/** ファクターバー表示コンポーネント（プログレスバー） */
function FactorBar({ rank }: { rank: FactorRank }) {
  const score = rankToScore(rank)
  const c = FACTOR_RANK_COLOR[rank]
  return (
    <div className="flex items-center gap-1 min-w-[80px]">
      <div className="flex-1 h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${c.bar}`} style={{ width: `${score}%` }} />
      </div>
      <FactorBadge rank={rank} />
    </div>
  )
}

// --- ユーティリティ ---
function fmtTime(v: number | null) {
  if (!v) return '-'
  return `${Math.floor(v / 1000)}:${String(Math.floor((v % 1000) / 10)).padStart(2, '0')}.${v % 10}`
}
function fmt3f(v: number | null) { return v ? (v / 10).toFixed(1) : '-' }
function fmtLap(v: number | null) { return v ? (v / 10).toFixed(1) : '-' }
function fmtPrize(v: number | null) {
  if (!v) return ''
  const m = v / 100
  return m >= 10000 ? `${(m / 10000).toFixed(1)}億` : `${m.toLocaleString()}万`
}
function fmtEarnings(v: number | null) {
  if (!v) return '-'
  return v >= 10000 ? `${(v / 10000).toFixed(1)}億` : `${v.toLocaleString()}万`
}
function Waku({ n }: { n: number }) {
  return <span className={`inline-flex items-center justify-center w-5 h-5 rounded text-[10px] font-bold ${WAKU_BG[n] ?? 'bg-gray-300'}`}>{n}</span>
}
function StyleBadge({ style }: { style: string | null }) {
  if (!style) return null
  return <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${STYLE_COLOR[style] ?? 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400'}`}>{style}</span>
}
/* グレードバッジ（ダークモード対応） */
function GradeBadge({ grade }: { grade: number | null }) {
  if (!grade || grade > 6) return null
  const cls = grade === 1 ? 'bg-yellow-400 text-yellow-900' : grade === 2 ? 'bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-300' :
    grade === 3 ? 'bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300' : 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300'
  const txt = grade <= 3 ? `G${grade}` : grade === 4 ? '重賞' : grade === 5 ? 'OP' : 'L'
  return <span className={`px-1 py-0.5 text-[9px] font-bold rounded ${cls}`}>{txt}</span>
}

// --- 過去走テーブル（展開部分） ---
function PastRacesTable({ races, onNavHorse }: { races: PastRace[]; onNavHorse?: () => void }) {
  if (races.length === 0) return <div className="text-xs text-gray-400 py-2 px-4">過去走データなし</div>
  return (
    /* 過去走テーブル: 横スクロール対応 */
    <div className="overflow-x-auto">
    <table className="min-w-[800px] w-full text-xs">
      <thead>
        <tr className="text-gray-400 border-b border-gray-100 dark:border-gray-700">
          <th className="px-1 py-1 text-left">日付</th>
          <th className="px-1 py-1 text-left">レース</th>
          <th className="px-1 py-1 text-center">距離</th>
          <th className="px-1 py-1 text-center">馬場</th>
          <th className="px-1 py-1 text-center">頭数</th>
          <th className="px-1 py-1 text-center">人気</th>
          <th className="px-1 py-1 text-center">着順</th>
          <th className="px-1 py-1 text-center">着差</th>
          <th className="px-1 py-1 text-right">タイム</th>
          <th className="px-1 py-1 text-right">上3F</th>
          <th className="px-1 py-1 text-center">通過</th>
          <th className="px-1 py-1 text-center">脚質</th>
          <th className="px-1 py-1 text-center">斤量</th>
          <th className="px-1 py-1 text-center">体重</th>
          <th className="px-1 py-1 text-left">騎手</th>
          <th className="px-1 py-1 text-right">単勝</th>
        </tr>
      </thead>
      <tbody>
        {races.map((r, i) => (
          <tr key={i} className={`border-t border-gray-50 dark:border-gray-700 ${r.finish_order === 1 ? 'bg-amber-50 dark:bg-amber-900/20' : r.finish_order != null && r.finish_order <= 3 ? 'bg-gray-50 dark:bg-gray-700/30' : ''}`}>
            <td className="px-1 py-1 text-gray-500">{r.race_date.slice(5)}</td>
            <td className="px-1 py-1 text-gray-600 dark:text-gray-300 truncate max-w-20">
              <div className="flex items-center gap-0.5">
                <GradeBadge grade={r.grade} />
                <span>{r.race_name || `${r.venue}`}</span>
              </div>
            </td>
            <td className="px-1 py-1 text-center text-gray-600 dark:text-gray-300">{r.track}{r.distance}</td>
            <td className="px-1 py-1 text-center text-gray-500">{r.cond}</td>
            <td className="px-1 py-1 text-center text-gray-400">{r.horse_count ?? '-'}</td>
            <td className="px-1 py-1 text-center text-gray-500">{r.popularity ?? '-'}</td>
            <td className="px-1 py-1 text-center">
              <span className={`font-bold ${r.finish_order === 1 ? 'text-amber-600' : r.finish_order != null && r.finish_order <= 3 ? 'text-emerald-600' : 'text-gray-500'}`}>
                {r.finish_order ?? '-'}
              </span>
            </td>
            <td className="px-1 py-1 text-center text-gray-400">{r.margin ?? '-'}</td>
            <td className="px-1 py-1 text-right text-gray-500 tabular-nums">{fmtTime(r.finish_time)}</td>
            <td className="px-1 py-1 text-right text-gray-500 tabular-nums">{fmt3f(r.last_3f)}</td>
            <td className="px-1 py-1 text-center text-gray-400 tabular-nums">{r.corner_text ?? '-'}</td>
            <td className="px-1 py-1 text-center"><StyleBadge style={r.running_style} /></td>
            <td className="px-1 py-1 text-center text-gray-500">{r.weight_carry ?? '-'}</td>
            <td className="px-1 py-1 text-center text-gray-500">
              {r.horse_weight ?? '-'}
              {r.weight_diff != null && r.weight_diff !== 0 && (
                <span className={r.weight_diff > 0 ? 'text-red-500' : 'text-blue-500'}>({r.weight_diff > 0 ? '+' : ''}{r.weight_diff})</span>
              )}
            </td>
            <td className="px-1 py-1 text-gray-500 truncate max-w-14">{r.jockey_name ?? '-'}</td>
            <td className="px-1 py-1 text-right text-gray-500">{r.odds_win ? r.odds_win.toFixed(1) : '-'}</td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  )
}

/** 過去走1レース分をコンパクトに表示（出馬表横展開用） */
function PastRaceCompact({ race }: { race: PastRace }) {
  const vShort = VENUE_SHORT[race.venue] || race.venue?.slice(0, 1) || '?'
  const trackShort = race.track === '芝' ? '芝' : race.track === 'ダート' ? 'ダ' : race.track?.slice(0, 1) || ''
  const distShort = race.distance >= 1000 ? `${Math.floor(race.distance / 100)}` : `${race.distance}`
  const dateStr = race.race_date ? `${race.race_date.slice(5, 7)}/${race.race_date.slice(8, 10)}` : ''
  const orderColor = race.finish_order === 1 ? 'text-red-600 dark:text-red-400 font-bold'
    : race.finish_order != null && race.finish_order <= 3 ? 'text-blue-600 dark:text-blue-400 font-bold'
    : 'text-gray-500 dark:text-gray-400'
  return (
    <div className="flex flex-col leading-tight">
      {/* 1行目: 日付 場 着順 */}
      <div className="flex items-center gap-0.5">
        <span className="text-gray-400 text-[10px]">{dateStr}</span>
        <span className="text-gray-500 text-[10px]">{vShort}</span>
        <span className={`text-xs ${orderColor}`}>{race.finish_order ?? '-'}着</span>
      </div>
      {/* 2行目: 距離 タイム */}
      <div className="flex items-center gap-0.5">
        <span className="text-gray-400 text-[10px]">{trackShort}{distShort}</span>
        <span className="text-gray-500 text-[10px] tabular-nums">{fmtTime(race.finish_time)}</span>
      </div>
      {/* 3行目: 上3F */}
      <div className="text-[10px] text-gray-400 tabular-nums">
        {race.last_3f ? `△${fmt3f(race.last_3f)}` : ''}
      </div>
    </div>
  )
}

// --- 調教データ表示 ---
function TrainingTable({ data }: { data: TrainingData[] }) {
  if (data.length === 0) return null
  return (
    <div className="mt-2">
      <div className="text-xs font-bold text-gray-500 mb-1">調教</div>
      <table className="w-full text-xs">
        <thead><tr className="text-gray-400 border-b border-gray-100 dark:border-gray-700">
          <th className="px-1 py-0.5 text-left">日付</th>
          <th className="px-1 py-0.5 text-center">週前</th>
          <th className="px-1 py-0.5 text-center">コース</th>
          <th className="px-1 py-0.5 text-right">タイム</th>
          <th className="px-1 py-0.5 text-right">上3F</th>
          <th className="px-1 py-0.5 text-center">評価</th>
        </tr></thead>
        <tbody>{data.map((t, i) => (
          <tr key={i} className="border-t border-gray-50 dark:border-gray-700">
            <td className="px-1 py-0.5 text-gray-500">{t.training_date.slice(5)}</td>
            <td className="px-1 py-0.5 text-center text-gray-400">{t.weeks_before ?? '-'}</td>
            <td className="px-1 py-0.5 text-center text-gray-500">{t.course_type ?? '-'}</td>
            <td className="px-1 py-0.5 text-right text-gray-500 tabular-nums">{t.lap_time ? (t.lap_time / 10).toFixed(1) : '-'}</td>
            <td className="px-1 py-0.5 text-right text-gray-500 tabular-nums">{t.last_3f ? (t.last_3f / 10).toFixed(1) : '-'}</td>
            <td className="px-1 py-0.5 text-center">
              {t.rank && <span className={`px-1 rounded text-[10px] font-bold ${t.rank === 'A' ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-400' : t.rank === 'B' ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400' : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400'}`}>{t.rank}</span>}
            </td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  )
}

// --- メインコンポーネント ---
export default function RaceDetail({ raceKey, onNavigateHorse, onNavigateJockey, onNavigateTrainer, onTitleReady }: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [tab, setTab] = useState<RaceTab>('table')
  const [sortKey, setSortKey] = useState<SortKey>('number')

  // データフェッチ（カスタムフックに集約）
  const { race, entries, pred, laps, payoutData, trainingRatingData, isLoading: rl, isError: rErr, refetchRace } = useRaceData(raceKey, tab)
  const el = !entries

  const pm = new Map(pred?.predictions.map(p => [p.horse_num, p]) ?? [])
  // 調教評価マップ（horse_num → TrainingRatingItem）
  const trMap = new Map(trainingRatingData?.ratings.map(r => [r.horse_num, r]) ?? [])
  const hasAI = pred?.model_available ?? false
  const top5 = hasAI ? [...(pred!.predictions)].sort((a, b) => (b.win_prob ?? 0) - (a.win_prob ?? 0)).slice(0, 5) : []
  const toggle = (num: number) => setExpanded(prev => { const s = new Set(prev); s.has(num) ? s.delete(num) : s.add(num); return s })

  // タブタイトルを更新
  const v0 = VENUE[race?.venue_code ?? ''] ?? ''
  useEffect(() => {
    if (race && onTitleReady) {
      const name = race.race_name || `${v0}${race.race_num}R`
      onTitleReady(`${v0}${race.race_num}R ${name}`)
    }
  }, [race, onTitleReady, v0])

  if (rl || el) return <div className="flex items-center justify-center h-full text-gray-400">読み込み中...</div>
  if (rErr) return <div className="p-5"><ErrorBanner message="レース情報の取得に失敗しました" onRetry={() => refetchRace()} /></div>
  if (!race) return <div className="p-5"><EmptyState icon="🏇" title="レース情報なし" description="指定されたレースのデータが存在しません。" /></div>

  const v = VENUE[race.venue_code] ?? race.venue_code
  const byOdds = entries?.slice().sort((a, b) => (a.odds_win ?? 999) - (b.odds_win ?? 999)) ?? []
  const fav = byOdds[0]
  const hasRes = entries?.some(e => e.finish_order != null && e.finish_order > 0) ?? false
  const winner = entries?.find(e => e.finish_order === 1)

  // ソート
  const sortedEntries = entries?.slice().sort((a, b) => {
    switch (sortKey) {
      case 'odds': return (a.odds_win ?? 999) - (b.odds_win ?? 999)
      case 'ai_ev': return (pm.get(b.horse_num)?.expected_value ?? -99) - (pm.get(a.horse_num)?.expected_value ?? -99)
      case 'popularity': return (a.popularity ?? 99) - (b.popularity ?? 99)
      case 'finish': return (a.finish_order ?? 99) - (b.finish_order ?? 99)
      default: return a.horse_num - b.horse_num
    }
  }) ?? []

  return (
    <div className="max-w-7xl mx-auto p-5 space-y-4">

      {/* ヘッダー */}
      <div>
        <div className="flex items-center gap-2">
          {race.grade != null && race.grade <= 6 && (
            <span className={`px-2 py-0.5 text-xs font-bold rounded ${
              race.grade === 1 ? 'bg-yellow-400 text-yellow-900' : race.grade === 2 ? 'bg-red-100 dark:bg-red-900/50 text-red-700 dark:text-red-300' :
              race.grade === 3 ? 'bg-green-100 dark:bg-green-900/50 text-green-700 dark:text-green-300' : 'bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300'
            }`}>{race.grade <= 3 ? `G${race.grade}` : race.grade === 4 ? '重賞' : race.grade === 5 ? 'OP' : 'L'}</span>
          )}
          <h2 className="text-xl font-bold text-gray-800 dark:text-gray-100">{race.race_name || `${v}${race.race_num}R`}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-sm text-gray-500 dark:text-gray-400">
          <span>{race.race_date}</span><span>{v}</span>
          {/* 発走時刻 */}
          {race.start_time && <span className="text-emerald-600 dark:text-emerald-400 font-medium">発走 {race.start_time}</span>}
          <span>{TRACK_L[race.track_type]}{race.distance}m{race.track_dir ? ` ${DIR_L[race.track_dir]}` : ''}</span>
          {race.track_cond && <span>{COND_L[race.track_cond]}</span>}
          {race.weather && <span>{WEATHER_L[race.weather]}</span>}
          {race.horse_count && <span>{race.horse_count}頭</span>}
          {race.is_handicap && <span className="text-orange-600 font-medium">ハンデ</span>}
          {race.is_female_only && <span className="text-pink-600 font-medium">牝馬限定</span>}
          {race.prize_1st && <span>1着賞金{fmtPrize(race.prize_1st)}</span>}
          <div className="flex items-center gap-2 ml-auto">
            <button onClick={() => window.print()} className="text-gray-400 hover:text-emerald-500 text-xs transition-colors print:hidden" title="印刷">🖨 印刷</button>
            <a href={getExportUrl(raceKey)} className="text-emerald-500 hover:text-emerald-700 text-xs" download>CSV↓</a>
          </div>
        </div>
      </div>

      {/* 概況 */}
      {entries && entries.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <div className="bg-white dark:bg-gray-800 rounded-xl p-3 border border-gray-200 dark:border-gray-700 shadow-sm">
            <div className="text-xs text-gray-400 mb-1">1番人気</div>
            {fav ? (<div className="flex items-center gap-2"><Waku n={fav.frame_num} /><b>{fav.horse_num}</b>
              <span className="text-sm text-gray-600 dark:text-gray-300 truncate">{fav.horse_name || '-'}</span>
              {fav.odds_win != null && <span className="text-amber-600 text-sm ml-auto">{fav.odds_win.toFixed(1)}倍</span>}
            </div>) : <span className="text-gray-400 dark:text-gray-500">-</span>}
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl p-3 border border-gray-200 dark:border-gray-700 shadow-sm">
            <div className="text-xs text-gray-400 mb-1">{hasRes ? '1着' : 'レース情報'}</div>
            {hasRes && winner ? (<>
              <div className="flex items-center gap-2"><span className="text-amber-600 font-bold">1着</span>
                <Waku n={winner.frame_num} /><b>{winner.horse_num}</b>
                <span className="text-sm text-gray-600 dark:text-gray-300 truncate">{winner.horse_name || '-'}</span>
              </div>
              <div className="text-xs text-gray-400 mt-0.5">{fmtTime(winner.finish_time)}{winner.last_3f ? ` / 上3F ${fmt3f(winner.last_3f)}` : ''}</div>
            </>) : <div className="text-sm text-gray-500">{race.horse_count}頭 {TRACK_L[race.track_type]}{race.distance}m</div>}
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-xl p-3 border border-gray-200 dark:border-gray-700 shadow-sm">
            <div className="text-xs text-gray-400 mb-1">
              {laps?.pace_analysis ? 'ペース' : '馬体重'}
            </div>
            {laps?.pace_analysis ? (
              <div className="text-sm">
                <span className={`font-bold ${PACE_COLOR[laps.pace_analysis.pace_label] ?? ''}`}>
                  {PACE_LABEL[laps.pace_analysis.pace_label] ?? laps.pace_analysis.pace_label}ペース
                </span>
                <span className="text-gray-400 text-xs ml-2">
                  前3F {fmtLap(laps.pace_analysis.first_3f)} / 後3F {fmtLap(laps.pace_analysis.last_3f)}
                </span>
              </div>
            ) : (() => {
              const ws = entries.filter(e => e.horse_weight).map(e => e.horse_weight!)
              if (!ws.length) return <span className="text-gray-400 dark:text-gray-500">-</span>
              const avg = Math.round(ws.reduce((a, b) => a + b, 0) / ws.length)
              return <div className="text-sm text-gray-700 dark:text-gray-200">平均 <b>{avg}</b>kg <span className="text-gray-400 text-xs">({Math.min(...ws)}〜{Math.max(...ws)})</span></div>
            })()}
          </div>
        </div>
      )}

      {/* AI予測 */}
      {hasAI ? (
        <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-700 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <h3 className="text-sm font-bold text-emerald-700 dark:text-emerald-400 tracking-wider">AI PREDICTION</h3>
          </div>
          <div className="grid grid-cols-5 gap-3 mb-4">
            {top5.map((p, i) => {
              const e = entries?.find(x => x.horse_num === p.horse_num)
              return (
                <div key={p.horse_num} className={`rounded-xl p-3 text-center ${i === 0 ? 'bg-white dark:bg-gray-800 border-2 border-emerald-400 shadow' : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700'}`}>
                  <div className={`text-lg font-bold mb-1 ${i === 0 ? 'text-emerald-600' : 'text-gray-400'}`}>{MARKS[i]}</div>
                  <div className="flex items-center justify-center gap-1 mb-1">{e && <Waku n={e.frame_num} />}<b>{p.horse_num}</b></div>
                  <div className="text-xs text-gray-500 truncate mb-1">{toFullWidth(p.horse_name) || '-'}</div>
                  <div className="text-sm font-bold">{(p.win_prob * 100).toFixed(1)}%</div>
                  <div className={`text-sm font-bold ${(p.expected_value ?? -999) >= 0 ? 'text-emerald-600' : 'text-gray-400'}`}>
                    EV{(p.expected_value ?? -999) >= 0 ? '+' : ''}{(p.expected_value ?? 0).toFixed(2)}
                  </div>
                  {p.ev_no_odds != null && (
                    <div className={`text-[10px] ${p.ev_no_odds >= 0 ? 'text-blue-500' : 'text-gray-400 dark:text-gray-500'}`}>
                      実力EV{p.ev_no_odds >= 0 ? '+' : ''}{p.ev_no_odds.toFixed(2)}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          {/* AI推奨買い目 */}
          {(() => {
            const evPlus = top5.filter(p => (p.expected_value ?? -999) >= 0)
            if (evPlus.length === 0) return null
            return (
              <div className="border-t border-emerald-200 dark:border-emerald-700 pt-3 text-sm space-y-1">
                <div><span className="text-gray-500">単勝推奨: </span><b>{evPlus[0].horse_num}番 {evPlus[0].horse_name || ''}</b>
                  <span className="text-emerald-600 ml-1">EV+{evPlus[0].expected_value.toFixed(2)}</span></div>
                {evPlus.length >= 2 && (
                  <div><span className="text-gray-500">馬連推奨: </span>
                    <b>{evPlus.slice(0, 2).sort((a, b) => a.horse_num - b.horse_num).map(p => `${p.horse_num}${p.horse_name ? p.horse_name : ''}`).join(' - ')}</b></div>
                )}
                {evPlus.length >= 3 && (
                  <div><span className="text-gray-500">三連複推奨: </span>
                    <b>{evPlus.slice(0, 3).sort((a, b) => a.horse_num - b.horse_num).map(p => `${p.horse_num}${p.horse_name ? p.horse_name : ''}`).join(' - ')}</b></div>
                )}
              </div>
            )
          })()}
        </div>
      ) : (
        <div className="bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-gray-300 dark:bg-gray-600" />
            <span className="text-sm text-gray-400">{pred?.message || 'AI予測: モデル未学習'}</span>
          </div>
        </div>
      )}

      {/* タブ */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
        {([['table', '出馬表'], ['ai_detail', 'AI詳細'], ['analysis', '分析'], ['odds_trend', 'オッズ推移'], ['betting', '買い目'], ['payouts', '払戻']] as const).map(([t, label]) => (
          <button key={t} onClick={() => setTab(t as typeof tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === t ? 'border-emerald-500 text-emerald-600' : 'border-transparent text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
            }`}>{label}</button>
        ))}
      </div>

      {/* ====== 出馬表タブ ====== */}
      {tab === 'table' && entries && entries.length > 0 && (
        <div>
          {/* ソートボタン */}
          <div className="flex gap-1 mb-2">
            {([['number', '馬番順'], ['odds', 'オッズ順'], ['popularity', '人気順'], ['finish', '着順'], ...(hasAI ? [['ai_ev', 'AI期待値順']] : [])] as [SortKey, string][]).map(([k, label]) => (
              <button key={k} onClick={() => setSortKey(k)}
                className={`px-2 py-1 text-xs rounded ${sortKey === k ? 'bg-emerald-500 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-600'}`}>{label}</button>
            ))}
          </div>

          {/* 出馬表: 横スクロール対応 + sticky固定列 */}
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm">
           <div className="overflow-x-auto">
            <table className="min-w-[1400px] w-full text-xs border-collapse">
              {/* 列幅を明示的に定義（colgroup） */}
              <colgroup>
                {hasAI && <col className="w-[28px]" />}
                <col className="w-[32px]" />  {/* 枠 */}
                <col className="w-[32px]" />  {/* 番 */}
                <col className="w-[120px]" /> {/* 馬名 */}
                <col className="w-[48px]" />  {/* 単勝 */}
                <col className="w-[32px]" />  {/* 人気 */}
                <col className="w-[36px]" />  {/* 性齢 */}
                <col className="w-[36px]" />  {/* 斤量 */}
                <col className="w-[72px]" />  {/* 騎手 */}
                <col className="w-[32px]" />  {/* 脚質 */}
                <col className="w-[110px]" /> {/* 前走1 */}
                <col className="w-[110px]" /> {/* 前走2 */}
                <col className="w-[110px]" /> {/* 前走3 */}
                <col className="w-[60px]" />  {/* 体重 */}
                {hasAI && <col className="w-[44px]" />}  {/* 勝率 */}
                {hasAI && <col className="w-[48px]" />}  {/* EV */}
                <col className="w-[24px]" />  {/* 展開ボタン */}
              </colgroup>
              <thead>
                <tr className="text-gray-400 text-[10px] border-b-2 border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700/40">
                  {hasAI && <th className="px-1 py-2 text-center sticky left-0 z-10 bg-gray-50 dark:bg-gray-700/40"></th>}
                  <th className="px-1 py-2 text-center sticky left-[28px] z-10 bg-gray-50 dark:bg-gray-700/40" style={hasAI ? {} : { left: 0 }}>枠</th>
                  <th className="px-1 py-2 text-center sticky z-10 bg-gray-50 dark:bg-gray-700/40" style={{ left: hasAI ? 60 : 32 }}>番</th>
                  <th className="px-1 py-2 text-left sticky z-10 bg-gray-50 dark:bg-gray-700/40" style={{ left: hasAI ? 92 : 64 }}>馬名</th>
                  <th className="px-1 py-2 text-right">単勝</th>
                  <th className="px-1 py-2 text-center">人気</th>
                  <th className="px-1 py-2 text-center">性齢</th>
                  <th className="px-1 py-2 text-center">斤量</th>
                  <th className="px-1 py-2 text-left">騎手</th>
                  <th className="px-1 py-2 text-center">脚質</th>
                  <th className="px-1 py-2 text-center border-l border-gray-200 dark:border-gray-600">前走(1)</th>
                  <th className="px-1 py-2 text-center">前走(2)</th>
                  <th className="px-1 py-2 text-center border-r border-gray-200 dark:border-gray-600">前走(3)</th>
                  <th className="px-1 py-2 text-center">体重</th>
                  {hasAI && <><th className="px-1 py-2 text-right text-emerald-600">勝率</th><th className="px-1 py-2 text-right text-emerald-600">EV</th></>}
                  <th className="px-1 py-2 text-center"></th>
                </tr>
              </thead>
              <tbody>
                {sortedEntries.map(e => {
                  const p = pm.get(e.horse_num)
                  const mi = top5.findIndex(x => x.horse_num === e.horse_num)
                  const isExpanded = expanded.has(e.horse_num)
                  // 過去走（最大3走）
                  const past3 = (e.past_races || []).slice(0, 3)
                  // 調教評価
                  const tr = trMap.get(e.horse_num)
                  // colSpan計算
                  const totalCols = 11 + (hasAI ? 3 : 0)
                  return (
                    <Fragment key={e.horse_num}>
                      {/* メイン行 */}
                      <tr
                        className={`cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors border-t border-gray-100 dark:border-gray-700 ${
                          e.abnormal_code != null && e.abnormal_code > 0
                            ? 'opacity-50'
                            : e.finish_order === 1 ? 'bg-amber-50/50 dark:bg-amber-900/20' : e.finish_order != null && e.finish_order <= 3 ? 'bg-gray-50/30 dark:bg-gray-700/20' : ''
                        }`}
                        onClick={() => toggle(e.horse_num)}
                      >
                        {/* AI印（sticky） */}
                        {hasAI && (
                          <td className="px-1 py-1.5 text-center sticky left-0 z-10 bg-inherit">
                            {mi >= 0 && <span className={mi === 0 ? 'font-bold text-emerald-600' : 'text-gray-400'}>{MARKS[mi]}</span>}
                          </td>
                        )}
                        {/* 枠番（sticky） */}
                        <td className="px-1 py-1.5 text-center sticky z-10 bg-inherit" style={{ left: hasAI ? 28 : 0 }}>
                          <Waku n={e.frame_num} />
                        </td>
                        {/* 馬番（sticky） */}
                        <td className="px-1 py-1.5 text-center font-bold sticky z-10 bg-inherit" style={{ left: hasAI ? 60 : 32 }}>
                          {e.horse_num}
                        </td>
                        {/* 馬名（sticky） */}
                        <td className="px-1 py-1.5 text-left sticky z-10 bg-inherit" style={{ left: hasAI ? 92 : 64 }}>
                          <div className="flex items-center gap-0.5 min-w-0">
                            <span className={`font-medium text-gray-700 dark:text-gray-200 truncate cursor-pointer hover:text-emerald-600 text-xs ${e.abnormal_code != null && e.abnormal_code > 0 ? 'line-through' : ''}`}
                              onClick={(ev) => { ev.stopPropagation(); e.horse_id && onNavigateHorse?.(e.horse_id, e.horse_name) }}>
                              {toFullWidth(e.horse_name) || '-'}
                            </span>
                            {e.abnormal_code != null && e.abnormal_code > 0 && ABNORMAL_L[e.abnormal_code] && (
                              <span className="text-[8px] px-0.5 bg-red-100 dark:bg-red-900/50 text-red-600 dark:text-red-400 rounded font-bold">{ABNORMAL_L[e.abnormal_code]}</span>
                            )}
                            {e.is_foreign_jockey && <span className="text-[8px] px-0.5 bg-yellow-100 dark:bg-yellow-900/40 text-yellow-700 dark:text-yellow-400 rounded">外</span>}
                            {e.jockey_change && <span className="text-[8px] px-0.5 bg-red-50 dark:bg-red-900/30 text-red-500 dark:text-red-400 rounded" title="乗り替わり">替</span>}
                          </div>
                        </td>
                        {/* 単勝（馬名の右） */}
                        <td className="px-1 py-1.5 text-right">
                          {e.odds_win != null ? <span className={e.odds_win <= 3 ? 'text-amber-600 font-bold' : 'text-gray-600 dark:text-gray-300'}>{e.odds_win.toFixed(1)}</span> : '-'}
                        </td>
                        {/* 人気 */}
                        <td className="px-1 py-1.5 text-center text-gray-400">{e.popularity ?? '-'}</td>
                        {/* 性齢 */}
                        <td className="px-1 py-1.5 text-center text-gray-500">{e.sex != null ? SEX_L[e.sex] ?? '' : ''}{e.age ?? ''}</td>
                        {/* 斤量 */}
                        <td className="px-1 py-1.5 text-center text-gray-500">{e.weight_carry ?? '-'}</td>
                        {/* 騎手 */}
                        <td className="px-1 py-1.5 text-left">
                          <span className="text-gray-600 dark:text-gray-300 truncate cursor-pointer hover:text-emerald-600"
                            onClick={(ev) => { ev.stopPropagation(); e.jockey_id && onNavigateJockey?.(e.jockey_id, e.jockey_name) }}>
                            {e.jockey_name || '-'}
                          </span>
                        </td>
                        {/* 脚質 */}
                        <td className="px-1 py-1.5 text-center"><StyleBadge style={e.running_style} /></td>
                        {/* 前走1 */}
                        <td className="px-1 py-1 border-l border-gray-100 dark:border-gray-700">
                          {past3[0] ? <PastRaceCompact race={past3[0]} /> : <span className="text-[10px] text-gray-400 dark:text-gray-500">-</span>}
                        </td>
                        {/* 前走2 */}
                        <td className="px-1 py-1">
                          {past3[1] ? <PastRaceCompact race={past3[1]} /> : <span className="text-[10px] text-gray-400 dark:text-gray-500">-</span>}
                        </td>
                        {/* 前走3 */}
                        <td className="px-1 py-1 border-r border-gray-100 dark:border-gray-700">
                          {past3[2] ? <PastRaceCompact race={past3[2]} /> : <span className="text-[10px] text-gray-400 dark:text-gray-500">-</span>}
                        </td>
                        {/* 体重 */}
                        <td className="px-1 py-1.5 text-center text-gray-500">
                          {e.horse_weight ?? '-'}
                          {e.weight_diff != null && e.weight_diff !== 0 && (
                            <span className={`text-[10px] ${e.weight_diff > 0 ? 'text-red-500' : 'text-blue-500'}`}>({e.weight_diff > 0 ? '+' : ''}{e.weight_diff})</span>
                          )}
                        </td>
                        {/* AI列 */}
                        {hasAI && <>
                          <td className="px-1 py-1.5 text-right text-gray-600 dark:text-gray-300 tabular-nums">{p ? `${(p.win_prob * 100).toFixed(1)}%` : '-'}</td>
                          <td className={`px-1 py-1.5 text-right tabular-nums font-medium ${p && (p.expected_value ?? -999) >= 0 ? 'text-emerald-600' : p && (p.expected_value ?? -999) >= -0.1 ? 'text-amber-600' : 'text-gray-400'}`}>
                            {p ? `${(p.expected_value ?? -999) >= 0 ? '+' : ''}${(p.expected_value ?? 0).toFixed(2)}` : '-'}
                          </td>
                        </>}
                        {/* 展開ボタン */}
                        <td className="px-1 py-1.5 text-center text-gray-400 dark:text-gray-500">
                          <svg className={`w-3 h-3 inline transition-transform ${isExpanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                        </td>
                      </tr>
                      {/* 展開部分 */}
                      {isExpanded && (
                        <tr>
                          <td colSpan={totalCols} className="p-0">
                            <div className="bg-gray-50 dark:bg-gray-900/50 border-t border-gray-100 dark:border-gray-700 px-4 py-3">
                              {/* 基本情報 */}
                              <div className="flex flex-wrap gap-4 mb-2 text-xs text-gray-500">
                                {e.interval_days != null && <span>中{Math.max(0, Math.floor(e.interval_days / 7))}週({e.interval_days}日)</span>}
                                <span className="cursor-pointer hover:text-emerald-600" onClick={() => e.trainer_id && onNavigateTrainer?.(e.trainer_id, e.trainer_name)}>
                                  厩舎: {e.trainer_name ?? '-'}
                                </span>
                                {e.father && <span>父: {e.father}</span>}
                                {e.mother_name && <span>母: {e.mother_name}</span>}
                                {e.mother_father && <span>母父: {e.mother_father}</span>}
                                {e.total_record && <span>通算: {e.total_record}</span>}
                                {e.total_earnings != null && e.total_earnings > 0 && <span>賞金: {fmtEarnings(e.total_earnings)}</span>}
                              </div>
                              {/* 調教AI評価 */}
                              {tr && (
                                <div className="flex items-center gap-3 mb-2 p-2 rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
                                  <div className="text-xs font-bold text-gray-500">調教AI評価</div>
                                  <span className={`inline-flex items-center justify-center w-7 h-7 rounded-lg text-sm font-bold ${TRAINING_RATING_COLOR[tr.rating] || TRAINING_RATING_COLOR.D}`}>
                                    {tr.rating}
                                  </span>
                                  <div className="text-xs text-gray-500">
                                    偏差値 <span className="font-bold text-gray-700 dark:text-gray-200">{tr.score}</span>
                                  </div>
                                  {tr.course && <div className="text-[10px] text-gray-400">{tr.course}</div>}
                                  {tr.last_3f != null && <div className="text-[10px] text-gray-400">3F: {(tr.last_3f / 10).toFixed(1)}</div>}
                                  {tr.last_1f != null && <div className="text-[10px] text-gray-400">1F: {(tr.last_1f / 10).toFixed(1)}</div>}
                                  {tr.training_date && <div className="text-[10px] text-gray-400">{tr.training_date.slice(5)}</div>}
                                </div>
                              )}
                              {/* 過去走テーブル */}
                              <div className="text-xs font-bold text-gray-500 mb-1">過去走</div>
                              <PastRacesTable races={e.past_races} />
                              <TrainingTable data={e.training} />
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
           </div>
          </div>
        </div>
      )}

      {/* ====== AI詳細タブ ====== */}
      {tab === 'ai_detail' && entries && entries.length > 0 && (() => {
        const sorted = entries.slice().sort((a, b) => (pm.get(b.horse_num)?.expected_value ?? -99) - (pm.get(a.horse_num)?.expected_value ?? -99))
        const evPlusH = sorted.filter(e => (pm.get(e.horse_num)?.expected_value ?? -1) > 0)
        const evNums = evPlusH.map(e => e.horse_num).sort((a, b) => a - b)
        const bestEV = evPlusH.length > 0 ? (pm.get(evPlusH[0].horse_num)?.expected_value ?? 0) : 0
        const confidence = evPlusH.length >= 3 && bestEV > 0.3 ? 'A' : evPlusH.length >= 2 && bestEV > 0.1 ? 'B' : evPlusH.length >= 1 ? 'C' : 'D'
        const confLabel: Record<string,string> = { A: '自信あり', B: 'やや自信あり', C: '微妙', D: '見送り推奨' }
        const confColor: Record<string,string> = { A: 'text-emerald-600 bg-emerald-100 dark:bg-emerald-900/40', B: 'text-blue-600 bg-blue-100 dark:bg-blue-900/40', C: 'text-yellow-700 dark:text-yellow-400 bg-yellow-100 dark:bg-yellow-900/40', D: 'text-red-600 bg-red-100 dark:bg-red-900/40' }
        return (
          <div className="space-y-4">
            <div className={`rounded-xl p-4 border-2 ${confidence === 'D' ? 'border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20' : confidence === 'A' ? 'border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/20' : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800'}`}>
              <div className="flex items-center gap-3 mb-2">
                <span className={`text-sm font-bold px-3 py-1 rounded-full ${confColor[confidence]}`}>{'信頼度 ' + confidence + ': ' + confLabel[confidence]}</span>
                <span className="text-xs text-gray-500">{'EV+: ' + evPlusH.length + '頭'}</span>
              </div>
              {confidence === 'D'
                ? <p className="text-sm text-red-700 dark:text-red-300">このレースにはEV+の馬がいません。<b>購入を見送る</b>のが最善です。</p>
                : <p className="text-sm text-gray-600 dark:text-gray-300">{'AIが期待値プラスと判断した馬が' + evPlusH.length + '頭います。以下の買い目を推奨します。'}</p>}
            </div>
            {/* AI最適購入プラン（全券種対応） */}
            {(pred as any)?.race_betting_plan?.tickets?.length > 0 && (() => {
              const plan = (pred as any).race_betting_plan
              const typeColors: Record<string, string> = {
                '単勝': 'border-emerald-500', '複勝': 'border-green-500',
                '馬連': 'border-blue-500', 'ワイド': 'border-cyan-500',
                '馬単': 'border-purple-500', '三連複': 'border-orange-500',
                '三連単': 'border-red-500',
              }
              const confBadge: Record<string, string> = {
                S: 'bg-red-600 text-white',
                A: 'bg-orange-500 text-white',
                B: 'bg-blue-500 text-white',
                C: 'bg-gray-500 text-white',
              }
              return (
                <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm overflow-hidden">
                  <div className="px-5 py-3 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between">
                    <h4 className="text-base font-bold text-gray-800 dark:text-gray-100">AI最適購入プラン</h4>
                    <div className="text-xs text-gray-500">{plan.strategy_summary}</div>
                  </div>
                  <div className="divide-y divide-gray-100 dark:divide-gray-700">
                    {plan.tickets.map((t: any, i: number) => (
                      <div key={i} className={`px-5 py-3 flex items-center gap-4 border-l-4 ${typeColors[t.bet_type] || 'border-gray-300'}`}>
                        <div className="w-16 shrink-0">
                          <span className="text-xs font-bold text-gray-700 dark:text-gray-200">{t.bet_type}</span>
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-bold text-gray-800 dark:text-gray-100">{t.combination}</div>
                          <div className="text-[11px] text-gray-500 mt-0.5">{t.reason}</div>
                        </div>
                        <div className="text-right shrink-0 w-20">
                          <div className="text-sm font-bold text-emerald-600 dark:text-emerald-400">{t.amount.toLocaleString()}円</div>
                          <div className="text-[10px] text-gray-400">推定{t.estimated_odds}倍</div>
                        </div>
                        <div className="text-right shrink-0 w-16">
                          <div className={`text-xs ${t.expected_value > 0 ? 'text-emerald-500' : 'text-gray-400'}`}>
                            EV {t.expected_value > 0 ? '+' : ''}{(t.expected_value * 100).toFixed(0)}%
                          </div>
                          <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${confBadge[t.confidence] || ''}`}>{t.confidence}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="px-5 py-3 bg-emerald-50 dark:bg-emerald-900/20 border-t border-emerald-200 dark:border-emerald-800 flex items-center justify-between">
                    <span className="text-xs text-emerald-700 dark:text-emerald-300 font-medium">
                      合計 {plan.tickets.length}点
                    </span>
                    <div className="flex gap-4 text-xs font-medium">
                      <span>投資: <b className="text-emerald-600 dark:text-emerald-400">{plan.total_invest.toLocaleString()}円</b></span>
                      <span>期待リターン: <b>{Math.round(plan.total_expected_return).toLocaleString()}円</b></span>
                      <span>期待ROI: <b className={plan.total_expected_return > plan.total_invest ? 'text-emerald-500' : 'text-red-400'}>
                        {plan.total_invest > 0 ? ((plan.total_expected_return / plan.total_invest) * 100).toFixed(0) : 0}%
                      </b></span>
                    </div>
                  </div>
                </div>
              )
            })()}
            {/* 全馬AI判定テーブル: 横スクロール対応 */}
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm">
              <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700">
                <h4 className="text-sm font-bold text-gray-700 dark:text-gray-200">全馬 AI判定</h4>
                <p className="text-[10px] text-gray-400">市場評価=オッズから逆算した勝率。AIがそれより高く評価=お買い得</p>
              </div>
              <div className="overflow-x-auto">
              <table className="min-w-[800px] w-full text-xs">
                <thead><tr className="text-gray-400 border-b border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-700/40">
                  <th className="px-2 py-2 text-center w-16">判定</th><th className="px-2 py-2 text-center w-8">番</th>
                  <th className="px-2 py-2 text-left">馬名</th><th className="px-2 py-2 text-right">オッズ</th>
                  <th className="px-2 py-2 text-right">AI勝率</th><th className="px-2 py-2 text-right">EV</th>
                  <th className="px-2 py-2 text-right">購入額</th>
                  <th className="px-3 py-2 text-left">AIの見解</th>
                </tr></thead>
                <tbody>
                  {sorted.map(e => {
                    const p = pm.get(e.horse_num)
                    if (!p) return null
                    const odds = p.odds_win ?? 0
                    const bp = (p as any).betting_plan
                    let vt: string, vc: string, vb: string
                    if ((p.expected_value ?? -999) >= 0.2) { vt = '◎ 強く買い'; vc = 'text-emerald-700 dark:text-emerald-400'; vb = 'bg-emerald-100 dark:bg-emerald-900/30' }
                    else if ((p.expected_value ?? -999) >= 0) { vt = '○ 買い'; vc = 'text-emerald-600 dark:text-emerald-400'; vb = 'bg-emerald-50 dark:bg-emerald-900/20' }
                    else if ((p.expected_value ?? -999) >= -0.15) { vt = '△ 様子見'; vc = 'text-yellow-700 dark:text-yellow-400'; vb = 'bg-yellow-50 dark:bg-yellow-900/20' }
                    else { vt = '✕ 不要'; vc = 'text-gray-400'; vb = '' }
                    const cm = p.ai_comment || ''
                    const confColor: Record<string, string> = { S: 'bg-red-600 text-white px-1 rounded', A: 'bg-orange-500 text-white px-1 rounded', B: 'bg-blue-500 text-white px-1 rounded', C: 'bg-gray-500 text-white px-1 rounded' }
                    return (
                      <tr key={e.horse_num} className={'border-t border-gray-50 dark:border-gray-700 align-top ' + vb}>
                        <td className="px-2 py-2 text-center"><span className={'text-xs font-bold ' + vc}>{vt}</span></td>
                        <td className="px-2 py-2 text-center font-bold">{e.horse_num}</td>
                        <td className="px-2 py-2 text-gray-700 dark:text-gray-200">{toFullWidth(e.horse_name) || '-'}</td>
                        <td className="px-2 py-2 text-right text-gray-600 dark:text-gray-300">{odds > 0 ? odds.toFixed(1) : '-'}</td>
                        <td className="px-2 py-2 text-right font-medium">{(p.win_prob * 100).toFixed(1) + '%'}</td>
                        <td className={`px-2 py-2 text-right font-medium ${(p.expected_value ?? -999) > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-400'}`}>
                          {(p.expected_value ?? -999) > 0 ? '+' : ''}{((p.expected_value ?? 0) * 100).toFixed(0)}%
                        </td>
                        <td className="px-2 py-2 text-right">
                          {bp ? (
                            <div>
                              <span className="font-bold text-emerald-600 dark:text-emerald-400">{bp.bet_amount.toLocaleString()}円</span>
                              <span className={`ml-1 text-[10px] font-bold ${confColor[bp.confidence] || ''}`}>{bp.confidence}</span>
                            </div>
                          ) : (
                            <span className="text-gray-300">-</span>
                          )}
                        </td>
                        <td className="px-3 py-2"><AiCommentCell text={cm} /></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              {/* 購入プランサマリー */}
              {pred && (pred as any).total_invest > 0 && (
                <div className="px-4 py-3 bg-emerald-50 dark:bg-emerald-900/20 border-t border-emerald-200 dark:border-emerald-800 flex items-center justify-between">
                  <div className="text-xs text-emerald-700 dark:text-emerald-300 font-medium">
                    購入プラン（資金10万円 / ケリー基準）
                  </div>
                  <div className="flex gap-4 text-xs">
                    <span>購入点数: <b>{pred.predictions.filter((p: any) => p.betting_plan).length}点</b></span>
                    <span>合計: <b className="text-emerald-600 dark:text-emerald-400">{(pred as any).total_invest?.toLocaleString()}円</b></span>
                    <span>期待リターン: <b>{Math.round((pred as any).total_expected_return || 0).toLocaleString()}円</b></span>
                  </div>
                </div>
              )}
              </div>
            </div>

            {/* ====== 予測ファクター別AI評価（B案レイアウト + グラデーション配色） ====== */}
            {entries && entries.length > 0 && race && (() => {
              const factorNames = ['血統', '調教', '直近', 'コース', '展開']
              const factorKeys = ['bloodline', 'training', 'recent', 'course', 'pace'] as const
              const heatStyle = (r: FactorRank) =>
                r === 'S' ? 'bg-emerald-600 text-white' :
                r === 'A' ? 'bg-emerald-400 text-white' :
                r === 'B' ? 'bg-emerald-200 text-emerald-800' :
                r === 'C' ? 'bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300' :
                r === 'D' ? 'bg-gray-100 dark:bg-gray-700 text-gray-400' :
                'bg-gray-50 dark:bg-gray-800 text-gray-300'
              const overallStyle = (r: FactorRank) =>
                r === 'S' ? 'bg-emerald-600 text-white' :
                r === 'A' ? 'bg-emerald-500 text-white' :
                r === 'B' ? 'bg-emerald-300 text-emerald-900' :
                r === 'C' ? 'bg-gray-300 dark:bg-gray-500 text-gray-700 dark:text-gray-200' :
                'bg-gray-200 dark:bg-gray-600 text-gray-500 dark:text-gray-300'

              return (
                <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden shadow-sm">
                  <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between">
                    <h4 className="text-sm font-bold text-gray-700 dark:text-gray-200">予測ファクター別 AI評価</h4>
                    <div className="flex items-center gap-1 text-[10px] text-gray-400">
                      <span className="px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700">D</span>
                      <span className="px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300">C</span>
                      <span className="px-1.5 py-0.5 rounded bg-emerald-200 text-emerald-800">B</span>
                      <span className="px-1.5 py-0.5 rounded bg-emerald-400 text-white">A</span>
                      <span className="px-1.5 py-0.5 rounded bg-emerald-600 text-white">S</span>
                    </div>
                  </div>
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-gray-400 border-b border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700/40">
                        <th className="px-3 py-2 text-center w-14">馬番</th>
                        <th className="px-3 py-2 text-left">馬名</th>
                        <th className="px-2 py-2 text-center w-10">総合</th>
                        {factorNames.map(n => (
                          <th key={n} className="px-1 py-2 text-center w-10">{n}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {entries.slice().sort((a, b) => a.horse_num - b.horse_num).map(e => {
                        const f = calcFactorEvaluation(e, trMap.get(e.horse_num), race, laps?.pace_analysis?.pace_label ?? null)
                        const overall = calcOverallRank(f)
                        const ranks = [f.bloodline, f.training, f.recent, f.course, f.pace]
                        const detailOpen = expanded.has(e.horse_num + 10000)
                        const toggleDetail = () => setExpanded(prev => {
                          const s = new Set(prev); detailOpen ? s.delete(e.horse_num + 10000) : s.add(e.horse_num + 10000); return s
                        })
                        return (
                          <Fragment key={e.horse_num}>
                            <tr className="border-t border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/20 cursor-pointer"
                              onClick={toggleDetail}>
                              <td className="px-3 py-2.5 text-center">
                                <Waku n={e.frame_num} /><span className="ml-1 font-bold">{e.horse_num}</span>
                              </td>
                              <td className="px-3 py-2.5 text-gray-800 dark:text-gray-100 font-medium">
                                {toFullWidth(e.horse_name) || '-'}
                                <span className="ml-1 text-gray-400 text-[10px]">{detailOpen ? '▲' : '▼'}</span>
                              </td>
                              <td className="px-2 py-2.5 text-center">
                                <span className={`inline-block w-8 py-0.5 rounded text-[11px] font-bold ${overallStyle(overall)}`}>{overall}</span>
                              </td>
                              {ranks.map((r, i) => (
                                <td key={i} className="px-1 py-2.5 text-center">
                                  <span className={`inline-block w-8 py-0.5 rounded text-[11px] font-bold ${heatStyle(r)}`}>{r}</span>
                                </td>
                              ))}
                            </tr>
                            {detailOpen && (
                              <tr className="bg-gray-50 dark:bg-gray-700/30">
                                <td colSpan={8} className="px-4 py-2">
                                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-1 text-[11px]">
                                    {factorKeys.map((fk, i) => {
                                      const label = ['血統', '調教', '直近成績', 'コース適性', '展開適性'][i]
                                      const r = ranks[i]
                                      return (
                                        <div key={fk} className="flex items-start gap-2 py-0.5">
                                          <span className={`shrink-0 w-5 text-center font-bold rounded ${heatStyle(r)}`}>{r}</span>
                                          <div>
                                            <span className="font-medium text-gray-700 dark:text-gray-200">{label}: </span>
                                            <span className="text-gray-500 dark:text-gray-400">{factorComment(fk, r, e)}</span>
                                          </div>
                                        </div>
                                      )
                                    })}
                                  </div>
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )
            })()}
          </div>
        )
      })()}

      {/* ====== 分析タブ ====== */}
      {tab === 'analysis' && entries && entries.length > 0 && (
        <div className="grid grid-cols-2 gap-4">
          {/* ラップタイム */}
          {laps && laps.laps.length > 0 && (
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm col-span-2">
              <h4 className="text-xs font-bold text-gray-500 mb-3">
                ラップタイム
                {laps.pace_analysis && (
                  <span className={`ml-2 ${PACE_COLOR[laps.pace_analysis.pace_label] ?? ''}`}>
                    {PACE_LABEL[laps.pace_analysis.pace_label]}ペース (PCI: {laps.pace_analysis.pci})
                  </span>
                )}
              </h4>
              <div className="flex items-end gap-1 h-24">
                {laps.laps.map((l, i) => {
                  const maxLap = Math.max(...laps.laps.map(x => x.time || 0))
                  const minLap = Math.min(...laps.laps.filter(x => x.time > 0).map(x => x.time))
                  const range = maxLap - minLap || 1
                  const h = 20 + ((l.time - minLap) / range) * 60
                  const isFirst3 = i < 3
                  const isLast3 = i >= laps.laps.length - 3
                  return (
                    <div key={i} className="flex-1 flex flex-col items-center gap-0.5">
                      <span className="text-[9px] text-gray-400 tabular-nums">{fmtLap(l.time)}</span>
                      <div className={`w-full rounded-t ${isFirst3 ? 'bg-red-200 dark:bg-red-500/50' : isLast3 ? 'bg-blue-200 dark:bg-blue-500/50' : 'bg-gray-200 dark:bg-gray-600'}`}
                        style={{ height: `${h}%` }} />
                      <span className="text-[8px] text-gray-400 dark:text-gray-500">{i + 1}</span>
                    </div>
                  )
                })}
              </div>
              <div className="flex justify-between text-[10px] text-gray-400 mt-1">
                <span className="text-red-400">← 前半</span>
                <span className="text-blue-400">後半 →</span>
              </div>
            </div>
          )}

          {/* オッズ分布 */}
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm">
            <h4 className="text-xs font-bold text-gray-500 mb-3">オッズ分布</h4>
            <div className="space-y-1.5">
              {byOdds.filter(e => e.odds_win != null).slice(0, 10).map(e => {
                const max = Math.max(...entries.filter(x => x.odds_win != null).map(x => x.odds_win!), 1)
                return (<div key={e.horse_num} className="flex items-center gap-2 text-xs">
                  <span className="w-4 text-right text-gray-500">{e.horse_num}</span>
                  <div className="flex-1 bg-gray-100 dark:bg-gray-700 rounded-full h-3.5"><div className="h-full rounded-full bg-emerald-200 dark:bg-emerald-600" style={{ width: `${Math.min((e.odds_win! / max) * 100, 100)}%` }} /></div>
                  <span className="w-12 text-right text-gray-600 dark:text-gray-300">{e.odds_win!.toFixed(1)}</span>
                </div>)
              })}
            </div>
          </div>

          {/* 脚質分布 */}
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm">
            <h4 className="text-xs font-bold text-gray-500 mb-3">脚質分布</h4>
            {(() => {
              const styles = entries.filter(e => e.running_style).reduce((acc, e) => { acc[e.running_style!] = (acc[e.running_style!] || 0) + 1; return acc }, {} as Record<string, number>)
              return (
                <div className="flex gap-3">
                  {['逃', '先', '差', '追'].map(s => (
                    <div key={s} className="flex-1 text-center">
                      <div className="text-2xl font-bold text-gray-700 dark:text-gray-100">{styles[s] || 0}</div>
                      <StyleBadge style={s} />
                    </div>
                  ))}
                </div>
              )
            })()}
          </div>

          {/* 枠番別着順 */}
          {hasRes && (
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm">
              <h4 className="text-xs font-bold text-gray-500 mb-3">枠番別着順</h4>
              <div className="flex gap-1">
                {[1,2,3,4,5,6,7,8].map(f => {
                  const es = entries.filter(e => e.frame_num === f && e.finish_order != null)
                  const avg = es.length > 0 ? es.reduce((a, e) => a + (e.finish_order ?? 0), 0) / es.length : null
                  return (
                    <div key={f} className="flex-1 text-center">
                      <Waku n={f} />
                      <div className="text-xs text-gray-600 dark:text-gray-300 mt-1">{avg != null ? avg.toFixed(1) : '-'}</div>
                      <div className="text-[10px] text-gray-400">{es.length}頭</div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* 上がり3Fランキング */}
          {hasRes && (
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-4 shadow-sm">
              <h4 className="text-xs font-bold text-gray-500 mb-3">上がり3Fランキング</h4>
              <div className="flex flex-wrap gap-2">
                {entries.filter(e => e.last_3f && e.last_3f > 0).sort((a, b) => (a.last_3f ?? 999) - (b.last_3f ?? 999)).slice(0, 5).map((e, i) => {
                  const avg = entries.filter(x => x.last_3f && x.last_3f > 0).reduce((a, x) => a + x.last_3f!, 0) / entries.filter(x => x.last_3f && x.last_3f > 0).length
                  const diff = e.last_3f! - avg
                  return (
                    <div key={e.horse_num} className={`px-3 py-2 rounded-xl text-center ${i === 0 ? 'bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-700' : 'bg-gray-50 dark:bg-gray-700'}`}>
                      <div className="text-xs text-gray-400">{i + 1}位</div>
                      <div className="font-bold text-gray-700 dark:text-gray-200">{e.horse_num}番</div>
                      <div className={i === 0 ? 'text-emerald-600 font-bold' : 'text-gray-600 dark:text-gray-300'}>{fmt3f(e.last_3f)}</div>
                      <div className={`text-[10px] ${diff < 0 ? 'text-emerald-500' : 'text-red-400'}`}>
                        {diff < 0 ? '' : '+'}{(diff / 10).toFixed(1)}
                      </div>
                      <div className="text-xs text-gray-400">{e.finish_order}着</div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ====== オッズ推移タブ ====== */}
      {tab === 'odds_trend' && (
        <OddsChart raceKey={raceKey} />
      )}

      {/* ====== 払戻タブ ====== */}
      {tab === 'payouts' && (
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-xl p-4 shadow-sm">
          <h4 className="text-xs font-bold text-gray-500 dark:text-gray-400 mb-3">払戻結果</h4>
          {payoutData && Object.keys(payoutData.payouts).length > 0 ? (
            <div className="grid grid-cols-2 gap-4">
              {Object.entries(payoutData.payouts).map(([betType, items]) => (
                <div key={betType}>
                  <div className="text-sm font-bold text-gray-700 dark:text-gray-100 mb-1">{betType}</div>
                  <div className="overflow-x-auto">
                  <table className="min-w-[250px] w-full text-xs">
                    <thead><tr className="text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-600">
                      <th className="py-1.5 text-left">組合せ</th>
                      <th className="py-1.5 text-right">払戻</th>
                      <th className="py-1.5 text-right">人気</th>
                    </tr></thead>
                    <tbody>{items.map((item, i) => (
                      <tr key={i} className="border-t border-gray-100 dark:border-gray-700">
                        <td className="py-1.5 text-gray-800 dark:text-gray-100 font-mono">{item.combination}</td>
                        <td className="py-1.5 text-right text-emerald-600 dark:text-emerald-400 font-bold">¥{item.payout.toLocaleString()}</td>
                        <td className="py-1.5 text-right text-gray-500 dark:text-gray-400">{item.popularity != null ? `${item.popularity}番人気` : '-'}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-gray-400 text-sm">払戻データなし</div>
          )}
        </div>
      )}

      {/* ====== 買い目タブ ====== */}
      {tab === 'betting' && entries && entries.length > 0 && (
        <BettingPanel
          entries={entries.map(e => ({ horse_num: e.horse_num, horse_name: e.horse_name, odds_win: e.odds_win }))}
          raceKey={raceKey}
        />
      )}

      {entries?.length === 0 && <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl p-8 text-center text-gray-400">出走馬データなし</div>}
    </div>
  )
}

/** AI見解セル — 長文を展開/折りたたみできるUI */
function AiCommentCell({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  if (!text) return <span className="text-gray-400 text-[11px]">-</span>

  const lines = text.split('\n').filter(Boolean)
  const isLong = lines.length > 2
  const display = expanded ? lines : lines.slice(0, 2)

  return (
    <div className="max-w-[320px]">
      <div className="text-[11px] leading-relaxed text-gray-600 dark:text-gray-300 whitespace-pre-line">
        {display.map((line, i) => {
          const isHeader = line.startsWith('【')
          return (
            <div key={i} className={isHeader ? 'font-medium text-gray-700 dark:text-gray-200' : ''}>
              {line}
            </div>
          )
        })}
      </div>
      {isLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-[10px] text-emerald-500 hover:text-emerald-400 mt-0.5"
        >
          {expanded ? '折りたたむ' : `他${lines.length - 2}項目を表示...`}
        </button>
      )}
    </div>
  )
}
