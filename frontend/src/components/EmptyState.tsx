/**
 * 空状態コンポーネント — データなし時の説明表示
 * 検索結果0件、一覧データなし、フィルタ不一致時などに使用
 */

interface Props {
  /** アイコン（絵文字やSVG） */
  icon?: string
  /** タイトル */
  title: string
  /** 説明文 */
  description?: string
  /** アクションボタンテキスト */
  actionLabel?: string
  /** アクションボタンのコールバック */
  onAction?: () => void
}

export default function EmptyState({ icon, title, description, actionLabel, onAction }: Props) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4">
      {/* アイコン */}
      {icon && (
        <div className="text-4xl mb-3 opacity-40">{icon}</div>
      )}

      {/* タイトル */}
      <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">{title}</h3>

      {/* 説明文 */}
      {description && (
        <p className="text-xs text-gray-400 dark:text-gray-500 text-center max-w-sm">{description}</p>
      )}

      {/* アクションボタン */}
      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className="mt-4 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg transition-colors"
        >
          {actionLabel}
        </button>
      )}
    </div>
  )
}
