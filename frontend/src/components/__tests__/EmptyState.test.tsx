/**
 * EmptyState コンポーネントのテスト
 * データなし時の空状態表示が正しくレンダリングされるか確認
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import EmptyState from '../EmptyState'

describe('EmptyState', () => {
  it('タイトルが正しく表示される', () => {
    render(<EmptyState title="データがありません" />)
    expect(screen.getByText('データがありません')).toBeInTheDocument()
  })

  it('説明文が表示される', () => {
    render(<EmptyState title="テスト" description="詳細な説明文" />)
    expect(screen.getByText('詳細な説明文')).toBeInTheDocument()
  })

  it('アイコンが指定された場合に表示される', () => {
    render(<EmptyState title="テスト" icon="📊" />)
    expect(screen.getByText('📊')).toBeInTheDocument()
  })

  it('アクションボタンがクリックできる', () => {
    let clicked = false
    render(<EmptyState title="テスト" actionLabel="再読み込み" onAction={() => { clicked = true }} />)
    screen.getByText('再読み込み').click()
    expect(clicked).toBe(true)
  })
})
