/**
 * Chrome風タブバー — タブの表示・切替・閉じるボタン
 */
import type { Tab } from '../hooks/useTabManager'

interface Props {
  tabs: Tab[]
  activeTabId: string | null
  onActivate: (id: string) => void
  onClose: (id: string) => void
}

/** タブ種別ごとのアイコン */
const TAB_ICON: Record<string, string> = {
  race: '🏇',
  horse: '🐴',
  jockey: '🧑',
  trainer: '👔',
}

export default function TabBar({ tabs, activeTabId, onActivate, onClose }: Props) {
  if (tabs.length === 0) return null

  return (
    <div className="flex items-end bg-gray-200 dark:bg-gray-800 px-1 pt-1 overflow-x-auto border-b border-gray-300 dark:border-gray-700"
      style={{ scrollbarWidth: 'none' }}>
      {tabs.map(tab => {
        const isActive = tab.id === activeTabId
        return (
          <div
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            // 中クリックで閉じる
            onMouseDown={(e) => { if (e.button === 1) { e.preventDefault(); onClose(tab.id) } }}
            onClick={() => onActivate(tab.id)}
            className={`group relative flex items-center gap-1.5 max-w-[200px] min-w-[100px] px-3 py-1.5 cursor-pointer select-none
              rounded-t-lg text-xs transition-colors shrink-0
              ${isActive
                ? 'bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-100 shadow-sm z-10 -mb-px border border-gray-300 dark:border-gray-700 border-b-white dark:border-b-gray-900'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-600 border border-transparent mt-0.5'
              }`}
          >
            {/* アイコン */}
            <span className="text-[11px] shrink-0">{TAB_ICON[tab.descriptor.type] ?? '📄'}</span>

            {/* タイトル */}
            <span className="truncate flex-1 font-medium">{tab.title}</span>

            {/* 閉じるボタン */}
            <button
              onClick={(e) => { e.stopPropagation(); onClose(tab.id) }}
              className={`shrink-0 w-4 h-4 flex items-center justify-center rounded
                transition-colors
                ${isActive
                  ? 'text-gray-400 hover:text-gray-700 hover:bg-gray-200 dark:hover:text-gray-200 dark:hover:bg-gray-700'
                  : 'text-transparent group-hover:text-gray-400 hover:!text-gray-700 hover:!bg-gray-200 dark:hover:!text-gray-200 dark:hover:!bg-gray-600'
                }`}
              title="閉じる"
            >
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )
      })}
    </div>
  )
}
