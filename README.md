# keiba-AI

JV-Linkから取得した公式競馬データをもとに、AIが馬券の予測（期待値基準）を行うWindowsデスクトップアプリです。

## 技術スタック

| カテゴリ | 技術 |
|---------|------|
| バックエンド | Python 3.13 / FastAPI / SQLAlchemy / Pydantic |
| データベース | PostgreSQL 16（Docker） |
| AI/ML | LightGBM / CatBoost / scikit-learn（4モデルアンサンブル、74特徴量） |
| データ取得 | JV-Link COM（C#ブリッジ方式、COPY高速取込対応） |
| フロントエンド | Electron + React + Tailwind CSS + TanStack Query |
| セキュリティ | SQLインジェクション/XSS防止、CORS制限、sandbox有効 |

## 主な機能

- **AI予測**: 4モデルアンサンブル + Stackingメタラーナー + 確率キャリブレーションによる勝率・期待値算出
- **74特徴量**: レース条件 / 馬基本 / 通算成績 / 体重・斤量 / 騎手・調教師 / 市場 / 直近成績 / 適性 / 血統 / 調教 等
- **17セグメント特化モデル**: 芝/ダート×距離帯 + 主要会場別に最適化
- **バックテスト**: 回収率分析（トラック/グレード/距離帯/馬場/頭数/会場の6軸）
- **買い目計算**: フォーメーション / ボックス / ながし / ケリー基準
- **47 APIエンドポイント**: レース / 馬 / 騎手 / 調教師 / 統計 / 予測 / バックテスト

## アーキテクチャ

### JV-Link データ取得
```
[Python] ─ subprocess ─→ [C#: JVLinkBridge.exe]
                            ↓ COM (JVDTLab.dll)
                            ↓ JVOpen → JVRead
[PostgreSQL] ←─ COPY/UPSERT ←─ パイプ ←─ JV-VAN
```

### COPY方式高速取込（初回・大量データ用）
- JV-Link → CSV → COPY → マージの3段階処理
- 従来比200倍の高速化（500件/秒 → 10万件/秒以上）

## セットアップ

### 前提条件
- Windows 11
- Python 3.13（64bit）
- Node.js
- Docker Desktop（PostgreSQL用）
- JV-Link（JRA公式データ取得ソフト）

### 環境構築

```bash
# 1. リポジトリのクローン
git clone https://github.com/kizunasouma/keiba-AI.git
cd keiba-AI

# 2. 環境変数の設定
cp .env.example .env
# .env を編集してDB接続情報等を設定

# 3. Docker起動（PostgreSQL）
docker-compose up -d

# 4. バックエンドセットアップ
pip install poetry
poetry install

# 5. フロントエンドセットアップ
cd frontend
npm install
cd ..
```

### データ取込

```bash
cd backend

# COPY方式（初回セットアップ推奨）
python scripts/copy_import.py --mode setup --dataspec RACE
python scripts/copy_import.py --mode setup --dataspec DIFN
python scripts/copy_import.py --mode setup --dataspec BLOD
python scripts/copy_import.py --mode setup --dataspec WOOD

# 日次差分更新
python scripts/sync_jvlink.py --mode normal --dataspec RACE
```

### 起動

```bash
# バックエンド（APIサーバー: http://localhost:8000）
cd backend
uvicorn app.main:app --reload

# フロントエンド（開発サーバー: http://localhost:5173）
cd frontend
npm run dev

# またはバッチファイルで一括起動
keiba-ai.bat
```

## プロジェクト構成

```
keiba-AI/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPIエントリ
│   │   ├── api/               # 47エンドポイント
│   │   ├── models/            # SQLAlchemyモデル
│   │   ├── schemas/           # Pydanticスキーマ
│   │   ├── services/          # JV-Dataパーサー / インポーター
│   │   └── ml/                # 特徴量エンジニアリング / AIモデル
│   ├── bridge/JVLinkBridge/   # C# JV-Linkブリッジ
│   └── scripts/               # データ取込 / 学習 / バッチ処理
├── frontend/
│   ├── src/
│   │   ├── App.tsx            # ルートコンポーネント
│   │   ├── api/               # APIクライアント
│   │   └── components/        # UIコンポーネント
│   └── electron/main.ts       # Electronメインプロセス
├── docker-compose.yml
└── pyproject.toml
```

## ライセンス

Private - All rights reserved.
