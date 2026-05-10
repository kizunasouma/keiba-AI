/**
 * Electronメインプロセス
 * Docker(PostgreSQL) + FastAPI を自動起動し、終了時に停止する
 */
import { app, BrowserWindow, shell, dialog, ipcMain } from 'electron'
import { spawn, execSync, ChildProcess } from 'child_process'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL']

// プロジェクトルート（frontend/の親ディレクトリ）
// ビルド後: dist-electron/ → frontend/ → keiba-AI/
// ソース: electron/ → frontend/ → keiba-AI/
const PROJECT_ROOT = path.resolve(__dirname, '../..')
const BACKEND_DIR = path.join(PROJECT_ROOT, 'backend')

// Pythonパス自動検出:
// 1. 環境変数 KEIBA_PYTHON_PATH があればそれを使用
// 2. なければ PATH 上の python を検索
// 3. それも見つからなければデフォルトパスにフォールバック
const DEFAULT_PYTHON_PATH = 'C:\\Users\\kizun\\AppData\\Local\\Programs\\Python\\Python313\\python.exe'

function detectPythonPath(): string {
  // 環境変数が設定されていればそちらを優先
  if (process.env.KEIBA_PYTHON_PATH) {
    console.log(`[Python] 環境変数 KEIBA_PYTHON_PATH を使用: ${process.env.KEIBA_PYTHON_PATH}`)
    return process.env.KEIBA_PYTHON_PATH
  }

  // PATH上のpythonを検索（64bitを優先、32bitは除外）
  try {
    const found = execSync('where python', { encoding: 'utf-8', timeout: 5000 })
      .split(/\r?\n/)
      .map(l => l.trim())
      .filter(l => l.length > 0 && !l.includes('32'))
    if (found.length > 0) {
      console.log(`[Python] PATH上で検出(64bit優先): ${found[0]}`)
      return found[0]
    }
  } catch {
    // where コマンド失敗 = PATHにpythonが見つからない
  }

  // フォールバック: デフォルトパス
  console.log(`[Python] デフォルトパスを使用: ${DEFAULT_PYTHON_PATH}`)
  return DEFAULT_PYTHON_PATH
}

const PYTHON_PATH = detectPythonPath()

let apiProcess: ChildProcess | null = null
let mainWindow: BrowserWindow | null = null
// ポップアップウィンドウを管理するMap（id → BrowserWindow）
const popupWindows = new Map<string, BrowserWindow>()

// ---------------------------------------------------------------------------
// ポップアップウィンドウ種別ごとのデフォルトサイズ
// ---------------------------------------------------------------------------
const POPUP_SIZES: Record<string, { width: number; height: number }> = {
  race: { width: 1200, height: 800 },
  horse: { width: 950, height: 700 },
  jockey: { width: 900, height: 650 },
  trainer: { width: 850, height: 600 },
}

// ---------------------------------------------------------------------------
// ポップアップウィンドウ生成（独立したOS別ウィンドウ）
// ---------------------------------------------------------------------------
function createPopupWindow(type: string, id: string): void {
  // 既に同じポップアップが開いている場合はフォーカスするだけ
  const popupId = `${type}-${id}`
  const existing = popupWindows.get(popupId)
  if (existing && !existing.isDestroyed()) {
    existing.focus()
    return
  }

  const size = POPUP_SIZES[type] ?? { width: 900, height: 700 }
  const popup = new BrowserWindow({
    width: size.width,
    height: size.height,
    // parentを指定しない → メインウィンドウと完全に独立して移動可能
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
    title: `${type} - ${id}`,
    icon: path.join(PROJECT_ROOT, 'assets', 'icon.ico'),
  })

  // ポップアップモードのURLをロード（クエリパラメータで種別とIDを渡す）
  if (VITE_DEV_SERVER_URL) {
    popup.loadURL(`${VITE_DEV_SERVER_URL}?popup=${encodeURIComponent(type)}&id=${encodeURIComponent(id)}`)
  } else {
    popup.loadFile(path.join(__dirname, '../dist/index.html'), {
      search: `popup=${encodeURIComponent(type)}&id=${encodeURIComponent(id)}`,
    })
  }

  // 外部リンクはブラウザで開く
  popup.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  // ウィンドウが閉じられたらMapから削除
  popup.on('closed', () => {
    popupWindows.delete(popupId)
  })

  popupWindows.set(popupId, popup)
}

// ---------------------------------------------------------------------------
// データベース起動（Docker優先 → ローカルPostgreSQL検出 → エラー）
// ---------------------------------------------------------------------------
function ensureDatabase(): { ok: boolean; mode: 'docker' | 'local' | 'none' } {
  // 1. Dockerコンテナ（keiba_db）の確認・起動
  try {
    const status = execSync('docker ps --filter name=keiba_db --format "{{.Status}}"', {
      encoding: 'utf-8',
      timeout: 10000,
    }).trim()
    if (status) {
      console.log('[DB] Docker keiba_db は起動済み')
      return { ok: true, mode: 'docker' }
    }
  } catch { /* Docker未インストール or 未起動 */ }

  try {
    execSync('docker start keiba_db', { encoding: 'utf-8', timeout: 30000 })
    console.log('[DB] Docker keiba_db 起動完了')
    return { ok: true, mode: 'docker' }
  } catch { /* keiba_dbコンテナが存在しない */ }

  // 2. ローカルPostgreSQLの検出（pg_isready コマンドで確認）
  try {
    execSync('pg_isready -U keiba_user -d keiba_db -h localhost -p 5432', {
      encoding: 'utf-8',
      timeout: 5000,
    })
    console.log('[DB] ローカルPostgreSQLを検出')
    return { ok: true, mode: 'local' }
  } catch { /* ローカルPostgreSQLなし */ }

  // 3. ポータブルPostgreSQLの起動（将来のインストーラー同梱用）
  const pgPortablePath = path.join(PROJECT_ROOT, 'pgsql', 'bin', 'pg_ctl.exe')
  try {
    const fs = require('fs')
    if (fs.existsSync(pgPortablePath)) {
      const pgDataDir = path.join(PROJECT_ROOT, 'pgdata')
      if (!fs.existsSync(pgDataDir)) {
        // 初回: initdb実行
        console.log('[DB] ポータブルPostgreSQL初期化中...')
        execSync(`"${path.join(PROJECT_ROOT, 'pgsql', 'bin', 'initdb.exe')}" -D "${pgDataDir}" -U keiba_user --encoding=UTF8`, {
          encoding: 'utf-8', timeout: 30000,
        })
      }
      console.log('[DB] ポータブルPostgreSQL起動中...')
      execSync(`"${pgPortablePath}" -D "${pgDataDir}" -l "${path.join(PROJECT_ROOT, 'logs', 'postgresql.log')}" start`, {
        encoding: 'utf-8', timeout: 15000,
      })
      return { ok: true, mode: 'local' }
    }
  } catch (e) {
    console.error('[DB] ポータブルPostgreSQL起動失敗:', e)
  }

  console.error('[DB] データベースが見つかりません')
  return { ok: false, mode: 'none' }
}

// ---------------------------------------------------------------------------
// FastAPI サーバー起動
// ---------------------------------------------------------------------------
function startApiServer(): ChildProcess | null {
  console.log('[API] uvicorn 起動中...')
  const proc = spawn(
    `"${PYTHON_PATH}"`,
    ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'],
    {
      cwd: BACKEND_DIR,
      stdio: ['ignore', 'pipe', 'pipe'],
      shell: true,
    },
  )

  proc.stdout?.on('data', (data: Buffer) => {
    const msg = data.toString().trim()
    if (msg) console.log(`[API] ${msg}`)
  })
  proc.stderr?.on('data', (data: Buffer) => {
    const msg = data.toString().trim()
    if (msg) console.log(`[API] ${msg}`)
  })
  proc.on('error', (err) => {
    console.error('[API] 起動エラー:', err)
  })
  proc.on('exit', (code) => {
    console.log(`[API] 終了 (code=${code})`)
    apiProcess = null
  })

  return proc
}

// ---------------------------------------------------------------------------
// APIサーバーの応答を待つ（最大30秒）
// ---------------------------------------------------------------------------
async function waitForApi(maxWaitMs = 30000): Promise<boolean> {
  const start = Date.now()
  while (Date.now() - start < maxWaitMs) {
    try {
      const res = await fetch('http://127.0.0.1:8000/health/db')
      if (res.ok) return true
    } catch { /* まだ起動中 */ }
    await new Promise(r => setTimeout(r, 500))
  }
  return false
}

// ---------------------------------------------------------------------------
// APIサーバー停止
// ---------------------------------------------------------------------------
function stopApiServer() {
  if (!apiProcess) return
  console.log('[API] uvicorn 停止中...')
  try {
    // Windows では taskkill でプロセスツリーごと停止
    if (apiProcess.pid) {
      execSync(`taskkill /PID ${apiProcess.pid} /T /F`, { encoding: 'utf-8' })
    }
  } catch {
    apiProcess.kill('SIGTERM')
  }
  apiProcess = null
}

// ---------------------------------------------------------------------------
// ウィンドウ生成
// ---------------------------------------------------------------------------
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 600,
    title: '競馬AI予測',
    icon: path.join(PROJECT_ROOT, 'assets', 'icon.ico'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  })

  if (VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(VITE_DEV_SERVER_URL)
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

// ---------------------------------------------------------------------------
// アプリ起動シーケンス
// ---------------------------------------------------------------------------
app.whenReady().then(async () => {
  // IPC: ポップアップウィンドウを開く
  ipcMain.handle('open-popup', (_event, type: string, id: string) => {
    createPopupWindow(type, id)
  })

  // IPC: ポップアップウィンドウのタイトルを更新
  ipcMain.handle('set-popup-title', (event, title: string) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (win) {
      win.setTitle(title)
    }
  })

  // 1. データベース起動（Docker → ローカルPostgreSQL → ポータブル）
  const dbResult = ensureDatabase()
  if (!dbResult.ok) {
    const result = dialog.showMessageBoxSync({
      type: 'warning',
      title: 'データベース未検出',
      message: 'PostgreSQLデータベースが見つかりません。\n\n'
        + '以下のいずれかの方法でデータベースを準備してください：\n'
        + '• Docker Desktop を起動して keiba_db コンテナを起動\n'
        + '• PostgreSQL をローカルにインストール\n\n'
        + 'データベースなしで起動しますか？（一部機能が制限されます）',
      buttons: ['データベースなしで起動', '終了'],
      defaultId: 1,
    })
    if (result === 1) {
      app.quit()
      return
    }
  } else {
    console.log(`[DB] モード: ${dbResult.mode}`)
  }

  // 2. APIサーバー起動（既に起動中なら省略）
  const alreadyRunning = await (async () => {
    try {
      const res = await fetch('http://127.0.0.1:8000/health/db')
      return res.ok
    } catch { return false }
  })()
  if (alreadyRunning) {
    console.log('[API] 既に起動中。新規起動をスキップ。')
  } else {
    apiProcess = startApiServer()
  }

  // 3. ウィンドウ生成（API起動中に先に表示）
  createWindow()

  // 4. API応答待ち（バックグラウンドで待機）
  const apiOk = await waitForApi()
  if (!apiOk) {
    console.warn('[API] 応答タイムアウト。UIは表示済みだが、データ取得に失敗する可能性あり。')
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

// ---------------------------------------------------------------------------
// アプリ終了時にAPIサーバーを停止
// ---------------------------------------------------------------------------
app.on('before-quit', () => {
  // 全ポップアップウィンドウを閉じる
  for (const [, popup] of popupWindows) {
    if (!popup.isDestroyed()) popup.close()
  }
  popupWindows.clear()
  stopApiServer()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
