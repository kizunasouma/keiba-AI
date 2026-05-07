"""
JV-Link データ同期スクリプト（v3: パイプ読取とDB書込を並列化）

パイプ読取スレッドがキューにレコードを詰め、
メインスレッドがバルクUPSERTでDBに書き込む。
"""
import sys
import os
import argparse
import logging
import struct
import subprocess
import time
import threading
import queue
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.jv_parser import parse_record
from app.services.jv_importer import (
    preload_cache, RecordBuffer, flush_in_order,
    FLUSH_ORDER, _BULK_SAVERS,
    get_last_timestamp, update_last_timestamp,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# C#ブリッジ（推奨: JV-Link COM の安定性が向上）
CSHARP_BRIDGE = Path(__file__).parent.parent / "bridge" / "JVLinkBridge" / "bin" / "Release" / "net8.0-windows" / "JVLinkBridge.exe"
# Python 32bitブリッジ（C#ブリッジが見つからない場合のフォールバック）
PYTHON32 = Path(os.environ.get(
    "PYTHON32_PATH",
    r"C:\Users\kizun\AppData\Local\Programs\Python\Python311-32\python.exe",
))
BRIDGE_SCRIPT = Path(__file__).parent / "jvlink_bridge.py"

OPTION_MAP = {"normal": 1, "weekly": 2, "setup": 3}
DEFAULT_DATASPEC = "DIFN"
BATCH_SIZE = 3000           # バルクUPSERTのバッチサイズ（1000→3000に拡大）
COMMIT_INTERVAL = 10000     # コミット間隔（5000→10000に拡大）
QUEUE_SIZE = 20000          # パイプ→DBキューの最大サイズ（5000→20000に拡大）

_SENTINEL = None  # キュー終端マーカー


def _start_bridge(dataspec: str, fromtime: str, option: int) -> subprocess.Popen:
    """ブリッジプロセスを起動（C#版優先、なければPython 32bit版にフォールバック）"""
    env = os.environ.copy()
    # JV-Link設定はレジストリから自動読取させる（環境変数は渡さない）
    # ※ 環境変数経由だとJVSetServiceKeyが-101エラーになるケースがあるため
    if settings.jvlink_save_path:
        env["JVLINK_SAVE_PATH"] = settings.jvlink_save_path

    if CSHARP_BRIDGE.exists():
        # C#ブリッジ（推奨）
        cmd = [
            str(CSHARP_BRIDGE),
            "--dataspec", dataspec, "--fromtime", fromtime, "--option", str(option),
        ]
    elif PYTHON32.exists():
        # Python 32bitフォールバック
        cmd = [
            str(PYTHON32), str(BRIDGE_SCRIPT),
            "--dataspec", dataspec, "--fromtime", fromtime, "--option", str(option),
        ]
    else:
        raise FileNotFoundError(f"ブリッジが見つかりません: {CSHARP_BRIDGE} も {PYTHON32} も存在しません")

    logger.info(f"ブリッジ起動: {' '.join(cmd)}")
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)


def _pipe_reader(proc: subprocess.Popen, q: queue.Queue, stats: dict):
    """パイプからレコードを読み、パース後にキューに入れるスレッド"""
    import io
    # バッファ付きリーダー（デフォルト8KBのパイプバッファを128KBに拡張）
    reader = io.BufferedReader(proc.stdout, buffer_size=1048576)  # 128KB→1MBに拡大
    try:
        while True:
            header = reader.read(4)
            if len(header) < 4:
                break
            length = struct.unpack(">I", header)[0]
            if length == 0:
                break
            data = reader.read(length)
            if len(data) < length:
                break

            stats["read"] += 1
            record = parse_record(data)
            if record is None:
                stats["skipped"] += 1
                continue
            q.put(record)
    except Exception as e:
        logger.error(f"パイプ読取エラー: {e}")
    finally:
        q.put(_SENTINEL)


def run_sync(mode: str, dataspec: str, force_fromtime: str | None = None) -> None:
    """JV-Linkからデータを取得してDBに高速保存する"""
    option = OPTION_MAP.get(mode, 1)
    db = SessionLocal()

    try:
        # setupモードの再開: 前回のタイムスタンプがあればそこから再開
        if force_fromtime:
            fromtime = force_fromtime
            logger.info(f"fromtime強制指定: {fromtime}")
        else:
            fromtime = get_last_timestamp(db, dataspec)
        if mode == "setup" and fromtime == "19860101000000" and not force_fromtime:
            # DB内の最新日付があれば、その少し前から再開（重複はUPSERTで安全）
            latest = db.execute(
                __import__("sqlalchemy").text("SELECT max(race_date) FROM races")
            ).scalar()
            if latest:
                # 1ヶ月前から再開（安全マージン）
                from datetime import timedelta
                resume_date = latest - timedelta(days=30)
                fromtime = resume_date.strftime("%Y%m%d") + "000000"
                logger.info(f"途中再開: DB最新={latest}, 再開地点={fromtime}")
        logger.info(f"同期開始: dataspec={dataspec}, mode={mode}, fromtime={fromtime}")

        cache = preload_cache(db)
        buffer = RecordBuffer(batch_size=BATCH_SIZE)
        record_q: queue.Queue = queue.Queue(maxsize=QUEUE_SIZE)
        stats = {"read": 0, "skipped": 0}

        # ブリッジ起動
        proc = _start_bridge(dataspec, fromtime, option)

        # stderr転送スレッド
        def forward_stderr():
            for line in proc.stderr:
                sys.stderr.buffer.write(line)
                sys.stderr.buffer.flush()
        threading.Thread(target=forward_stderr, daemon=True).start()

        # パイプ読取スレッド（パース含む）
        reader = threading.Thread(target=_pipe_reader, args=(proc, record_q, stats), daemon=True)
        reader.start()

        # メインスレッド: キューからレコードを取得してDB書き込み
        saved_total = 0
        start_time = time.time()
        last_log_time = start_time
        last_commit_count = 0
        last_flush_time = start_time

        while True:
            try:
                record = record_q.get(timeout=1.0)
            except queue.Empty:
                # タイムアウト — 時間ベースフラッシュ
                now = time.time()
                if now - last_flush_time >= 10.0:
                    s, sk = flush_in_order(db, buffer, cache)
                    if s > 0:
                        saved_total += s
                        stats["skipped"] += sk
                        db.commit()
                        last_commit_count = saved_total
                    last_flush_time = now
                if now - last_log_time >= 5.0:
                    elapsed = now - start_time
                    rate = saved_total / elapsed if elapsed > 0 else 0
                    logger.info(f"  保存: {saved_total:,}件 / 読出: {stats['read']:,}件 / {rate:.0f}件/秒")
                    last_log_time = now
                continue

            if record is _SENTINEL:
                break

            full_type = buffer.add(record)
            if full_type:
                s, sk = flush_in_order(db, buffer, cache)
                saved_total += s
                stats["skipped"] += sk
                last_flush_time = time.time()

            # 定期commit
            if saved_total - last_commit_count >= COMMIT_INTERVAL:
                db.commit()
                last_commit_count = saved_total

            now = time.time()
            if now - last_log_time >= 5.0:
                elapsed = now - start_time
                rate = saved_total / elapsed if elapsed > 0 else 0
                logger.info(f"  保存: {saved_total:,}件 / 読出: {stats['read']:,}件 / {rate:.0f}件/秒")
                last_log_time = now

        # 残りフラッシュ
        remaining = buffer.take_all()
        for rtype in FLUSH_ORDER:
            batch = remaining.pop(rtype, [])
            if batch:
                saver = _BULK_SAVERS.get(rtype)
                if saver:
                    s, sk = saver(db, batch, cache)
                    saved_total += s
                    stats["skipped"] += sk
        for batch in remaining.values():
            stats["skipped"] += len(batch)

        db.commit()

        # クリーンアップ
        reader.join(timeout=10)
        proc.stdout.close()
        proc.wait()

        elapsed = time.time() - start_time
        rate = saved_total / elapsed if elapsed > 0 else 0
        logger.info(
            f"同期完了: 保存={saved_total:,}件, スキップ={stats['skipped']:,}件, "
            f"時間={elapsed:.1f}秒, 速度={rate:.0f}件/秒"
        )

        # 全モードでタイムスタンプを保存（setupでも途中再開に使う）
        from datetime import datetime
        new_ts = datetime.now().strftime("%Y%m%d%H%M%S")
        update_last_timestamp(db, dataspec, new_ts)
        logger.info(f"タイムスタンプ保存: {new_ts}")

    except Exception as e:
        db.rollback()
        logger.error(f"エラー: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()


def run_rt_odds(race_key: str) -> None:
    """JVRTOpenで0B31（単複オッズ）を取得し、race_entries.odds_winを直接更新する"""
    import io

    env = os.environ.copy()
    # JV-Link設定はレジストリから自動読取させる
    if settings.jvlink_save_path:
        env["JVLINK_SAVE_PATH"] = settings.jvlink_save_path

    cmd = [str(CSHARP_BRIDGE), "--rt", "--dataspec", "0B31", "--rtkey", race_key]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

    try:
        stdout, _ = proc.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        logger.warning(f"  0B31 タイムアウト: {race_key}")
        return

    if len(stdout) < 8:
        return

    length = struct.unpack(">I", stdout[0:4])[0]
    if length == 0:
        return
    data = stdout[4:4+length]

    try:
        raw = data.decode("cp932", errors="replace")
    except:
        return

    if raw[0:2] != "O1":
        return

    # 0B31フォーマット:
    # pos 0-26: 共通ヘッダー（27バイト）
    # pos 27-42: 拡張ヘッダー（16バイト）
    # pos 43-: 単勝オッズ（各8バイト × 18スロット）
    #   馬番(2) + オッズ×10(4) + 人気(2) = 8バイト
    # pos 43+18*8=187-: 複勝オッズ（各8バイト × 18スロット）
    #   馬番(2) + 複勝最低オッズ×10(4) + 複勝最高オッズ×10(?)

    WIN_START = 43
    ENTRY_SIZE = 8  # 馬番(2)+odds×10(4)+pop(2)
    MAX_HORSES = 18

    entries = []
    for i in range(MAX_HORSES):
        pos = WIN_START + i * ENTRY_SIZE
        if pos + ENTRY_SIZE > len(raw):
            break
        chunk = raw[pos:pos + ENTRY_SIZE]
        num_s = chunk[0:2].strip()
        odds_s = chunk[2:6].strip()
        pop_s = chunk[6:8].strip()
        if not num_s or not odds_s:
            continue
        try:
            num = int(num_s)
            odds = int(odds_s) / 10.0
            pop = int(pop_s) if pop_s.isdigit() else 0
            if num > 0 and odds > 0:
                entries.append({"horse_num": num, "odds_win": odds, "popularity": pop})
        except ValueError:
            continue

    if not entries:
        return

    # DBに直接更新
    db = SessionLocal()
    try:
        from sqlalchemy import text as sql_text
        for e in entries:
            db.execute(sql_text("""
                UPDATE race_entries re SET odds_win = :odds, popularity = :pop
                FROM races r
                WHERE r.id = re.race_id AND r.race_key = :rk AND re.horse_num = :hn
            """), {"odds": e["odds_win"], "pop": e["popularity"], "rk": race_key, "hn": e["horse_num"]})
        db.commit()
        logger.info(f"  0B31 odds更新: {race_key} ({len(entries)}頭)")
    finally:
        db.close()


def run_rt_sync(dataspec: str = "0B15", rtkey: str | None = None) -> None:
    """JVRTOpenでリアルタイムデータを取得してDBに保存する"""
    db = SessionLocal()
    try:
        if not rtkey:
            from datetime import date
            rtkey = date.today().strftime("%Y%m%d")

        logger.info(f"リアルタイム同期開始: dataspec={dataspec}, key={rtkey}")

        env = os.environ.copy()
        if settings.jvlink_service_key:
            env["JVLINK_SERVICE_KEY"] = settings.jvlink_service_key
        if settings.jvlink_software_id:
            env["JVLINK_SOFTWARE_ID"] = settings.jvlink_software_id
        if settings.jvlink_save_path:
            env["JVLINK_SAVE_PATH"] = settings.jvlink_save_path

        cmd = [
            str(CSHARP_BRIDGE),
            "--rt", "--dataspec", dataspec, "--rtkey", rtkey,
        ]
        logger.info(f"ブリッジ起動: {' '.join(cmd)}")
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

        # stderr転送
        def forward_stderr():
            for line in proc.stderr:
                sys.stderr.buffer.write(line)
                sys.stderr.buffer.flush()
        threading.Thread(target=forward_stderr, daemon=True).start()

        # パイプ読取
        import io
        reader = io.BufferedReader(proc.stdout, buffer_size=1048576)
        cache = preload_cache(db)
        buffer = RecordBuffer(batch_size=BATCH_SIZE)
        saved_total = 0
        read_total = 0
        skipped = 0

        while True:
            header = reader.read(4)
            if len(header) < 4:
                break
            length = struct.unpack(">I", header)[0]
            if length == 0:
                break
            data = reader.read(length)
            if len(data) < length:
                break

            read_total += 1
            record = parse_record(data)
            if record is None:
                skipped += 1
                continue

            rtype = record.get("_record_type")
            ready = buffer.add(record)
            if ready:
                s, sk = flush_in_order(db, buffer, cache)
                saved_total += s
                skipped += sk

        # 残りフラッシュ
        for rtype in FLUSH_ORDER:
            recs = buffer.take(rtype)
            if recs:
                ready_buf = RecordBuffer(batch_size=len(recs) + 1)
                for r in recs:
                    ready_buf.add(r)
                s2, sk2 = flush_in_order(db, ready_buf, cache)
                saved_total += s2
                skipped += sk2
        db.commit()

        proc.wait()

        # O1レコード（0B31）の場合、odds_snapshotsからrace_entries.odds_winを更新
        if dataspec in ("0B31", "0B30"):
            from sqlalchemy import text as sql_text
            updated = db.execute(sql_text("""
                UPDATE race_entries re
                SET odds_win = os.odds_win,
                    odds_place_min = os.odds_place_min,
                    odds_place_max = os.odds_place_max
                FROM odds_snapshots os
                WHERE os.entry_id = re.id
                  AND os.odds_win > 0
                  AND (re.odds_win = 0 OR re.odds_win IS NULL
                       OR os.snapshot_type > COALESCE(
                           (SELECT max(os2.snapshot_type) FROM odds_snapshots os2
                            WHERE os2.entry_id = re.id AND os2.snapshot_type < os.snapshot_type), 0))
            """))
            db.commit()
            logger.info(f"odds_win更新: {updated.rowcount}件")

        logger.info(f"リアルタイム同期完了: 読取={read_total}, 保存={saved_total}, スキップ={skipped}")

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="JV-Link データ同期（高速バルク版）")
    parser.add_argument("--mode", choices=["normal", "weekly", "setup"], default="normal")
    parser.add_argument("--dataspec", default=DEFAULT_DATASPEC)
    parser.add_argument("--fromtime", default=None, help="fromtimeを強制指定（例: 19860101000000）")
    parser.add_argument("--rt", action="store_true", help="リアルタイムモード（JVRTOpen使用）")
    parser.add_argument("--rtkey", default=None, help="リアルタイムキー（YYYYMMDD or レースキー）")
    args = parser.parse_args()

    if args.rt:
        run_rt_sync(args.dataspec, args.rtkey)
    else:
        run_sync(args.mode, args.dataspec, force_fromtime=args.fromtime)


if __name__ == "__main__":
    main()
