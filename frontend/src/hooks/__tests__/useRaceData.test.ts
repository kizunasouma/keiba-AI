/**
 * useRaceData カスタムフックのテスト
 * 型定義とエクスポートが正しいことを確認
 */
import { describe, it, expect } from 'vitest'
import type { RaceTab, RaceDataResult } from '../useRaceData'

describe('useRaceData 型定義', () => {
  it('RaceTabの型が正しく定義されている', () => {
    // 型チェック（コンパイル時に検証）
    const tabs: RaceTab[] = ['table', 'ai_detail', 'analysis', 'odds_trend', 'betting', 'payouts']
    expect(tabs).toHaveLength(6)
  })

  it('RaceDataResultの型が正しく定義されている', () => {
    // RaceDataResultのキーが存在することを確認
    const keys: (keyof RaceDataResult)[] = [
      'race', 'entries', 'pred', 'laps', 'payoutData',
      'trainingRatingData', 'isLoading', 'isError', 'refetchRace',
    ]
    expect(keys).toHaveLength(9)
  })
})
