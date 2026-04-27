/**
 * ステータスバー — API接続状態を表示
 * 緑: API接続中 / 赤: 接続エラー
 */
import { useQuery } from '@tanstack/react-query'
import { fetchHealth } from '../api/client'

export default function StatusBar() {
  const { data, isError, isLoading } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
    retry: 1,
  })

  const dbOk = data?.database === 'connected'

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-xs">
        <Dot color="orange" label="接続中..." />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex items-center gap-2 text-xs">
        <Dot color="red" label="API未接続" />
      </div>
    )
  }

  return (
    <div className="flex items-center gap-3 text-xs">
      <Dot color="green" label="API接続中" />
      <Dot color={dbOk ? 'green' : 'yellow'} label="DB" />
    </div>
  )
}

/** 状態インジケータードット */
function Dot({ color, label }: { color: string; label: string }) {
  const c: Record<string, string> = {
    green: 'bg-emerald-500',
    yellow: 'bg-yellow-500',
    red: 'bg-red-500',
    orange: 'bg-orange-500 animate-pulse',
  }
  return (
    <div className="flex items-center gap-1.5">
      <span className={`inline-block w-1.5 h-1.5 rounded-full ${c[color] ?? 'bg-gray-400'}`} />
      <span className="text-gray-500 dark:text-gray-400">{label}</span>
    </div>
  )
}
