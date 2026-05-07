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
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PYTHON64 = sys.executable
BACKEND_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = Path(__file__).parent


def _wait_for_pg_ready(max_wait: int = 30) -> bool:
    """pg_isreadyでPostgreSQLの応答を確認（最大max_wait秒待機）"""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            result = subprocess.run(
                ["docker", "exec", "keiba_db", "pg_isready", "-U", "postgres"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _wait_for_health(url: str = "http://localhost:8000/health", max_wait: int = 30) -> bool:
    """HTTPヘルスチェックエンドポイントの応答を確認（最大max_wait秒待機）"""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            req = urllib.request.urlopen(url, timeout=3)
            if req.status == 200:
                return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(1)
    return False


def _log_elapsed(step_name: str, start: float):
    """ステップの所要時間をログ出力"""
    elapsed = time.time() - start
    logger.info(f"   {step_name} 所要時間: {elapsed:.1f}秒")


def check_docker():
    """Docker + keiba_db コンテナの起動確認 + pg_isreadyヘルスチェック"""
    step_start = time.time()
    logger.info("[1] Docker / keiba_db 確認...")
    already_running = False
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=keiba_db", "--format", "{{.Status}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.stdout.strip():
            logger.info("   keiba_db: 起動済み")
            already_running = True
    except Exception:
        pass

    if not already_running:
        logger.info("   keiba_db を起動中...")
        subprocess.run(["docker", "start", "keiba_db"], capture_output=True, timeout=30)

    # pg_isreadyで実際のDB応答を確認
    logger.info("   PostgreSQL応答確認中...")
    if _wait_for_pg_ready(max_wait=30):
        logger.info("   PostgreSQL: 応答OK")
    else:
        logger.error("   PostgreSQL: 30秒以内に応答しませんでした")
        raise RuntimeError("PostgreSQLが応答しません。Dockerコンテナを確認してください。")

    _log_elapsed("Docker/DB起動", step_start)
    return True


def sync_weekly(retry: bool = True):
    """当週のレースデータを差分取得（失敗時1回リトライ）"""
    step_start = time.time()
    logger.info("[2] RACE 差分同期中（今週分）...")

    def _run_sync(dataspec: str, mode: str):
        """同期サブプロセスを実行し、失敗時はリトライ"""
        proc = subprocess.run(
            [PYTHON64, str(SCRIPTS_DIR / "sync_jvlink.py"), "--mode", mode, "--dataspec", dataspec],
            cwd=str(BACKEND_DIR),
            timeout=600,
        )
        if proc.returncode == 0:
            logger.info(f"   {dataspec}同期完了")
            return True
        else:
            logger.warning(f"   {dataspec}同期で警告: returncode={proc.returncode}")
            return False

    # RACE同期（失敗時1回リトライ）
    if not _run_sync("RACE", "weekly") and retry:
        logger.info("   RACE同期リトライ中...")
        time.sleep(5)
        _run_sync("RACE", "weekly")

    # DIFN差分（マスタ更新）（失敗時1回リトライ）
    logger.info("   DIFN 差分同期中...")
    if not _run_sync("DIFN", "normal") and retry:
        logger.info("   DIFN同期リトライ中...")
        time.sleep(5)
        _run_sync("DIFN", "normal")

    _log_elapsed("データ同期", step_start)


def update_speed_index():
    """直近のspeed_indexを再計算"""
    step_start = time.time()
    logger.info("[3] speed_index 再計算中（直近30日分）...")
    since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    proc = subprocess.run(
        [PYTHON64, str(SCRIPTS_DIR / "calc_speed_index.py"), "--since", since],
        cwd=str(BACKEND_DIR),
        timeout=120,
    )
    if proc.returncode == 0:
        logger.info("   speed_index更新完了")
    _log_elapsed("speed_index計算", step_start)


def start_api():
    """APIサーバー起動 + ヘルスチェック確認"""
    step_start = time.time()
    logger.info("[4] APIサーバー起動中 (port 8000)...")
    subprocess.Popen(
        [PYTHON64, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(BACKEND_DIR),
    )

    # /healthエンドポイントで実際の起動を確認（最大30秒）
    logger.info("   APIヘルスチェック待機中...")
    if _wait_for_health("http://localhost:8000/health", max_wait=30):
        logger.info("   APIサーバー起動完了: http://localhost:8000")
    else:
        logger.warning("   APIサーバーが30秒以内にヘルスチェックに応答しませんでした")

    _log_elapsed("APIサーバー起動", step_start)


def main():
    parser = argparse.ArgumentParser(description="レース当日ワークフロー")
    parser.add_argument("--skip-sync", action="store_true", help="データ同期をスキップ")
    parser.add_argument("--skip-api", action="store_true", help="APIサーバー起動をスキップ")
    args = parser.parse_args()

    workflow_start = time.time()
    logger.info("=" * 50)
    logger.info(f"レース当日ワークフロー開始 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    logger.info("=" * 50)

    try:
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

        # ワークフロー全体の所要時間
        total = time.time() - workflow_start
        logger.info("")
        logger.info(f"準備完了（合計 {total:.1f}秒）。ブラウザで http://localhost:5173 を開いてください。")

    except Exception as e:
        # 異常終了時にエラーログ出力 + exit code 1
        logger.error(f"ワークフローが異常終了しました: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
