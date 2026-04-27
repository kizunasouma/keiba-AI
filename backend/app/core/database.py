"""
データベース接続・セッション管理
SQLAlchemyを使ってPostgreSQLに接続する
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# エンジン作成（接続プール最適化済み）
engine = create_engine(
    settings.database_url,
    echo=False,  # SQLログを出したい場合はTrue
    pool_size=20,           # デフォルト5→20に拡大（同期処理の並列度向上）
    max_overflow=10,        # オーバーフロー許容数
    pool_recycle=3600,      # コネクション再利用（1時間）
)

# セッションファクトリ
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """全モデルの基底クラス"""
    pass


def get_db():
    """
    FastAPIの依存性注入用DB セッションジェネレータ
    リクエストごとにセッションを生成し、例外時はrollback、終了後に閉じる
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
