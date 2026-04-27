"""
タスク実行API — フロントエンドからデータ最新化・AI推奨生成をトリガーする

バックグラウンドでスクリプトを実行し、進捗・結果を返す。
"""
import subprocess
import sys
import threading
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])

PYTHON64 = sys.executable
BACKEND_DIR = Path(__file__).parent.parent.parent
SCRIPTS_DIR = BACKEND_DIR / "scripts"

# 実行中タスクの状態管理
_task_state = {
    "sync": {"running": False, "last_run": None, "last_result": None, "log": ""},
    "predict": {"running": False, "last_run": None, "last_result": None, "log": ""},
}
_lock = threading.Lock()


def _run_sync_background():
    """バックグラウンドでデータ同期を実行"""
    with _lock:
        _task_state["sync"]["running"] = True
        _task_state["sync"]["log"] = "同期開始...\n"

    steps = []
    try:
        # Step 1: Docker確認
        _append_log("sync", "[1/3] Docker / keiba_db 確認中...\n")
        proc = subprocess.run(
            ["docker", "ps", "--filter", "name=keiba_db", "--format", "{{.Status}}"],
            capture_output=True, text=True, timeout=10,
        )
        if not proc.stdout.strip():
            subprocess.run(["docker", "start", "keiba_db"], capture_output=True, timeout=30)
            time.sleep(3)
        _append_log("sync", "   keiba_db: OK\n")
        steps.append("docker: ok")

        # Step 2: RACE差分同期（normalモード、3日前から取得で確定オッズ・結果・払戻を取得）
        from_date = (datetime.now() - timedelta(days=3)).strftime("%Y%m%d") + "000000"
        _append_log("sync", f"[2/4] RACE差分同期中（{from_date[:8]}〜）...\n")
        proc = subprocess.run(
            [PYTHON64, str(SCRIPTS_DIR / "sync_jvlink.py"), "--mode", "normal", "--dataspec", "RACE", "--fromtime", from_date],
            cwd=str(BACKEND_DIR), capture_output=True, text=True, timeout=600,
        )
        if proc.returncode == 0:
            _append_log("sync", "   RACE同期完了\n")
            steps.append("race_sync: ok")
        else:
            _append_log("sync", f"   RACE同期警告: {proc.stderr[:200]}\n")
            steps.append(f"race_sync: warning (rc={proc.returncode})")

        # RACE weekly（出走馬確定情報の取得）
        _append_log("sync", "   RACE週次同期中...\n")
        proc = subprocess.run(
            [PYTHON64, str(SCRIPTS_DIR / "sync_jvlink.py"), "--mode", "weekly", "--dataspec", "RACE"],
            cwd=str(BACKEND_DIR), capture_output=True, text=True, timeout=600,
        )
        if proc.returncode == 0:
            _append_log("sync", "   RACE週次完了\n")
            steps.append("race_weekly: ok")
        else:
            steps.append(f"race_weekly: warning (rc={proc.returncode})")

        # DIFN差分（マスタ更新）
        _append_log("sync", "[3/4] DIFN差分同期中...\n")
        proc = subprocess.run(
            [PYTHON64, str(SCRIPTS_DIR / "sync_jvlink.py"), "--mode", "normal", "--dataspec", "DIFN"],
            cwd=str(BACKEND_DIR), capture_output=True, text=True, timeout=600,
        )
        if proc.returncode == 0:
            _append_log("sync", "   DIFN同期完了\n")
            steps.append("difn_sync: ok")
        else:
            steps.append(f"difn_sync: warning (rc={proc.returncode})")

        # Step 4: リアルタイムデータ取得（確定情報 + 発売中オッズ）
        _append_log("sync", "[4/5] リアルタイムデータ取得中...\n")

        # 4a: 0B15（速報レース情報: 確定オッズ・着順・払戻・馬体重）
        proc = subprocess.run(
            [PYTHON64, str(SCRIPTS_DIR / "sync_jvlink.py"), "--rt", "--dataspec", "0B15"],
            cwd=str(BACKEND_DIR), capture_output=True, text=True, timeout=120,
        )
        if proc.returncode == 0:
            _append_log("sync", "   0B15（確定情報）完了\n")
            steps.append("rt_0B15: ok")
        else:
            _append_log("sync", f"   0B15警告: rc={proc.returncode}\n")
            steps.append(f"rt_0B15: warning")

        # 4b: 0B31（発売中レースのリアルタイムオッズ）
        from app.core.database import SessionLocal as SyncSession
        sync_db = SyncSession()
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            no_odds_races = sync_db.execute(text("""
                SELECT DISTINCT r.race_key
                FROM races r
                JOIN race_entries re ON re.race_id = r.id
                WHERE r.race_date = :today AND re.odds_win = 0
                ORDER BY r.race_key
            """), {"today": today_str}).fetchall()
            race_keys = [row[0] for row in no_odds_races]
        finally:
            sync_db.close()

        if race_keys:
            _append_log("sync", f"   0B31（発売中オッズ）{len(race_keys)}レース取得中...\n")
            sys.path.insert(0, str(BACKEND_DIR))
            from scripts.sync_jvlink import run_rt_odds
            ok_count = 0
            for rk in race_keys:
                try:
                    run_rt_odds(rk)
                    ok_count += 1
                except Exception:
                    pass
            _append_log("sync", f"   0B31完了（{ok_count}/{len(race_keys)}）\n")
            steps.append(f"rt_0B31: {ok_count}/{len(race_keys)}")
        else:
            _append_log("sync", "   全レースオッズ取得済み\n")
            steps.append("rt_0B31: skip")

        # Step 5: speed_index再計算
        _append_log("sync", "[5/5] speed_index再計算中...\n")
        since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        proc = subprocess.run(
            [PYTHON64, str(SCRIPTS_DIR / "calc_speed_index.py"), "--since", since],
            cwd=str(BACKEND_DIR), capture_output=True, text=True, timeout=120,
        )
        if proc.returncode == 0:
            _append_log("sync", "   speed_index更新完了\n")
            steps.append("speed_index: ok")
        else:
            steps.append(f"speed_index: warning (rc={proc.returncode})")

        _append_log("sync", "全ステップ完了\n")
        result = {"status": "success", "steps": steps}

    except Exception as e:
        _append_log("sync", f"エラー: {str(e)}\n")
        result = {"status": "error", "message": str(e), "steps": steps}

    with _lock:
        _task_state["sync"]["running"] = False
        _task_state["sync"]["last_run"] = datetime.now().isoformat()
        _task_state["sync"]["last_result"] = result


def _append_log(task_name: str, msg: str):
    """タスクログに追記"""
    with _lock:
        _task_state[task_name]["log"] += msg


@router.post("/sync")
def trigger_sync():
    """データ最新化（RACE/DIFN差分取得 + speed_index再計算）をバックグラウンド実行"""
    with _lock:
        if _task_state["sync"]["running"]:
            return {"status": "already_running", "message": "同期タスクは既に実行中です"}

    thread = threading.Thread(target=_run_sync_background, daemon=True)
    thread.start()
    return {"status": "started", "message": "データ最新化を開始しました"}


@router.get("/sync/status")
def sync_status():
    """データ最新化タスクの進捗・結果を取得"""
    with _lock:
        return {
            "running": _task_state["sync"]["running"],
            "last_run": _task_state["sync"]["last_run"],
            "last_result": _task_state["sync"]["last_result"],
            "log": _task_state["sync"]["log"],
        }


def _run_predict_background(scope: str = "month"):
    """バックグラウンドでAI予測を実行"""
    from app.core.database import SessionLocal
    db = SessionLocal()
    result = {"status": "error", "message": "不明なエラー"}

    try:
        today = datetime.now().date()

        if scope == "week":
            # 今週の土日（競馬開催日）
            day_of_week = today.weekday()  # 0=月
            if day_of_week == 6:  # 日曜
                sat = today - timedelta(days=1)
            elif day_of_week == 5:  # 土曜
                sat = today
            else:
                sat = today + timedelta(days=5 - day_of_week)
            sun = sat + timedelta(days=1)
            _append_log("predict", f"スコープ: 今週（{sat}〜{sun}）\n")
            rows = db.execute(text("""
                SELECT DISTINCT r.race_key, r.race_name, r.race_date
                FROM races r
                WHERE r.race_date BETWEEN :sat AND :sun
                ORDER BY r.race_date, r.race_key
            """), {"sat": sat, "sun": sun}).fetchall()
        elif scope.startswith("20"):
            # 日付指定（YYYY-MM-DD）
            _append_log("predict", f"スコープ: 指定日（{scope}）\n")
            rows = db.execute(text("""
                SELECT DISTINCT r.race_key, r.race_name, r.race_date
                FROM races r
                WHERE r.race_date = :target_date
                ORDER BY r.race_key
            """), {"target_date": scope}).fetchall()
        else:
            # 今月（デフォルト）
            month_start = today.replace(day=1)
            _append_log("predict", f"スコープ: 今月（{month_start}〜）\n")
            rows = db.execute(text("""
                SELECT DISTINCT r.race_key, r.race_name, r.race_date
                FROM races r
                WHERE r.race_date >= :month_start
                ORDER BY r.race_date, r.race_key
            """), {"month_start": month_start}).fetchall()

        if not rows:
            rows = db.execute(text("""
                SELECT DISTINCT r.race_key, r.race_name, r.race_date
                FROM races r
                ORDER BY r.race_date DESC, r.race_key
                LIMIT 48
            """)).fetchall()

        race_keys = [r[0] for r in rows]
        race_names = {r[0]: (r[1] or "") for r in rows}

        _append_log("predict", f"対象レース: {len(race_keys)}件\n")

        results = []
        errors = []
        for i, rk in enumerate(race_keys):
            name = race_names.get(rk, "")
            _append_log("predict", f"  [{i+1}/{len(race_keys)}] {rk} {name}\n")
            try:
                from app.api.predictions import predict_race
                pred = predict_race(rk, db)
                pred_list = pred.predictions if hasattr(pred, 'predictions') else []
                top = pred_list[:3]
                top_names = [f"{p.horse_num}番" for p in top]
                results.append({
                    "race_key": rk, "race_name": name,
                    "prediction_count": len(pred_list),
                    "top3": top_names,
                })
            except Exception as e:
                errors.append({"race_key": rk, "error": str(e)[:100]})

        _append_log("predict", f"完了: 成功={len(results)}, エラー={len(errors)}\n")

        result = {
            "status": "success",
            "total": len(race_keys),
            "success": len(results),
            "errors": len(errors),
            "results": results[:10],
            "error_details": errors[:5],
        }

    except Exception as e:
        result = {"status": "error", "message": str(e)}
    finally:
        db.close()

    with _lock:
        _task_state["predict"]["running"] = False
        _task_state["predict"]["last_run"] = datetime.now().isoformat()
        _task_state["predict"]["last_result"] = result


@router.post("/predict")
def trigger_predict_all(scope: str = "month"):
    """AI予測をバックグラウンドで一括生成する。scope: week/month/YYYY-MM-DD"""
    with _lock:
        if _task_state["predict"]["running"]:
            return {"status": "already_running", "message": "AI推奨生成は実行中です"}
        _task_state["predict"]["running"] = True
        _task_state["predict"]["log"] = ""

    thread = threading.Thread(target=_run_predict_background, args=(scope,), daemon=True)
    thread.start()

    scope_label = {"week": "今週", "month": "今月"}.get(scope, scope)
    return {"status": "started", "message": f"AI推奨生成を開始しました（{scope_label}）"}


@router.post("/predict/reset")
def predict_reset():
    """AI推奨生成タスクの状態を強制リセット"""
    with _lock:
        _task_state["predict"]["running"] = False
    return {"status": "reset", "message": "リセットしました"}


@router.get("/predict/status")
def predict_status():
    """AI推奨生成タスクの進捗・結果を取得"""
    with _lock:
        return {
            "running": _task_state["predict"]["running"],
            "last_run": _task_state["predict"]["last_run"],
            "last_result": _task_state["predict"]["last_result"],
            "log": _task_state["predict"]["log"],
        }


@router.get("/db/summary")
def db_summary(db: Session = Depends(get_db)):
    """DB概要情報（最終更新日時、レコード数等）"""
    row = db.execute(text("""
        SELECT
            (SELECT count(*) FROM races) AS races,
            (SELECT max(race_date) FROM races) AS latest_race,
            (SELECT count(*) FROM race_entries) AS entries,
            (SELECT count(*) FROM horses) AS horses,
            (SELECT count(*) FROM training_times) AS training
    """)).fetchone()
    return {
        "races": row[0],
        "latest_race": str(row[1]) if row[1] else None,
        "entries": row[2],
        "horses": row[3],
        "training": row[4],
    }
