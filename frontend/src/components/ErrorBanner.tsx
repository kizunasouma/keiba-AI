/**
 * エラーバナー — API失敗時・データ取得エラー時に表示する共通コンポーネント
 * リトライボタン付きで、ユーザーが再取得を試行できる
 */

interface Props {
  /** エラーメッセージ（省略時はデフォルトメッセージ） */
  message?: string
  /** リトライコールバック（省略時はリトライボタン非表示） */
  onRetry?: () => void
  /** コンパクト表示（インライン用） */
  compact?: boolean
}

export default function ErrorBanner({ message, onRetry, compact = false }: Props) {
  const defaultMsg = 'データの取得に失敗しました。サーバーが起動しているか確認してください。'

  if (compact) {
    // インライン用のコンパクト表示
    return (
      <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-400">
        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <span>{message || defaultMsg}</span>
        {onRetry && (
          <button
            onClick={onRetry}
            className="text-emerald-600 dark:text-emerald-400 hover:underline font-medium ml-1"
          >
            再試行
          </button>
        )}
      </div>
    )
  }

  // フルサイズ表示
  return (
    <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4">
      <div className="flex items-start gap-3">
        {/* アイコン */}
        <div className="shrink-0 w-8 h-8 rounded-full bg-red-100 dark:bg-red-900/40 flex items-center justify-center">
          <svg className="w-5 h-5 text-red-500 dark:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>

        {/* メッセージ */}
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-bold text-red-700 dark:text-red-400 mb-1">エラーが発生しました</h4>
          <p className="text-sm text-red-600 dark:text-red-300">{message || defaultMsg}</p>
        </div>

        {/* リトライボタン */}
        {onRetry && (
          <button
            onClick={onRetry}
            className="shrink-0 px-3 py-1.5 bg-red-100 dark:bg-red-900/40 hover:bg-red-200 dark:hover:bg-red-800/50 text-red-700 dark:text-red-300 text-xs font-medium rounded-lg transition-colors"
          >
            再試行
          </button>
        )}
      </div>
    </div>
  )
}
