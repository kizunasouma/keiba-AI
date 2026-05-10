"""
アプリ全体の設定管理
1. %APPDATA%/keiba-ai/config.json を優先的に読み込む
2. なければ .env ファイルから読み込む（pydantic-settings）
3. save_config() で config.json に設定を保存可能
"""
import json
import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# config.json の保存先ディレクトリ
_APPDATA = os.environ.get("APPDATA", "")
CONFIG_DIR = Path(_APPDATA) / "keiba-ai" if _APPDATA else Path.home() / ".keiba-ai"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _load_config_json() -> Dict[str, Any]:
    """config.json を読み込む。存在しなければ空辞書を返す"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info("config.json を読み込みました: %s", CONFIG_FILE)
                return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("config.json の読み込みに失敗: %s", e)
    return {}


def _apply_config_json_to_env(data: Dict[str, Any]) -> None:
    """config.json の値を環境変数にセットして pydantic-settings で読み取れるようにする"""
    mapping = {
        "database_url": "DATABASE_URL",
        "jvlink_service_key": "JVLINK_SERVICE_KEY",
        "jvlink_software_id": "JVLINK_SOFTWARE_ID",
        "jvlink_save_path": "JVLINK_SAVE_PATH",
    }
    for json_key, env_key in mapping.items():
        if json_key in data and data[json_key]:
            os.environ[env_key] = str(data[json_key])


# 起動時に config.json があればその値を環境変数に反映
_config_json_data = _load_config_json()
if _config_json_data:
    _apply_config_json_to_env(_config_json_data)


class Settings(BaseSettings):
    # データベース接続URL（.envから読み込み）
    database_url: str = "postgresql://localhost:5432/keiba_db"

    # JV-Link利用キー（JRA-VANで取得した17桁）
    jvlink_service_key: str = "UNKNOWN"

    # JV-LinkソフトウェアID
    jvlink_software_id: str = "UNKNOWN"

    # JV-Linkデータ保存パス（空文字はデフォルトを使用）
    jvlink_save_path: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# シングルトンとして使い回す
settings = Settings()


def save_config(updates: Dict[str, Any]) -> None:
    """
    設定を config.json に保存する。
    既存の config.json があれば読み込んでマージし、なければ新規作成。
    """
    # 既存データを読み込み
    existing = _load_config_json()
    existing.update(updates)

    # ディレクトリ作成
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # 書き込み
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    logger.info("config.json を保存しました: %s", CONFIG_FILE)

    # settings シングルトンにも反映
    for key, value in updates.items():
        if hasattr(settings, key):
            object.__setattr__(settings, key, value)


def is_setup_completed() -> bool:
    """セットアップが完了済みかどうかを判定する"""
    data = _load_config_json()
    return bool(data.get("setup_completed", False))


def get_config_for_display() -> Dict[str, Any]:
    """
    表示用の設定情報を返す。
    パスワードを含む database_url はマスクする。
    """
    result = {
        "database_url": _mask_database_url(settings.database_url),
        "jvlink_service_key": _mask_string(settings.jvlink_service_key),
        "jvlink_software_id": settings.jvlink_software_id,
        "jvlink_save_path": settings.jvlink_save_path,
        "setup_completed": is_setup_completed(),
        "config_file_path": str(CONFIG_FILE),
    }
    return result


def _mask_database_url(url: str) -> str:
    """database_url のパスワード部分をマスクする"""
    if "://" not in url:
        return url
    try:
        # postgresql://user:password@host:port/db
        prefix, rest = url.split("://", 1)
        if "@" in rest:
            userpass, hostpart = rest.rsplit("@", 1)
            if ":" in userpass:
                user, _ = userpass.split(":", 1)
                return f"{prefix}://{user}:****@{hostpart}"
        return url
    except Exception:
        return url


def _mask_string(s: str, visible_chars: int = 4) -> str:
    """文字列の先頭数文字のみ表示し、残りをマスクする"""
    if not s or s == "UNKNOWN" or len(s) <= visible_chars:
        return s
    return s[:visible_chars] + "*" * (len(s) - visible_chars)
