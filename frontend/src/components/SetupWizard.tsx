/**
 * セットアップウィザード — 初回起動時に表示される5ステップのガイド
 *
 * ステップ:
 * 1. ようこそ画面（アプリ概要）
 * 2. JV-Linkインストール確認
 * 3. JV-Linkサービスキー入力
 * 4. データベース初期化（自動実行・進捗表示）
 * 5. 完了画面
 */
import { useState, useEffect, useCallback } from 'react'
import { checkJVLink, updateSettings, completeSetup, fetchDbSummary } from '../api/client'
import type { JVLinkStatus } from '../types'

interface SetupWizardProps {
  /** セットアップ完了時のコールバック */
  onComplete: () => void
}

/** ステップインジケーター */
function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center justify-center gap-2 mb-8">
      {Array.from({ length: total }, (_, i) => (
        <div key={i} className="flex items-center gap-2">
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-colors ${
            i + 1 === current
              ? 'bg-emerald-500 text-white'
              : i + 1 < current
                ? 'bg-emerald-700 text-emerald-200'
                : 'bg-gray-300 dark:bg-gray-700 text-gray-500 dark:text-gray-400'
          }`}>
            {i + 1 < current ? '\u2713' : i + 1}
          </div>
          {i < total - 1 && (
            <div className={`w-12 h-0.5 ${
              i + 1 < current ? 'bg-emerald-500' : 'bg-gray-300 dark:bg-gray-700'
            }`} />
          )}
        </div>
      ))}
    </div>
  )
}

/** ステップ1: ようこそ画面 */
function StepWelcome({ onNext }: { onNext: () => void }) {
  return (
    <div className="text-center">
      <div className="text-6xl mb-6">
        <span className="text-emerald-500 font-bold">AI</span>
        <span className="dark:text-white text-gray-900 font-bold">競馬予測</span>
      </div>
      <h2 className="text-2xl font-bold mb-4 dark:text-white text-gray-900">
        ようこそ！
      </h2>
      <p className="text-gray-600 dark:text-gray-300 mb-6 max-w-md mx-auto leading-relaxed">
        このアプリは、JV-Linkから取得した公式競馬データをもとに、
        AIが馬券の予測（期待値基準）を行うデスクトップアプリです。
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-lg mx-auto mb-8">
        {[
          ['74特徴量', 'AIが多角的に分析'],
          ['4モデル', 'アンサンブル予測'],
          ['期待値基準', '回収率重視の戦略'],
        ].map(([title, desc]) => (
          <div key={title} className="bg-gray-100 dark:bg-gray-800 rounded-lg p-3">
            <div className="text-emerald-500 font-bold text-sm">{title}</div>
            <div className="text-xs text-gray-500 dark:text-gray-400">{desc}</div>
          </div>
        ))}
      </div>
      <button onClick={onNext}
        className="px-8 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-medium transition-colors">
        セットアップを開始
      </button>
    </div>
  )
}

/** ステップ2: JV-Linkインストール確認 */
function StepJVLinkCheck({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [status, setStatus] = useState<JVLinkStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const checkStatus = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await checkJVLink()
      setStatus(data)
    } catch (e: any) {
      setError('JV-Linkの確認に失敗しました。APIサーバーが起動しているか確認してください。')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { checkStatus() }, [checkStatus])

  return (
    <div>
      <h2 className="text-xl font-bold mb-4 dark:text-white text-gray-900 text-center">
        JV-Link インストール確認
      </h2>
      <p className="text-gray-600 dark:text-gray-300 mb-6 text-center text-sm">
        JV-Linkは JRA-VAN が提供する競馬データ取得ソフトウェアです。
      </p>

      {loading && (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500" />
          <span className="ml-3 text-gray-500 dark:text-gray-400">確認中...</span>
        </div>
      )}

      {error && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-4">
          <p className="text-red-700 dark:text-red-300 text-sm">{error}</p>
        </div>
      )}

      {status && !loading && (
        <div className="space-y-3 mb-6">
          {/* JV-Link本体 */}
          <div className={`flex items-center gap-3 p-4 rounded-lg border ${
            status.jvlink_installed
              ? 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800'
              : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
          }`}>
            <span className="text-2xl">{status.jvlink_installed ? '\u2705' : '\u274C'}</span>
            <div>
              <div className="font-medium dark:text-white text-gray-900">
                JV-Link {status.jvlink_installed ? 'インストール済み' : '未インストール'}
              </div>
              {status.jvlink_version && (
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  バージョン: {status.jvlink_version}
                </div>
              )}
            </div>
          </div>

          {/* JVLinkAgent */}
          <div className={`flex items-center gap-3 p-4 rounded-lg border ${
            status.agent_running
              ? 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800'
              : 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
          }`}>
            <span className="text-2xl">{status.agent_running ? '\u2705' : '\u26A0\uFE0F'}</span>
            <div>
              <div className="font-medium dark:text-white text-gray-900">
                JVLinkAgent {status.agent_running ? '実行中' : '停止中'}
              </div>
              {!status.agent_running && (
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  「net start JVLinkAgent」で起動してください
                </div>
              )}
            </div>
          </div>

          {status.error_message && (
            <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-3">
              <p className="text-yellow-700 dark:text-yellow-300 text-sm">{status.error_message}</p>
              <a href="https://jra-van.jp/dlb/sdv/download.html"
                target="_blank" rel="noopener noreferrer"
                className="text-emerald-600 dark:text-emerald-400 text-sm underline mt-1 inline-block">
                JV-Link ダウンロードページ
              </a>
            </div>
          )}
        </div>
      )}

      <div className="flex justify-between">
        <button onClick={onBack}
          className="px-6 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors">
          戻る
        </button>
        <div className="flex gap-2">
          <button onClick={checkStatus}
            className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors text-sm">
            再確認
          </button>
          <button onClick={onNext}
            className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-medium transition-colors">
            {status?.jvlink_installed ? '次へ' : 'スキップして次へ'}
          </button>
        </div>
      </div>
    </div>
  )
}

/** ステップ3: サービスキー入力 */
function StepServiceKey({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [serviceKey, setServiceKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSave = async () => {
    if (!serviceKey.trim()) {
      // キーなしでもスキップ可能
      onNext()
      return
    }
    setSaving(true)
    setError(null)
    try {
      await updateSettings({ jvlink_service_key: serviceKey.trim() })
      setSaved(true)
      setTimeout(() => onNext(), 500)
    } catch (e: any) {
      setError('設定の保存に失敗しました。')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <h2 className="text-xl font-bold mb-4 dark:text-white text-gray-900 text-center">
        JV-Link サービスキー設定
      </h2>
      <p className="text-gray-600 dark:text-gray-300 mb-6 text-center text-sm">
        JRA-VANデータラボで取得した17桁のサービスキーを入力してください。
        <br />後から設定画面で変更することもできます。
      </p>

      <div className="max-w-md mx-auto mb-6">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          サービスキー
        </label>
        <input
          type="text"
          value={serviceKey}
          onChange={(e) => setServiceKey(e.target.value)}
          placeholder="例: ABCDE12345678FGHI"
          maxLength={20}
          className="w-full px-4 py-3 rounded-lg border border-gray-300 dark:border-gray-600
            bg-white dark:bg-gray-800 text-gray-900 dark:text-white
            focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500
            placeholder-gray-400 dark:placeholder-gray-500 font-mono text-lg tracking-wider"
        />
        {error && (
          <p className="text-red-500 text-sm mt-2">{error}</p>
        )}
        {saved && (
          <p className="text-emerald-500 text-sm mt-2">保存しました</p>
        )}
      </div>

      <div className="flex justify-between">
        <button onClick={onBack}
          className="px-6 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors">
          戻る
        </button>
        <button onClick={handleSave} disabled={saving}
          className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-medium transition-colors disabled:opacity-50">
          {saving ? '保存中...' : serviceKey.trim() ? '保存して次へ' : 'スキップして次へ'}
        </button>
      </div>
    </div>
  )
}

/** ステップ4: データベース初期化 */
function StepDatabase({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [status, setStatus] = useState<'idle' | 'checking' | 'done' | 'error'>('idle')
  const [dbInfo, setDbInfo] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)

  const checkDatabase = useCallback(async () => {
    setStatus('checking')
    setError(null)
    try {
      const data = await fetchDbSummary()
      setDbInfo(data)
      setStatus('done')
    } catch (e: any) {
      setError('データベースへの接続に失敗しました。Dockerが起動しているか確認してください。')
      setStatus('error')
    }
  }, [])

  useEffect(() => { checkDatabase() }, [checkDatabase])

  return (
    <div>
      <h2 className="text-xl font-bold mb-4 dark:text-white text-gray-900 text-center">
        データベース確認
      </h2>
      <p className="text-gray-600 dark:text-gray-300 mb-6 text-center text-sm">
        PostgreSQLデータベースの接続を確認します。
      </p>

      <div className="max-w-md mx-auto mb-6">
        {status === 'checking' && (
          <div className="flex flex-col items-center py-8">
            <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-emerald-500 mb-4" />
            <p className="text-gray-500 dark:text-gray-400">データベースを確認中...</p>
            {/* 進捗バー風の表示 */}
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 mt-4">
              <div className="bg-emerald-500 h-2 rounded-full animate-pulse" style={{ width: '60%' }} />
            </div>
          </div>
        )}

        {status === 'done' && dbInfo && (
          <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-2xl">\u2705</span>
              <span className="font-bold text-emerald-700 dark:text-emerald-300">接続成功</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="text-gray-600 dark:text-gray-400">レース数:</div>
              <div className="font-mono dark:text-white text-gray-900">{dbInfo.races?.toLocaleString() ?? 0}</div>
              <div className="text-gray-600 dark:text-gray-400">出走馬数:</div>
              <div className="font-mono dark:text-white text-gray-900">{dbInfo.entries?.toLocaleString() ?? 0}</div>
              <div className="text-gray-600 dark:text-gray-400">競走馬数:</div>
              <div className="font-mono dark:text-white text-gray-900">{dbInfo.horses?.toLocaleString() ?? 0}</div>
              <div className="text-gray-600 dark:text-gray-400">最新レース:</div>
              <div className="font-mono dark:text-white text-gray-900">{dbInfo.latest_race ?? '-'}</div>
            </div>
            {dbInfo.races === 0 && (
              <p className="text-yellow-600 dark:text-yellow-400 text-xs mt-3">
                データが空です。セットアップ完了後に「データ最新化」からデータを取り込んでください。
              </p>
            )}
          </div>
        )}

        {status === 'error' && (
          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-2xl">\u274C</span>
              <span className="font-bold text-red-700 dark:text-red-300">接続失敗</span>
            </div>
            <p className="text-red-600 dark:text-red-400 text-sm mb-3">{error}</p>
            <div className="text-xs text-gray-500 dark:text-gray-400 space-y-1">
              <p>以下を確認してください:</p>
              <ul className="list-disc list-inside">
                <li>Docker Desktop が起動しているか</li>
                <li>keiba_db コンテナが実行中か（docker start keiba_db）</li>
                <li>データベース接続URLが正しいか</li>
              </ul>
            </div>
          </div>
        )}
      </div>

      <div className="flex justify-between">
        <button onClick={onBack}
          className="px-6 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors">
          戻る
        </button>
        <div className="flex gap-2">
          {(status === 'error' || status === 'idle') && (
            <button onClick={checkDatabase}
              className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors text-sm">
              再確認
            </button>
          )}
          <button onClick={onNext}
            className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-medium transition-colors">
            {status === 'done' ? '次へ' : 'スキップして次へ'}
          </button>
        </div>
      </div>
    </div>
  )
}

/** ステップ5: 完了画面 */
function StepComplete({ onFinish }: { onFinish: () => void }) {
  const [completing, setCompleting] = useState(false)

  const handleFinish = async () => {
    setCompleting(true)
    try {
      await completeSetup()
    } catch {
      // 完了フラグの保存に失敗しても続行可能
    }
    onFinish()
  }

  return (
    <div className="text-center">
      <div className="text-6xl mb-4">{'🎉'}</div>
      <h2 className="text-2xl font-bold mb-4 dark:text-white text-gray-900">
        セットアップ完了！
      </h2>
      <p className="text-gray-600 dark:text-gray-300 mb-6 max-w-md mx-auto leading-relaxed">
        初期設定が完了しました。メイン画面に進みましょう。
      </p>
      <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 max-w-md mx-auto mb-8 text-left">
        <h3 className="font-medium text-sm mb-2 dark:text-white text-gray-900">次のステップ:</h3>
        <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-2">
          <li className="flex gap-2">
            <span className="text-emerald-500 shrink-0">1.</span>
            「データ最新化」ボタンでJV-Linkからデータを取り込む
          </li>
          <li className="flex gap-2">
            <span className="text-emerald-500 shrink-0">2.</span>
            レースダッシュボードで開催レースを確認
          </li>
          <li className="flex gap-2">
            <span className="text-emerald-500 shrink-0">3.</span>
            AI予想タブで期待値の高い馬をチェック
          </li>
        </ul>
      </div>
      <button onClick={handleFinish} disabled={completing}
        className="px-8 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-medium transition-colors disabled:opacity-50">
        {completing ? '準備中...' : 'メイン画面へ'}
      </button>
    </div>
  )
}

/** セットアップウィザード本体 */
export default function SetupWizard({ onComplete }: SetupWizardProps) {
  const [step, setStep] = useState(1)
  const totalSteps = 5

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl bg-white dark:bg-gray-850 dark:bg-gray-800/50 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 p-8">
        <StepIndicator current={step} total={totalSteps} />

        {step === 1 && <StepWelcome onNext={() => setStep(2)} />}
        {step === 2 && <StepJVLinkCheck onNext={() => setStep(3)} onBack={() => setStep(1)} />}
        {step === 3 && <StepServiceKey onNext={() => setStep(4)} onBack={() => setStep(2)} />}
        {step === 4 && <StepDatabase onNext={() => setStep(5)} onBack={() => setStep(3)} />}
        {step === 5 && <StepComplete onFinish={onComplete} />}
      </div>
    </div>
  )
}
