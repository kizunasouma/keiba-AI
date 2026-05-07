/**
 * 共通型定義
 * APIレスポンス型を各コンポーネントで共有する
 */

// --- レース ---
export interface RaceInfo {
  race_key: string; race_name: string | null; race_date: string; venue_code: string
  race_num: number; grade: number | null; distance: number; track_type: number
  track_dir: number | null; weather: number | null; track_cond: number | null
  horse_count: number | null; is_handicap: boolean; is_female_only: boolean
  prize_1st: number | null
  start_time?: string | null
}

// --- AI予測 ---
export interface PredictionItem {
  entry_id: number; horse_num: number; horse_name: string | null
  jockey_name: string | null; odds_win: number | null
  win_prob: number; expected_value: number
  win_prob_no_odds?: number | null; ev_no_odds?: number | null
  recommendation: string
  ai_comment?: string | null
  betting_plan?: BettingPlan | null
}

export interface BettingPlan {
  bet_amount: number; kelly_fraction: number; edge: number; confidence: number
}

export interface PredictionResponse {
  race_key: string; model_available: boolean; model_type?: string
  predictions: PredictionItem[]; message?: string | null
  race_betting_plan?: RaceBettingPlan | null
  total_invest?: number; total_expected_return?: number
}

export interface RaceBettingPlan {
  tickets: BettingTicket[]
  total_invest: number; total_expected_return: number
}

export interface BettingTicket {
  bet_type: string; horses: number[]; amount: number
  expected_value: number; confidence: number
}

// --- 出走馬 ---
export interface Entry {
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

export interface PastRace {
  race_date: string; race_name: string | null; venue: string; distance: number
  track: string; cond: string; horse_count: number | null; grade: number | null
  horse_num: number; popularity: number | null; finish_order: number | null
  finish_time: number | null; last_3f: number | null; weight_carry: number | null
  horse_weight: number | null; weight_diff: number | null; odds_win: number | null
  margin: string | null; corner_text: string | null; speed_index: number | null
  jockey_name: string | null; running_style: string | null
}

export interface TrainingData {
  training_date: string; weeks_before: number | null; course_type: string | null
  distance: number | null; lap_time: number | null; last_3f: number | null
  last_1f: number | null; rank: string | null; note: string | null
}

// --- ラップ・払戻 ---
export interface LapData {
  race_key: string; distance: number
  laps: { order: number; time: number }[]
  pace_analysis: { first_3f: number; last_3f: number; pci: number; pace_label: string } | null
}

export interface PayoutData {
  race_key: string; payouts: Record<string, { combination: string; payout: number; popularity: number | null }[]>
}

// --- 調教評価 ---
export interface TrainingRatingItem {
  horse_num: number; rating: string; score: number
  course?: string; training_date?: string; last_3f?: number; last_1f?: number
}

export interface TrainingRatingResponse {
  race_key: string; ratings: TrainingRatingItem[]
}

// --- バックテスト ---
export interface BacktestSummary {
  total_races: number; total_bets: number; total_invest: number
  total_return: number; total_hits: number; roi: number
  hit_rate: number; days: number
  bet_history?: BetHistoryItem[]
  daily_results?: DailyResult[]
}

export interface BetHistoryItem {
  race_key: string; race_date: string; race_label: string; race_name: string
  bet_type: string; combination: string; horse_num: number; odds: number
  popularity: number; bet_amount: number; finish_order: number
  payout: number; profit: number; hit: boolean
}

export interface DailyResult {
  date: string; bets: number; invest: number; ret: number; hits: number
  roi: number; cum_invest: number; cum_return: number; cum_roi: number
}

// --- 統計 ---
export interface StatColumn {
  key: string; label: string; fmt?: (v: unknown) => string
}

// --- 会場コード ---
export const VENUE: Record<string, string> = {
  '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
  '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉',
}
