/**
 * レース詳細のデータフェッチを集約するカスタムフック
 * タブ状態に応じた遅延ロードを制御する
 */
import { useQuery } from '@tanstack/react-query'
import { fetchRace, fetchEntries, fetchPredictions, fetchLaps, fetchPayouts, fetchTrainingRating } from '../api/client'
import type { RaceInfo, Entry, PredictionResponse, LapData, PayoutData, TrainingRatingResponse } from '../types'

/** レース詳細のタブ種別 */
export type RaceTab = 'table' | 'ai_detail' | 'analysis' | 'odds_trend' | 'betting' | 'payouts'

/** useRaceDataの戻り値 */
export interface RaceDataResult {
  race: RaceInfo | undefined
  entries: Entry[] | undefined
  pred: PredictionResponse | undefined
  laps: LapData | undefined
  payoutData: PayoutData | undefined
  trainingRatingData: TrainingRatingResponse | undefined
  isLoading: boolean
  isError: boolean
  refetchRace: () => void
}

/**
 * レース詳細画面のデータをまとめてフェッチするフック
 * タブ状態に応じて必要なデータだけを遅延ロードする
 */
export function useRaceData(raceKey: string, tab: RaceTab): RaceDataResult {
  // 基本データ（常にロード）
  const { data: race, isLoading: rl, isError: rErr, refetch: refetchRace } = useQuery<RaceInfo>({
    queryKey: ['race', raceKey],
    queryFn: () => fetchRace(raceKey),
    retry: 1,
  })
  const { data: entries, isLoading: el } = useQuery<Entry[]>({
    queryKey: ['entries', raceKey],
    queryFn: () => fetchEntries(raceKey),
    retry: 1,
  })

  // 遅延ロード（タブ切替時に取得）
  const { data: pred } = useQuery<PredictionResponse>({
    queryKey: ['predict', raceKey],
    queryFn: () => fetchPredictions(raceKey),
    retry: false,
    enabled: tab === 'ai_detail' || tab === 'table',
    staleTime: 5 * 60 * 1000,
  })
  const { data: laps } = useQuery<LapData>({
    queryKey: ['laps', raceKey],
    queryFn: () => fetchLaps(raceKey),
    retry: false,
    enabled: tab === 'analysis',
  })
  const { data: payoutData } = useQuery<PayoutData>({
    queryKey: ['payouts', raceKey],
    queryFn: () => fetchPayouts(raceKey),
    retry: false,
    enabled: tab === 'payouts',
  })
  // 調教AI評価（出馬表タブで使用）
  const { data: trainingRatingData } = useQuery<TrainingRatingResponse>({
    queryKey: ['trainingRating', raceKey],
    queryFn: () => fetchTrainingRating(raceKey),
    retry: false,
    enabled: tab === 'table',
  })

  return {
    race, entries, pred, laps, payoutData, trainingRatingData,
    isLoading: rl || el,
    isError: rErr,
    refetchRace,
  }
}
