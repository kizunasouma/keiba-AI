/**
 * 設定ダイアログ — モーダル形式の設定画面
 *
 * タブ:
 * - JV-Link: サービスキー表示・変更
 * - データ: データ取込設定（データベースURL、保存パス）
 * - バージョン情報: アプリバージョン、ソフトウェアID
 */
import { useState, useEffect, useCallback } from 'react'
import { fetchSettings, updateSettings, checkJVLink } from '../api/client'
import type { AppSettings, JVLinkStatus } from '../types'

interface SettingsDialogProps {
  /** ダイアログを閉じるコールバック */
  onClose: () => void
}

type TabKey = 'jvlink' | 'data' | 'version'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'jvlink', label: 'JV-Link' },
  { key: 'data', label: 'データ' },
  { key: 'version', label: 'バージョン情報' },
]

/** JV-Link設定タブ */
function JVLinkTab() {
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [jvStatus, setJvStatus] = useState<JVLinkStatus | null>(null)
  const [serviceKey, setServiceKey] = useState('')
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // 設定読み込み
  useEffect(() => {
    fetchSettings().then(data => {
      setSettings(data)
      setServiceKey(data.jvlink_service_key || '')
    }).catch(() => {})
    checkJVLink().then(setJvStatus).catch(() => {})
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const result = await updateSettings({ jvlink_service_key: serviceKey })
      setSettings(result.settings)
      setEditing(false)
      setMessage({ type: 'success', text: '保存しました' })
      setTimeout(() => setMessage(null), 3000)
    } catch {
      setMessage({ type: 'error', text: '保存に失敗しました' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* JV-Link状態 */}
      {jvStatus && (
        <div className={`flex items-center gap-3 p-3 rounded-lg border ${
          jvStatus.jvlink_installed
            ? 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800'
            : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
        }`}>
          <span className="text-lg">{jvStatus.jvlink_installed ? '\u2705' : '\u274C'}</span>
          <div className="text-sm">
            <span className="font-medium dark:text-white text-gray-900">
              JV-Link: {jvStatus.jvlink_installed ? 'インストール済み' : '未インストール'}
            </span>
            {jvStatus.jvlink_version && (
              <span className="text-gray-500 dark:text-gray-400 ml-2">({jvStatus.jvlink_version})</span>
            )}
            <span className="ml-4">
              Agent: {jvStatus.agent_running
                ? <span className="text-emerald-500">実行中</span>
                : <span className="text-yellow-500">停止中</span>}
            </span>
          </div>
        </div>
      )}

      {/* サービスキー */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          サービスキー
        </label>
        {editing ? (
          <div className="flex gap-2">
            <input
              type="text"
              value={serviceKey}
              onChange={(e) => setServiceKey(e.target.value)}
              placeholder="17桁のサービスキー"
              maxLength={20}
              className="flex-1 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600
                bg-white dark:bg-gray-800 text-gray-900 dark:text-white
                focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500
                font-mono text-sm"
            />
            <button onClick={handleSave} disabled={saving}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm transition-colors disabled:opacity-50">
              {saving ? '...' : '保存'}
            </button>
            <button onClick={() => { setEditing(false); setServiceKey(settings?.jvlink_service_key || '') }}
              className="px-3 py-2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 text-sm">
              取消
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 px-3 py-2 rounded-lg flex-1">
              {settings?.jvlink_service_key || '未設定'}
            </span>
            <button onClick={() => setEditing(true)}
              className="px-3 py-2 text-sm text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-900/30 rounded-lg transition-colors">
              変更
            </button>
          </div>
        )}
      </div>

      {message && (
        <p className={`text-sm ${message.type === 'success' ? 'text-emerald-500' : 'text-red-500'}`}>
          {message.text}
        </p>
      )}
    </div>
  )
}

/** データ設定タブ */
function DataTab() {
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [dbUrl, setDbUrl] = useState('')
  const [savePath, setSavePath] = useState('')
  const [editingDb, setEditingDb] = useState(false)
  const [editingPath, setEditingPath] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    fetchSettings().then(data => {
      setSettings(data)
      setDbUrl(data.database_url || '')
      setSavePath(data.jvlink_save_path || '')
    }).catch(() => {})
  }, [])

  const handleSave = async (field: 'database_url' | 'jvlink_save_path') => {
    setSaving(true)
    setMessage(null)
    try {
      const updates = field === 'database_url'
        ? { database_url: dbUrl }
        : { jvlink_save_path: savePath }
      const result = await updateSettings(updates)
      setSettings(result.settings)
      if (field === 'database_url') setEditingDb(false)
      else setEditingPath(false)
      setMessage({ type: 'success', text: '保存しました（再起動後に反映）' })
      setTimeout(() => setMessage(null), 3000)
    } catch {
      setMessage({ type: 'error', text: '保存に失敗しました' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5">
      {/* データベースURL */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          データベース接続URL
        </label>
        {editingDb ? (
          <div className="flex gap-2">
            <input
              type="text"
              value={dbUrl}
              onChange={(e) => setDbUrl(e.target.value)}
              placeholder="postgresql://user:pass@host:5432/db"
              className="flex-1 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600
                bg-white dark:bg-gray-800 text-gray-900 dark:text-white
                focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500
                font-mono text-sm"
            />
            <button onClick={() => handleSave('database_url')} disabled={saving}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm transition-colors disabled:opacity-50">
              保存
            </button>
            <button onClick={() => { setEditingDb(false); setDbUrl(settings?.database_url || '') }}
              className="px-3 py-2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 text-sm">
              取消
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 px-3 py-2 rounded-lg flex-1 truncate">
              {settings?.database_url || '未設定'}
            </span>
            <button onClick={() => setEditingDb(true)}
              className="px-3 py-2 text-sm text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-900/30 rounded-lg transition-colors">
              変更
            </button>
          </div>
        )}
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
          変更は次回のAPI再起動時に反映されます
        </p>
      </div>

      {/* JV-Linkデータ保存パス */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          JV-Link データ保存パス
        </label>
        {editingPath ? (
          <div className="flex gap-2">
            <input
              type="text"
              value={savePath}
              onChange={(e) => setSavePath(e.target.value)}
              placeholder="空欄 = デフォルト"
              className="flex-1 px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600
                bg-white dark:bg-gray-800 text-gray-900 dark:text-white
                focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500
                font-mono text-sm"
            />
            <button onClick={() => handleSave('jvlink_save_path')} disabled={saving}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm transition-colors disabled:opacity-50">
              保存
            </button>
            <button onClick={() => { setEditingPath(false); setSavePath(settings?.jvlink_save_path || '') }}
              className="px-3 py-2 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 text-sm">
              取消
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 px-3 py-2 rounded-lg flex-1">
              {settings?.jvlink_save_path || '(デフォルト)'}
            </span>
            <button onClick={() => setEditingPath(true)}
              className="px-3 py-2 text-sm text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-900/30 rounded-lg transition-colors">
              変更
            </button>
          </div>
        )}
      </div>

      {/* 設定ファイルパス */}
      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          設定ファイルの場所
        </label>
        <span className="font-mono text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 px-3 py-2 rounded-lg block">
          {settings?.config_file_path || '-'}
        </span>
      </div>

      {message && (
        <p className={`text-sm ${message.type === 'success' ? 'text-emerald-500' : 'text-red-500'}`}>
          {message.text}
        </p>
      )}
    </div>
  )
}

/** バージョン情報タブ */
function VersionTab() {
  const [settings, setSettings] = useState<AppSettings | null>(null)

  useEffect(() => {
    fetchSettings().then(setSettings).catch(() => {})
  }, [])

  return (
    <div className="space-y-4">
      <div className="text-center mb-6">
        <div className="text-3xl mb-2">
          <span className="text-emerald-500 font-bold">AI</span>
          <span className="dark:text-white text-gray-900 font-bold">競馬予測</span>
        </div>
        <p className="text-gray-500 dark:text-gray-400 text-sm">
          JV-Link対応 AI馬券予測デスクトップアプリ
        </p>
      </div>

      <div className="bg-gray-100 dark:bg-gray-800 rounded-lg p-4 space-y-3">
        <div className="flex justify-between text-sm">
          <span className="text-gray-500 dark:text-gray-400">アプリバージョン</span>
          <span className="font-mono dark:text-white text-gray-900">v0.2.0</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500 dark:text-gray-400">AIモデル</span>
          <span className="font-mono dark:text-white text-gray-900">v5 (74特徴量)</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500 dark:text-gray-400">ソフトウェアID</span>
          <span className="font-mono dark:text-white text-gray-900">{settings?.jvlink_software_id || '-'}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500 dark:text-gray-400">フロントエンド</span>
          <span className="font-mono dark:text-white text-gray-900">Electron + React</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500 dark:text-gray-400">バックエンド</span>
          <span className="font-mono dark:text-white text-gray-900">Python 3.13 + FastAPI</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500 dark:text-gray-400">データベース</span>
          <span className="font-mono dark:text-white text-gray-900">PostgreSQL 16</span>
        </div>
      </div>

      <div className="text-center text-xs text-gray-400 dark:text-gray-500 mt-4">
        <p>Powered by LightGBM + CatBoost</p>
        <p className="mt-1">74特徴量 / 4モデルアンサンブル / 17セグメント特化</p>
      </div>
    </div>
  )
}

/** 設定ダイアログ本体 */
export default function SettingsDialog({ onClose }: SettingsDialogProps) {
  const [activeTab, setActiveTab] = useState<TabKey>('jvlink')

  // ESCキーで閉じる
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[10000] flex items-center justify-center">
      {/* オーバーレイ */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      {/* ダイアログ */}
      <div className="relative w-full max-w-lg bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        {/* ヘッダー */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-bold dark:text-white text-gray-900">設定</h2>
          <button onClick={onClose}
            className="p-1 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* タブ */}
        <div className="flex border-b border-gray-200 dark:border-gray-700 px-6">
          {TABS.map(tab => (
            <button key={tab.key} onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
              }`}>
              {tab.label}
            </button>
          ))}
        </div>

        {/* タブコンテンツ */}
        <div className="p-6 min-h-[300px]">
          {activeTab === 'jvlink' && <JVLinkTab />}
          {activeTab === 'data' && <DataTab />}
          {activeTab === 'version' && <VersionTab />}
        </div>
      </div>
    </div>
  )
}
