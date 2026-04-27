# keiba-AI - 競馬AI予測デスクトップアプリ

JV-Link（JRA公式データ配信）から取得した70年分・24万レースの競馬データを機械学習で分析し、期待値ベースで馬券を予測するWindowsデスクトップアプリケーションです。

## 技術的ハイライト

### 機械学習パイプライン
- **4モデルアンサンブル**: LightGBM（Classifier + LambdaRank） + CatBoost + オッズなしモデル
- **Stackingメタラーナー**: LogisticRegressionで各モデルのOOF予測を最適統合
- **確率キャリブレーション**: Isotonic Regressionで予測確率を実勝率に補正（AUC 0.84達成）
- **74特徴量**: レース条件 / 通算成績 / 体重変動 / 騎手効率 / 血統適性 / 調教評価 / コーナー通過推移 等
- **17セグメント特化モデル**: 芝/ダート × 距離帯7 + 主要会場10に個別最適化
- **Optunaチューニング**: 自動ハイパーパラメータ最適化

### 異言語間データブリッジ
JV-Linkは32bit COM専用のため、64bit Python → C# (.NET 8.0 x86) ブリッジ経由で接続する設計を実装。
```
[64bit Python] ── subprocess ──→ [C#: JVLinkBridge.exe (x86)]
                                    ↓ COM Interop (JVDTLab.dll)
                                    ↓ JVOpen → JVRead
[PostgreSQL] ←── COPY/UPSERT ←── パイプ(1MBバッファ) ←── JV-VAN
```

### 高速データ取込（COPY方式）
- JV-Link → CSV → PostgreSQL COPY → ステージングマージの3段階パイプライン
- **従来比200倍の高速化**（500件/秒 → 10万件/秒以上）
- UNLOGGEDステージングテーブル + `synchronous_commit=off` + `work_mem=256MB`
- JOINベースのFK解決（race_key → race_id等をSQL内で一括変換）

### セキュリティ
- SQLインジェクション / XSS検出ミドルウェア（パラメータ化クエリ + 入力バリデーション）
- CORS制限（localhost + Electronオリジンのみ）
- Electronサンドボックス有効
- 認証情報は全て環境変数管理（.env）

## 技術スタック

| カテゴリ | 技術 |
|---------|------|
| バックエンド | Python 3.13 / FastAPI / SQLAlchemy / Pydantic |
| データベース | PostgreSQL 16（Docker） / Alembicマイグレーション |
| AI/ML | LightGBM / CatBoost / scikit-learn / Optuna |
| データ取得 | JV-Link COM → C# (.NET 8.0) ブリッジ |
| フロントエンド | Electron + React + TypeScript + Tailwind CSS + TanStack Query |
| CI/CD | GitHub Actions（lint / unit test / integration test / frontend build） |
| インフラ | Docker Compose（PostgreSQL + pgAdmin） |

## 主な機能

### バックエンド（47 APIエンドポイント）
- **レース情報**: 検索 / 詳細 / 出走馬（血統・過去走5走・脚質・調教）/ ラップ / 払戻
- **AI予測**: 勝率 / 期待値 / 推奨買い目 / AI見解テキスト（9軸ルールベース）
- **統計分析**: 種牡馬 / 母父 / 枠番 / 人気別成績 / 馬場指数 / 対戦表 / 展開予想 / 荒れ予測
- **バックテスト**: 回収率分析（6軸: トラック/グレード/距離帯/馬場/頭数/会場）/ 月別推移 / 精度モニタリング
- **買い目計算**: フォーメーション / ボックス / ながし / ケリー基準配分
- **馬・騎手・調教師**: 検索 / 成績 / 統計 / 相性分析

### フロントエンド
- ダッシュボード（週選択・開催日フィルター付きレースカードグリッド）
- AI予測ビュー（期待値TOP20 + 推奨買い目 + バックテスト結果）
- 出馬表（過去3走横展開 + sticky左固定 + 調教AI評価 + ファクター別5軸プログレスバー）
- オッズ推移グラフ（recharts LineChart）
- ライト/ダークモード完全対応
- Electron別ウィンドウ（フローティングウィンドウ）

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────┐
│  Electron + React (TypeScript)                              │
│  Dashboard / RaceDetail / AIPrediction / Stats / Betting    │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTP (localhost:8000)
┌──────────────────────▼──────────────────────────────────────┐
│  FastAPI  (47 endpoints)                                    │
│  ├─ api/     races, predictions, statistics, betting ...    │
│  ├─ ml/      features.py (74特徴量) + model.py (ensemble)  │
│  └─ core/    security middleware, config, database          │
└──────────────────────┬──────────────────────────────────────┘
                       │ SQLAlchemy
┌──────────────────────▼──────────────────────────────────────┐
│  PostgreSQL 16  (Docker)                                    │
│  12テーブル: races, race_entries, payouts, horses,          │
│  jockeys, trainers, pedigree_lineages, training_times ...   │
└──────────────────────▲──────────────────────────────────────┘
                       │ COPY / Bulk UPSERT
┌──────────────────────┴──────────────────────────────────────┐
│  Data Pipeline                                              │
│  copy_import.py ── subprocess ──→ JVLinkBridge.exe (C#)     │
│                                    ↓ COM Interop             │
│                                    JV-Link (JRA公式データ)   │
└─────────────────────────────────────────────────────────────┘
```

## セットアップ

### 前提条件
- Windows 11
- Python 3.13（64bit）
- Node.js 20+
- Docker Desktop
- JV-Link（JRA-VAN会員登録が必要）

### 環境構築

```bash
# リポジトリのクローン
git clone https://github.com/kizunasouma/keiba-AI.git
cd keiba-AI

# 環境変数の設定
cp .env.example .env
# .env を編集してDB接続情報等を設定

# Docker起動（PostgreSQL + pgAdmin）
docker-compose up -d

# バックエンドセットアップ
pip install poetry
poetry install

# DBマイグレーション
cd backend
alembic upgrade head

# フロントエンドセットアップ
cd ../frontend
npm install
```

### 起動

```bash
# APIサーバー（http://localhost:8000）
cd backend && uvicorn app.main:app --reload

# フロントエンド開発サーバー（http://localhost:5173）
cd frontend && npm run dev

# または一括起動
keiba-ai.bat
```

## プロジェクト構成

```
keiba-AI/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPIエントリ + セキュリティミドルウェア
│   │   ├── api/                 # 47エンドポイント（7モジュール）
│   │   ├── ml/                  # 特徴量エンジニアリング + アンサンブルモデル
│   │   ├── models/              # SQLAlchemy ORMモデル（12テーブル）
│   │   ├── schemas/             # Pydantic リクエスト/レスポンススキーマ
│   │   ├── services/            # JV-Dataパーサー（11レコード種別）+ インポーター
│   │   └── core/                # 設定 / DB接続 / セキュリティ
│   ├── bridge/JVLinkBridge/     # C# JV-Linkブリッジ（.NET 8.0 x86）
│   ├── scripts/                 # データ取込 / モデル学習 / バッチ処理
│   └── tests/                   # pytest（58テストケース）
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # ルート（ナビ/タブ/ダークモード）
│   │   ├── api/                 # APIクライアント + モックフォールバック
│   │   ├── components/          # 16 UIコンポーネント
│   │   └── hooks/               # カスタムフック（タブ/ウィンドウ管理）
│   └── electron/                # Electronメインプロセス + プリロード
├── .github/workflows/ci.yml    # GitHub Actions CI
├── docker-compose.yml
└── pyproject.toml
```

## 技術的な工夫・設計判断

| 課題 | 解決策 |
|------|--------|
| JV-Linkが32bit COM専用 | C# (.NET x86) ブリッジを作成し、64bit Pythonからsubprocess経由で通信 |
| 初回データ取込が遅い（70年分） | COPY方式3段階パイプラインで200倍高速化 |
| 競馬予測の不確実性 | 4モデルアンサンブル + Stacking + 確率キャリブレーションで信頼性向上 |
| コース/距離で傾向が異なる | 17セグメント特化モデルで条件別に最適化 |
| APIとフロント未接続時のUX | モックデータフォールバックで開発体験を維持 |
| セキュリティ | SQLi/XSS検出ミドルウェア + CORS制限 + sandbox + 環境変数管理 |

## ライセンス

Private - All rights reserved.
