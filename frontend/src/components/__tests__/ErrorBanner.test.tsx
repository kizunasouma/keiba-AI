/**
 * ErrorBanner コンポーネントのテスト
 * エラー表示とリトライボタンの動作確認
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ErrorBanner from '../ErrorBanner'

describe('ErrorBanner', () => {
  it('エラーメッセージが表示される', () => {
    render(<ErrorBanner message="接続エラー" />)
    expect(screen.getByText('接続エラー')).toBeInTheDocument()
  })

  it('リトライボタンがクリックできる', () => {
    const onRetry = vi.fn()
    render(<ErrorBanner message="エラー" onRetry={onRetry} />)
    const button = screen.getByRole('button')
    fireEvent.click(button)
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})
