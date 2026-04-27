"""
アプリ全体の設定管理
.envファイルから設定値を読み込む
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # データベース接続URL
    database_url: str = "postgresql://keiba_user:keiba_pass@localhost:5432/keiba_db"

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
