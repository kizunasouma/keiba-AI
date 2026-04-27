/**
 * FastAPI クライアント — API直接呼出し
 * リトライ付き: ネットワークエラー・5xx時に最大2回リトライ（指数バックオフ）
 */
import axios, { AxiosError } from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

/** リトライ設定 */
const MAX_RETRIES = 2
const RETRY_DELAY_MS = 500

export const apiClient = axios.create({ baseURL: BASE_URL, timeout: 15000 })

/** リトライ可能なエラーかどうかを判定 */
function isRetryable(error: unknown): boolean {
  if (error instanceof AxiosError) {
    if (!error.response) return true
    if (error.response.status >= 500) return true
  }
  return false
}

/** 指数バックオフで待機 */
function delay(attempt: number): Promise<void> {
  const ms = RETRY_DELAY_MS * Math.pow(2, attempt)
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function callApi<T>(apiFn: () => Promise<T>): Promise<T> {
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      return await apiFn()
    } catch (err) {
      if (attempt >= MAX_RETRIES || !isRetryable(err)) {
        throw err
      }
      console.warn(`[client] リトライ ${attempt + 1}/${MAX_RETRIES}...`)
      await delay(attempt)
    }
  }
  throw new Error('API呼出し失敗')
}

// --- レース ---
export async function fetchRaces(params: {
  race_date?: string; date_from?: string; date_to?: string
  venue_code?: string; grade?: number; track_type?: number
  distance_min?: number; distance_max?: number; track_cond?: number
  is_handicap?: boolean; is_female_only?: boolean; race_name?: string
  limit?: number; offset?: number
}) {
  return callApi(async () => (await apiClient.get('/races', { params })).data)
}

export async function fetchRace(raceKey: string) {
  return callApi(async () => (await apiClient.get(`/races/${raceKey}`)).data)
}

export async function fetchEntries(raceKey: string) {
  return callApi(async () => (await apiClient.get(`/races/${raceKey}/entries`)).data)
}

export async function fetchLaps(raceKey: string) {
  return callApi(async () => (await apiClient.get(`/races/${raceKey}/laps`)).data)
}

export async function fetchPayouts(raceKey: string) {
  return callApi(async () => (await apiClient.get(`/races/${raceKey}/payouts`)).data)
}

// --- オッズ推移 ---
export async function fetchOddsTimeline(raceKey: string) {
  return callApi(async () => (await apiClient.get(`/races/${raceKey}/odds`)).data)
}

export async function fetchPredictions(raceKey: string) {
  return callApi(async () => (await apiClient.get(`/races/${raceKey}/predict`)).data)
}

export async function fetchRaceOdds(raceKey: string) {
  return callApi(async () => (await apiClient.get(`/races/${raceKey}/odds`)).data)
}

// --- 馬カルテ ---
export async function fetchHorse(horseId: number) {
  return callApi(async () => (await apiClient.get(`/horses/${horseId}`)).data)
}

export async function fetchHorseResults(horseId: number) {
  return callApi(async () => (await apiClient.get(`/horses/${horseId}/results`)).data)
}

export async function fetchHorseStats(horseId: number) {
  return callApi(async () => (await apiClient.get(`/horses/${horseId}/stats`)).data)
}

export async function fetchHorseWeightHistory(horseId: number) {
  return callApi(async () => (await apiClient.get(`/horses/${horseId}/weight_history`)).data)
}

// --- 騎手 ---
export async function fetchJockey(jockeyId: number) {
  return callApi(async () => (await apiClient.get(`/jockeys/${jockeyId}`)).data)
}

export async function fetchJockeyStats(jockeyId: number) {
  return callApi(async () => (await apiClient.get(`/jockeys/${jockeyId}/stats`)).data)
}

export async function fetchJockeyRecent(jockeyId: number, days = 90) {
  return callApi(async () => (await apiClient.get(`/jockeys/${jockeyId}/recent`, { params: { days } })).data)
}

export async function fetchJockeyCombo(jockeyId: number) {
  return callApi(async () => (await apiClient.get(`/jockeys/${jockeyId}/combo`)).data)
}

// --- 調教師 ---
export async function fetchTrainer(trainerId: number) {
  return callApi(async () => (await apiClient.get(`/trainers/${trainerId}`)).data)
}

export async function fetchTrainerStats(trainerId: number) {
  return callApi(async () => (await apiClient.get(`/trainers/${trainerId}/stats`)).data)
}

export async function fetchTrainerRecent(trainerId: number, days = 90) {
  return callApi(async () => (await apiClient.get(`/trainers/${trainerId}/recent`, { params: { days } })).data)
}

// --- 統計 ---
export async function fetchSireStats(params?: Record<string, unknown>) {
  return callApi(async () => (await apiClient.get('/stats/sire', { params })).data)
}
export async function fetchBmsStats(params?: Record<string, unknown>) {
  return callApi(async () => (await apiClient.get('/stats/bms', { params })).data)
}
export async function fetchFrameStats(params?: Record<string, unknown>) {
  return callApi(async () => (await apiClient.get('/stats/frame', { params })).data)
}
export async function fetchPopularityStats() {
  return callApi(async () => (await apiClient.get('/stats/popularity')).data)
}
export async function fetchMiningStats(params: Record<string, unknown>) {
  return callApi(async () => (await apiClient.get('/stats/mining', { params })).data)
}

// --- 買い目計算 ---
export async function calcFormation(data: { bet_type: string; first: number[]; second: number[]; third?: number[]; amount?: number }) {
  return callApi(async () => (await apiClient.post('/betting/formation', data)).data)
}
export async function calcBox(data: { bet_type: string; horses: number[]; amount?: number }) {
  return callApi(async () => (await apiClient.post('/betting/box', data)).data)
}
export async function calcNagashi(data: { bet_type: string; axis: number[]; partners: number[]; amount?: number }) {
  return callApi(async () => (await apiClient.post('/betting/nagashi', data)).data)
}
export async function calcKelly(win_prob: number, odds: number) {
  return callApi(async () => (await apiClient.get('/betting/kelly', { params: { win_prob, odds } })).data)
}

// --- 統合検索 ---
export async function searchHorses(q: string, limit = 20) {
  return callApi(async () => (await apiClient.get('/horses/search', { params: { q, limit } })).data)
}
export async function searchJockeys(q: string, limit = 20) {
  return callApi(async () => (await apiClient.get('/jockeys/search', { params: { q, limit } })).data)
}
export async function searchTrainers(q: string, limit = 20) {
  return callApi(async () => (await apiClient.get('/trainers/search', { params: { q, limit } })).data)
}
export async function searchRaces(q: string, limit = 20) {
  return callApi(async () => (await apiClient.get('/races', { params: { race_name: q, limit } })).data)
}

// --- 回収率バックテスト ---
export async function fetchBacktestSummary(days = 30, ev_threshold = 0, bet_mode = 'kelly', date_from?: string, date_to?: string) {
  const params: any = { days, ev_threshold, bet_mode }
  if (date_from) params.date_from = date_from
  if (date_to) params.date_to = date_to
  return callApi(async () => (await apiClient.get('/backtest/summary', { params })).data)
}

// --- お気に入り ---
export async function fetchFavorites() {
  return callApi(async () => (await apiClient.get('/favorites')).data)
}
export async function addFavorite(data: { horse_id: number; horse_name?: string; note?: string }) {
  return callApi(async () => (await apiClient.post('/favorites', data)).data)
}
export async function removeFavorite(horseId: number) {
  return callApi(async () => (await apiClient.delete(`/favorites/${horseId}`)).data)
}
export async function fetchUpcomingFavorites() {
  return callApi(async () => (await apiClient.get('/favorites/upcoming')).data)
}

// --- 調教評価 ---
export async function fetchTrainingRating(raceKey: string) {
  return callApi(async () => (await apiClient.get('/stats/training_rating', { params: { race_key: raceKey } })).data)
}

// --- エクスポート ---
export function getExportUrl(raceKey: string) { return `${BASE_URL}/export/race/${raceKey}` }

// --- バックテスト分析（v5追加） ---
export async function fetchBacktestBreakdown(days: number = 90) {
  return callApi(async () => (await apiClient.get('/backtest/breakdown', { params: { days } })).data)
}

// --- 予測精度モニタリング（v5追加） ---
export async function fetchAccuracyMonitor(days: number = 30) {
  return callApi(async () => (await apiClient.get('/backtest/accuracy', { params: { days } })).data)
}

// --- タスク実行 ---
export async function triggerDataSync() {
  return callApi(async () => (await apiClient.post('/tasks/sync')).data)
}
export async function fetchSyncStatus() {
  return callApi(async () => (await apiClient.get('/tasks/sync/status')).data)
}
export async function triggerAIPredictions(scope: 'week' | 'month' | string = 'month') {
  return callApi(async () => (await apiClient.post('/tasks/predict', null, { params: { scope } })).data)
}
export async function fetchPredictStatus() {
  return callApi(async () => (await apiClient.get('/tasks/predict/status')).data)
}
export async function fetchDbSummary() {
  return callApi(async () => (await apiClient.get('/tasks/db/summary')).data)
}

// --- ヘルスチェック ---
export async function fetchHealth() {
  return callApi(async () => (await apiClient.get('/health/db')).data)
}
