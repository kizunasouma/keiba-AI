"""
Alembic マイグレーション環境設定
.env から DATABASE_URL を読み込み、全モデルを自動検出する
"""
import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# backend/ を sys.path に追加して app.* のインポートを可能にする
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.core.database import Base

# モデルを全てインポートしてメタデータに登録する
import app.models.race  # noqa: F401

# Alembic の Config オブジェクト
config = context.config

# logging 設定を alembic.ini から読み込む
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# .env の DATABASE_URL で alembic.ini の値を上書き
config.set_main_option("sqlalchemy.url", settings.database_url)

# マイグレーション対象のメタデータ
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """オフラインモード（DBへの接続なしでSQLを生成）"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """オンラインモード（DBに直接接続してマイグレーション実行）"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
