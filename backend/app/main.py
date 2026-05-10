"""
FastAPI メインエントリポイント
`uvicorn app.main:app --reload` で起動する
"""
import time
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.security import SecurityMiddleware

# リクエストログ用ロガー
request_logger = logging.getLogger("app.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """リクエスト/レスポンスのログを出力するミドルウェア（所要時間・ステータスコード・パス）"""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        elapsed_ms = (time.time() - start) * 1000
        # メソッド、パス、ステータスコード、所要時間をINFOレベルで記録
        request_logger.info(
            "%s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

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
from app.api.tasks import settings_router

# アプリインスタンス
app = FastAPI(
    title="競馬AI予測API",
    description="JV-Linkデータを元にAIが馬券予測を行うAPI",
    version="0.2.0",
)

# セキュリティミドルウェア（SQLインジェクション・XSS防止）
app.add_middleware(SecurityMiddleware)

# リクエストログミドルウェア（所要時間・ステータスコード・パス記録）
app.add_middleware(RequestLoggingMiddleware)

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
app.include_router(settings_router)
