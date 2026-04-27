"""
テスト共通フィクスチャ
FastAPIテストクライアント + DBセッション管理
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.database import get_db, Base
from app.core.config import settings


# テスト用DBセッション（本番DBをそのまま使用、テスト専用スキーマは不要）
# ※破壊的操作は行わない読み取り専用テスト
_engine = create_engine(settings.database_url, echo=False)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(scope="session")
def db_session():
    """テスト用DBセッション（セッション全体で共有）"""
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def client():
    """FastAPIテストクライアント"""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def sample_race_key(db_session):
    """テスト用の実在するレースキー（直近のレースから取得）"""
    row = db_session.execute(
        text("SELECT race_key FROM races ORDER BY race_date DESC LIMIT 1")
    ).fetchone()
    if row:
        return row[0]
    pytest.skip("レースデータがDBに存在しません")


@pytest.fixture(scope="session")
def sample_horse_id(db_session):
    """テスト用の実在する馬ID"""
    row = db_session.execute(
        text("SELECT id FROM horses LIMIT 1")
    ).fetchone()
    if row:
        return row[0]
    pytest.skip("馬データがDBに存在しません")


@pytest.fixture(scope="session")
def sample_jockey_id(db_session):
    """テスト用の実在する騎手ID"""
    row = db_session.execute(
        text("SELECT id FROM jockeys LIMIT 1")
    ).fetchone()
    if row:
        return row[0]
    pytest.skip("騎手データがDBに存在しません")


@pytest.fixture(scope="session")
def sample_trainer_id(db_session):
    """テスト用の実在する調教師ID"""
    row = db_session.execute(
        text("SELECT id FROM trainers LIMIT 1")
    ).fetchone()
    if row:
        return row[0]
    pytest.skip("調教師データがDBに存在しません")
