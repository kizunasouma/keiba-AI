"""
レース当日ワークフロー自動化スクリプト

朝実行すると以下を順次実行:
1. JVLinkAgent起動確認
2. RACE差分データ取得（当週分）
3. speed_index再計算（直近分のみ）
4. APIサーバー起動

使い方:
    python scripts/daily_workflow.py
    python scripts/daily_workflow.py --skip-sync   # 同期をスキップ
    python scripts/daily_workflow.py --skip-api     # APIサーバーをスキップ
"""
import subprocess
import sys
import os
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PYTHON64 = sys.executable
BACKEND_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent


def check_docker():
    """Docker + keiba_db コンテナの起動確認"""
    logger.info("[1] Docker / keiba_db 確認...")
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=keiba_db", "--format", "{{.Status}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.stdout.strip():
            logger.info("   keiba_db: 起動済み")
            return True
    except Exception:
        pass

    logger.info("   keiba_db を起動中...")
    subprocess.run(["docker", "start", "keiba_db"], capture_output=True, timeout=30)
    time.sleep(3)
    logger.info("   keiba_db: 起動完了")
    return True


def sync_weekly():
    """当週のレースデータを差分取得"""
    logger.info("[2] RACE 差分同期中（今週分）...")
    proc = subprocess.run(
        [PYTHON64, str(SCRIPTS_DIR / "sync_jvlink.py"), "--mode", "weekly", "--dataspec", "RACE"],
        cwd=str(BACKEND_DIR),
        timeout=600,
    )
    if proc.returncode == 0:
        logger.info("   RACE同期完了")
    else:
        logger.warning(f"   RACE同期で警告: returncode={proc.returncode}")

    # DIFN差分（マスタ更新）
    logger.info("   DIFN 差分同期中...")
    proc = subprocess.run(
        [PYTHON64, str(SCRIPTS_DIR / "sync_jvlink.py"), "--mode", "normal", "--dataspec", "DIFN"],
        cwd=str(BACKEND_DIR),
        timeout=600,
    )
    if proc.returncode == 0:
        logger.info("   DIFN同期完了")
    else:
        logger.warning(f"   DIFN同期で警告: returncode={proc.returncode}")


def update_speed_index():
    """直近のspeed_indexを再計算"""
    logger.info("[3] speed_index 再計算中（直近30日分）...")
    since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    proc = subprocess.run(
        [PYTHON64, str(SCRIPTS_DIR / "calc_speed_index.py"), "--since", since],
        cwd=str(BACKEND_DIR),
        timeout=120,
    )
    if proc.returncode == 0:
        logger.info("   speed_index更新完了")


def start_api():
    """APIサーバー起動"""
    logger.info("[4] APIサーバー起動中 (port 8000)...")
    subprocess.Popen(
        [PYTHON64, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(BACKEND_DIR),
    )
    time.sleep(3)
    logger.info("   APIサーバー起動完了: http://localhost:8000")


def main():
    parser = argparse.ArgumentParser(description="レース当日ワークフロー")
    parser.add_argument("--skip-sync", action="store_true", help="データ同期をスキップ")
    parser.add_argument("--skip-api", action="store_true", help="APIサーバー起動をスキップ")
    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info(f"レース当日ワークフロー開始 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    logger.info("=" * 50)

    check_docker()

    if not args.skip_sync:
        sync_weekly()
    else:
        logger.info("[2] 同期スキップ")

    update_speed_index()

    if not args.skip_api:
        start_api()
    else:
        logger.info("[4] API起動スキップ")

    logger.info("")
    logger.info("準備完了。ブラウザで http://localhost:5173 を開いてください。")


if __name__ == "__main__":
    main()
