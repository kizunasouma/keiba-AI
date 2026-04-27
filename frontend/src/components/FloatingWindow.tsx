/**
 * フローティングウィンドウ — ドラッグ移動・全辺リサイズ・最大化・最小化対応
 * position: fixed でメインウィンドウ外への移動を許可
 * 全辺・四隅からのリサイズに対応
 */
import { useRef, useCallback, useState } from 'react'
import type { FloatingWindow as FW } from '../hooks/useWindowManager'

const TYPE_ICON: Record<string, string> = {
  race: '🏇', horse: '🐴', jockey: '🧑', trainer: '👔',
}

/** リサイズの方向を示す型 */
type ResizeEdge = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'

/** リサイズハンドルの定義 */
const RESIZE_HANDLES: { edge: ResizeEdge; className: string; cursor: string }[] = [
  // 四辺
  { edge: 'n',  className: 'top-0 left-2 right-2 h-1.5',           cursor: 'ns-resize' },
  { edge: 's',  className: 'bottom-0 left-2 right-2 h-1.5',        cursor: 'ns-resize' },
  { edge: 'e',  className: 'top-2 right-0 bottom-2 w-1.5',         cursor: 'ew-resize' },
  { edge: 'w',  className: 'top-2 left-0 bottom-2 w-1.5',          cursor: 'ew-resize' },
  // 四隅
  { edge: 'nw', className: 'top-0 left-0 w-3 h-3',                 cursor: 'nwse-resize' },
  { edge: 'ne', className: 'top-0 right-0 w-3 h-3',                cursor: 'nesw-resize' },
  { edge: 'sw', className: 'bottom-0 left-0 w-3 h-3',              cursor: 'nesw-resize' },
  { edge: 'se', className: 'bottom-0 right-0 w-3 h-3',             cursor: 'nwse-resize' },
]

/** 最小サイズ */
const MIN_W = 320
const MIN_H = 250
/** タイトルバーの最低表示量（画面内に残す最低px） */
const MIN_VISIBLE = 50

interface Props {
  win: FW
  onFocus: () => void
  onClose: () => void
  onMove: (x: number, y: number) => void
  onResize: (w: number, h: number) => void
  onMoveAndResize: (x: number, y: number, w: number, h: number) => void
  onMinimize: () => void
  onMaximize: () => void
  children: React.ReactNode
}

export default function FloatingWindow({
  win, onFocus, onClose, onMove, onResize, onMoveAndResize, onMinimize, onMaximize, children,
}: Props) {
  const dragRef = useRef<{ startX: number; startY: number; winX: number; winY: number } | null>(null)
  const resizeRef = useRef<{
    startX: number; startY: number
    winX: number; winY: number; winW: number; winH: number
    edge: ResizeEdge
  } | null>(null)
  const [dragging, setDragging] = useState(false)
  const [resizing, setResizing] = useState(false)

  // ドラッグ開始 — position: fixed ベースでビューポート内に制約
  const onDragStart = useCallback((e: React.MouseEvent) => {
    if (win.maximized) return
    e.preventDefault()
    onFocus()
    dragRef.current = { startX: e.clientX, startY: e.clientY, winX: win.x, winY: win.y }
    setDragging(true)

    const onMouseMove = (ev: MouseEvent) => {
      if (!dragRef.current) return
      const dx = ev.clientX - dragRef.current.startX
      const dy = ev.clientY - dragRef.current.startY
      let newX = dragRef.current.winX + dx
      let newY = dragRef.current.winY + dy

      // タイトルバー部分が最低50px画面内に残るよう制約
      const vpW = window.innerWidth
      const vpH = window.innerHeight
      // 右にはみ出しすぎないよう制約（タイトルバーの左端50pxは画面内）
      newX = Math.min(newX, vpW - MIN_VISIBLE)
      // 左にはみ出しすぎないよう制約（タイトルバーの右端50pxは画面内）
      newX = Math.max(newX, -(win.width - MIN_VISIBLE))
      // 上にはみ出さないよう制約（タイトルバーは常に画面内）
      newY = Math.max(newY, 0)
      // 下にはみ出しすぎないよう制約（タイトルバー部分は画面内に残す）
      newY = Math.min(newY, vpH - MIN_VISIBLE)

      onMove(newX, newY)
    }
    const onMouseUp = () => {
      dragRef.current = null
      setDragging(false)
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }, [win.x, win.y, win.width, win.maximized, onFocus, onMove])

  // 辺・角からのリサイズ開始
  const onResizeStart = useCallback((edge: ResizeEdge, e: React.MouseEvent) => {
    if (win.maximized) return
    e.preventDefault()
    e.stopPropagation()
    onFocus()
    resizeRef.current = {
      startX: e.clientX, startY: e.clientY,
      winX: win.x, winY: win.y, winW: win.width, winH: win.height,
      edge,
    }
    setResizing(true)

    const onMouseMove = (ev: MouseEvent) => {
      if (!resizeRef.current) return
      const r = resizeRef.current
      const dx = ev.clientX - r.startX
      const dy = ev.clientY - r.startY
      // ビューポートの90%を最大サイズに
      const maxW = Math.floor(window.innerWidth * 0.9)
      const maxH = Math.floor(window.innerHeight * 0.9)

      let newX = r.winX
      let newY = r.winY
      let newW = r.winW
      let newH = r.winH

      // 方向に応じてサイズと位置を計算
      if (r.edge.includes('e')) {
        newW = Math.min(maxW, Math.max(MIN_W, r.winW + dx))
      }
      if (r.edge.includes('w')) {
        const proposedW = Math.min(maxW, Math.max(MIN_W, r.winW - dx))
        newX = r.winX + (r.winW - proposedW)
        newW = proposedW
      }
      if (r.edge.includes('s')) {
        newH = Math.min(maxH, Math.max(MIN_H, r.winH + dy))
      }
      if (r.edge.includes('n')) {
        const proposedH = Math.min(maxH, Math.max(MIN_H, r.winH - dy))
        newY = r.winY + (r.winH - proposedH)
        newH = proposedH
      }

      // 位置が変わる場合（上辺・左辺リサイズ）はmoveAndResizeを使う
      if (newX !== r.winX || newY !== r.winY) {
        onMoveAndResize(newX, newY, newW, newH)
      } else {
        onResize(newW, newH)
      }
    }
    const onMouseUp = () => {
      resizeRef.current = null
      setResizing(false)
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)
    }
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mouseup', onMouseUp)
  }, [win.x, win.y, win.width, win.height, win.maximized, onFocus, onResize, onMoveAndResize])

  // ダブルクリックで最大化
  const onDoubleClick = useCallback(() => { onMaximize() }, [onMaximize])

  // 最小化時は非表示
  if (win.minimized) return null

  // position: fixed で親要素から独立
  const style: React.CSSProperties = win.maximized
    ? { position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, width: '100%', height: '100%', zIndex: win.zIndex }
    : { position: 'fixed', top: win.y, left: win.x, width: win.width, height: win.height, zIndex: win.zIndex }

  return (
    <div
      style={style}
      className={`flex flex-col bg-white dark:bg-gray-900 rounded-xl overflow-hidden shadow-2xl border border-gray-200 dark:border-gray-700
        ${dragging || resizing ? '' : 'transition-shadow'}
        ${win.maximized ? '!rounded-none' : ''}`}
      onMouseDown={onFocus}
    >
      {/* タイトルバー */}
      <div
        className="flex items-center gap-2 px-3 py-1.5 bg-gray-100 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 select-none shrink-0"
        onMouseDown={onDragStart}
        onDoubleClick={onDoubleClick}
      >
        {/* ウィンドウアイコン＋タイトル */}
        <span className="text-sm shrink-0">{TYPE_ICON[win.descriptor.type] ?? '📄'}</span>
        <span className="flex-1 text-xs font-semibold text-gray-700 dark:text-gray-200 truncate">{win.title}</span>

        {/* 最小化 */}
        <button onClick={(e) => { e.stopPropagation(); onMinimize() }}
          className="w-7 h-5 flex items-center justify-center rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 transition-colors"
          title="最小化">
          <svg className="w-3 h-0.5" fill="currentColor"><rect width="12" height="2" /></svg>
        </button>
        {/* 最大化 */}
        <button onClick={(e) => { e.stopPropagation(); onMaximize() }}
          className="w-7 h-5 flex items-center justify-center rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 transition-colors"
          title={win.maximized ? '元に戻す' : '最大化'}>
          {win.maximized
            ? <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 10 10" stroke="currentColor" strokeWidth={1.5}><rect x="2" y="0" width="8" height="8" rx="1" /><rect x="0" y="2" width="8" height="8" rx="1" /></svg>
            : <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 10 10" stroke="currentColor" strokeWidth={1.5}><rect x="0.5" y="0.5" width="9" height="9" rx="1" /></svg>}
        </button>
        {/* 閉じる */}
        <button onClick={(e) => { e.stopPropagation(); onClose() }}
          className="w-7 h-5 flex items-center justify-center rounded hover:bg-red-500 hover:text-white text-gray-500 dark:text-gray-400 transition-colors"
          title="閉じる">
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* コンテンツ */}
      <div className="flex-1 overflow-y-auto">
        {children}
      </div>

      {/* リサイズハンドル（全辺・四隅） */}
      {!win.maximized && RESIZE_HANDLES.map(({ edge, className, cursor }) => (
        <div
          key={edge}
          className={`absolute ${className}`}
          style={{ cursor, zIndex: 1 }}
          onMouseDown={(e) => onResizeStart(edge, e)}
        />
      ))}

      {/* 右下角のビジュアルインジケーター（ドット） */}
      {!win.maximized && (
        <svg className="absolute bottom-0.5 right-0.5 w-3 h-3 text-gray-300 dark:text-gray-600 pointer-events-none" fill="currentColor" viewBox="0 0 12 12">
          <circle cx="10" cy="10" r="1.5" />
          <circle cx="6" cy="10" r="1.5" />
          <circle cx="10" cy="6" r="1.5" />
        </svg>
      )}
    </div>
  )
}
