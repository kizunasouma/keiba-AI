"""
FastAPI メインエントリポイント
`uvicorn app.main:app --reload` で起動する
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.security import SecurityMiddleware

from app.api.health import router as health_router
from app.api.races import router as races_router
from app.api.predictions import router as predictions_router
from app.api.horses import router as horses_router
from app.api.jockeys import router as jockeys_router
from app.api.trainers import router as trainers_router
from app.api.statistics import router as stats_router
from app.api.betting import router as betting_router
from app.api.favorites import router as favorites_router
from app.api.export import router as export_router
from app.api.tasks import router as tasks_router

# アプリインスタンス
app = FastAPI(
    title="競馬AI予測API",
    description="JV-Linkデータを元にAIが馬券予測を行うAPI",
    version="0.2.0",
)

# セキュリティミドルウェア（SQLインジェクション・XSS防止）
app.add_middleware(SecurityMiddleware)

# CORS設定（Electronフロントエンドからのアクセスを許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",    # Vite dev server
        "http://localhost:8000",    # FastAPI
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "app://.",                   # Electron
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# ルーター登録
app.include_router(health_router, tags=["health"])
app.include_router(races_router)
app.include_router(predictions_router)
app.include_router(horses_router)
app.include_router(jockeys_router)
app.include_router(trainers_router)
app.include_router(stats_router)
app.include_router(betting_router)
app.include_router(favorites_router)
app.include_router(export_router)
app.include_router(tasks_router)
