/**
 * お気に入り馬画面 — 登録済み馬一覧・出走予定・登録/削除
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchFavorites, removeFavorite, fetchUpcomingFavorites } from '../api/client'
import ErrorBanner from './ErrorBanner'
import EmptyState from './EmptyState'

interface Props {
  onOpenHorse: (horseId: number, name?: string) => void
  onOpenRace: (raceKey: string, title?: string) => void
}

export default function FavoritesView({ onOpenHorse, onOpenRace }: Props) {
  const qc = useQueryClient()
  const { data: favorites, isLoading, isError, refetch } = useQuery({ queryKey: ['favorites'], queryFn: fetchFavorites, retry: 1 })
  const { data: upcoming } = useQuery({ queryKey: ['favorites-upcoming'], queryFn: fetchUpcomingFavorites })

  const removeMut = useMutation({
    mutationFn: (horseId: number) => removeFavorite(horseId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['favorites'] }); qc.invalidateQueries({ queryKey: ['favorites-upcoming'] }) },
  })

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-1">⭐ お気に入り馬</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">注目馬の登録・出走予定チェック</p>
      </div>

      {/* 出走予定 */}
      {upcoming && upcoming.length > 0 && (
        <section className="mb-8">
          <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
            <span className="w-1 h-5 bg-yellow-500 rounded-full" />
            直近の出走予定
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {upcoming.map((u: any, i: number) => (
              <div key={i}
                className="bg-white dark:bg-gray-800 rounded-xl border border-yellow-200 dark:border-yellow-800/50 p-4 cursor-pointer hover:border-yellow-500 transition-colors"
                onClick={() => onOpenRace(u.race_key, `${u.venue}${u.race_num}R ${u.race_name ?? ''}`)}>
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-yellow-600 dark:text-yellow-400 font-bold">{u.horse_name}</span>
                  <span className="text-xs text-gray-500 ml-auto">{u.race_date}</span>
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-300">{u.venue} {u.race_num}R {u.race_name ?? ''}</div>
                <div className="text-xs text-gray-500 mt-1">{u.track}{u.distance}m</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 登録済み一覧 */}
      <section>
        <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
          <span className="w-1 h-5 bg-emerald-500 rounded-full" />
          登録馬一覧
          <span className="text-xs text-gray-500 font-normal">{favorites?.length ?? 0}頭</span>
        </h2>

        {isLoading ? (
          <div className="text-gray-500 py-8 text-center">読み込み中...</div>
        ) : isError ? (
          <div className="py-4">
            <ErrorBanner message="お気に入りデータの取得に失敗しました" onRetry={() => refetch()} />
          </div>
        ) : !favorites || favorites.length === 0 ? (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-8 text-center text-gray-500">
            お気に入り馬が登録されていません<br />
            <span className="text-xs">馬カルテ画面から⭐ボタンで登録できます</span>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  <th className="px-4 py-2 text-left">馬名</th>
                  <th className="px-4 py-2 text-left">メモ</th>
                  <th className="px-4 py-2 text-center">操作</th>
                </tr>
              </thead>
              <tbody>
                {favorites.map((f: any) => (
                  <tr key={f.horse_id} className="border-t border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/20">
                    <td className="px-4 py-3">
                      <button onClick={() => onOpenHorse(f.horse_id, f.horse_name)}
                        className="text-emerald-600 dark:text-emerald-400 hover:text-emerald-500 dark:hover:text-emerald-300 font-medium">
                        {f.horse_name ?? `ID:${f.horse_id}`}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{f.note ?? '-'}</td>
                    <td className="px-4 py-3 text-center">
                      <button onClick={() => removeMut.mutate(f.horse_id)}
                        className="text-xs text-red-500 dark:text-red-400 hover:text-red-600 dark:hover:text-red-300 px-2 py-1 rounded hover:bg-red-50 dark:hover:bg-red-900/30">
                        削除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
