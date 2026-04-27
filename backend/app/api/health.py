"""
ヘルスチェックAPI
アプリとDBの死活監視用エンドポイント
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db

router = APIRouter()


@router.get("/health")
def health_check():
    """アプリの生存確認"""
    return {"status": "ok"}


@router.get("/health/db")
def db_health_check(db: Session = Depends(get_db)):
    """DBへの接続確認"""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}
