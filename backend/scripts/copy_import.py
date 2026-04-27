"""
COPY方式 高速データ取込スクリプト

従来のバルクUPSERT方式（500件/秒）に対し、
PostgreSQL COPY + ステージングテーブル方式で 10万件/秒以上を実現する。

処理フロー:
  1. JVLinkBridge.exe → パイプ読取 → parse_record() → レコードタイプ別CSV書出
  2. UNLOGGED ステージングテーブル作成
  3. COPY IN でCSV→ステージング（psycopg2 copy_expert）
  4. ステージング→本テーブルへマージ（INSERT...ON CONFLICT + JOINでFK解決）
  5. 既存データのhorse_id/jockey_id/trainer_id 一括紐付け修正
  6. ステージングテーブル DROP

使い方:
  # 全レコード取込（JV-Link→CSV→COPY→マージ）
  python scripts/copy_import.py --mode setup --dataspec RACE

  # 既存データのID紐付け修正のみ（JV-Link不使用）
  python scripts/copy_import.py --fix-links-only

  # CSVファイルから取込（JV-Link不使用、既存CSV再利用）
  python scripts/copy_import.py --csv-only
"""
import sys
import os
import io
import csv
import argparse
import logging
import struct
import subprocess
import time
import threading
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.services.jv_parser import parse_record

_LOG_DIR = Path(__file__).parent.parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(_LOG_DIR / "copy_import.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# === パス定義 ===
CSHARP_BRIDGE = Path(__file__).parent.parent / "bridge" / "JVLinkBridge" / "bin" / "Release" / "net8.0-windows" / "JVLinkBridge.exe"
PYTHON32 = Path(os.environ.get(
    "PYTHON32_PATH",
    r"C:\Users\kizun\AppData\Local\Programs\Python\Python311-32\python.exe",
))
BRIDGE_SCRIPT = Path(__file__).parent / "jvlink_bridge.py"
STAGING_DIR = Path(__file__).parent.parent / "data" / "staging"
OPTION_MAP = {"normal": 1, "weekly": 2, "setup": 3}

# === CSV列定義（ステージングテーブルと一致させる） ===
RA_COLS = [
    "race_key", "race_date", "venue_code", "kai", "nichi", "race_num",
    "race_name", "race_name_sub", "race_name_short", "grade", "distance",
    "track_type", "track_dir", "horse_count", "weather", "track_cond",
    "condition_code", "is_female_only", "is_mixed", "is_handicap",
    "start_time", "prize_1st", "prize_2nd", "prize_3rd",
]

SE_COLS = [
    "race_key", "horse_num", "frame_num", "blood_reg_num", "horse_name",
    "sex", "age", "belong_region", "trainer_code", "jockey_code",
    "weight_carry", "prev_weight_carry", "blinker_code", "prev_jockey_code",
    "apprentice_code", "horse_weight", "weight_diff", "abnormal_code",
    "finish_order", "finish_time", "last_3f", "margin",
    "corner_1", "corner_2", "corner_3", "corner_4",
    "odds_win", "popularity",
]

UM_COLS = [
    "blood_reg_num", "name_kana", "name_eng", "birth_date", "sex",
    "coat_color", "father_name", "father_code", "mother_name", "mother_code",
    "mother_father", "mother_father_code", "producer_name", "area_name",
    "owner_name", "total_wins", "total_races", "total_earnings",
]

KS_COLS = [
    "jockey_code", "name_kanji", "name_kana", "birth_date", "belong_code",
    "total_1st", "total_2nd", "total_3rd", "total_races",
]

CH_COLS = [
    "trainer_code", "name_kanji", "name_kana", "belong_code",
    "total_1st", "total_races",
]

BT_COLS = ["breed_reg_num", "lineage_id", "lineage_name"]

HR_COLS = ["race_key", "bet_type", "combination", "payout", "popularity"]

# ラップは別テーブル
LAPS_COLS = ["race_key", "hallon_order", "lap_time"]

# 調教系
TRAINING_COLS = [
    "blood_reg_num", "training_date", "course_type", "distance",
    "lap_time", "last_3f", "last_1f", "rank",
]

# 馬体重
WH_COLS = ["race_key", "horse_num", "weight", "weight_diff"]

# オッズ
O1_COLS = [
    "race_key", "horse_num", "snapshot_type",
    "odds_win", "odds_place_min", "odds_place_max",
]

# レコードタイプ → (CSV列定義, ファイル名)
RECORD_CONFIG = {
    "RA": (RA_COLS, "ra.csv"),
    "SE": (SE_COLS, "se.csv"),
    "UM": (UM_COLS, "um.csv"),
    "KS": (KS_COLS, "ks.csv"),
    "CH": (CH_COLS, "ch.csv"),
    "BT": (BT_COLS, "bt.csv"),
    "HR": (HR_COLS, "hr.csv"),
    "HC": (TRAINING_COLS, "hc.csv"),
    "WC": (TRAINING_COLS, "wc.csv"),
    "WH": (WH_COLS, "wh.csv"),
    "O1": (O1_COLS, "o1.csv"),
}


def _val(v) -> str:
    """値をCSV用文字列に変換（Noneは空文字）"""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "t" if v else "f"
    return str(v)


# ====================================================================
# Phase 1: JV-Link → CSV書出
# ====================================================================

def _start_bridge(dataspec: str, fromtime: str, option: int) -> subprocess.Popen:
    """ブリッジプロセスを起動（sync_jvlink.pyと同一ロジック）"""
    env = os.environ.copy()
    if settings.jvlink_service_key:
        env["JVLINK_SERVICE_KEY"] = settings.jvlink_service_key
    if settings.jvlink_software_id:
        env["JVLINK_SOFTWARE_ID"] = settings.jvlink_software_id
    if settings.jvlink_save_path:
        env["JVLINK_SAVE_PATH"] = settings.jvlink_save_path

    if CSHARP_BRIDGE.exists():
        cmd = [
            str(CSHARP_BRIDGE),
            "--dataspec", dataspec, "--fromtime", fromtime, "--option", str(option),
        ]
    elif PYTHON32.exists():
        cmd = [
            str(PYTHON32), str(BRIDGE_SCRIPT),
            "--dataspec", dataspec, "--fromtime", fromtime, "--option", str(option),
        ]
    else:
        raise FileNotFoundError(f"ブリッジが見つかりません: {CSHARP_BRIDGE} も {PYTHON32} も存在しません")

    logger.info(f"ブリッジ起動: {' '.join(cmd)}")
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)


def _write_record_to_csv(record: dict, writers: dict, counters: dict):
    """パース済みレコードをCSVライターに書き出す"""
    rtype = record.get("_record_type")
    if rtype not in RECORD_CONFIG:
        return

    cols, _ = RECORD_CONFIG[rtype]

    if rtype == "HR":
        # HR: payoutsリストを展開して複数行に
        race_key = record.get("race_key", "")
        for p in record.get("payouts", []):
            row = [race_key, _val(p.get("bet_type")), _val(p.get("combination")),
                   _val(p.get("payout")), _val(p.get("popularity"))]
            writers["HR"].writerow(row)
            counters["HR"] = counters.get("HR", 0) + 1
    elif rtype == "O1":
        # O1: odds_entriesリストを展開
        race_key = record.get("race_key", "")
        snap_type = record.get("snapshot_type", "")
        for e in record.get("odds_entries", []):
            row = [race_key, _val(e.get("horse_num")), _val(snap_type),
                   _val(e.get("odds_win")), _val(e.get("odds_place_min")),
                   _val(e.get("odds_place_max"))]
            writers["O1"].writerow(row)
            counters["O1"] = counters.get("O1", 0) + 1
    elif rtype == "RA":
        # RA: メインレコード + ラップデータ
        row = [_val(record.get(c)) for c in cols]
        writers["RA"].writerow(row)
        counters["RA"] = counters.get("RA", 0) + 1
        # ラップを別CSVに書出
        race_key = record.get("race_key", "")
        for i, lap in enumerate(record.get("laps", []), start=1):
            if lap and lap > 0:
                writers["LAPS"].writerow([race_key, str(i), str(lap)])
                counters["LAPS"] = counters.get("LAPS", 0) + 1
    else:
        row = [_val(record.get(c)) for c in cols]
        writers[rtype].writerow(row)
        counters[rtype] = counters.get(rtype, 0) + 1


def phase1_jvlink_to_csv(dataspec: str, mode: str, fromtime: str | None) -> dict:
    """JV-Linkからレコードを読み、レコードタイプ別CSVに書出す"""
    option = OPTION_MAP.get(mode, 1)

    # fromtime決定
    if not fromtime:
        if mode == "setup":
            fromtime = "19860101000000"
        else:
            fromtime = (datetime.now().strftime("%Y%m%d") + "000000")
    logger.info(f"Phase1開始: dataspec={dataspec}, mode={mode}, fromtime={fromtime}")

    # ステージングディレクトリ作成
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    # CSVファイルオープン
    files = {}
    writers = {}
    counters = {}

    try:
        for rtype, (cols, fname) in RECORD_CONFIG.items():
            fp = open(STAGING_DIR / fname, "w", newline="", encoding="utf-8")
            files[rtype] = fp
            writers[rtype] = csv.writer(fp)

        # ラップ用CSV
        fp_laps = open(STAGING_DIR / "laps.csv", "w", newline="", encoding="utf-8")
        files["LAPS"] = fp_laps
        writers["LAPS"] = csv.writer(fp_laps)

        # WE（調教タイム）はHC/WCと同じフォーマットなのでwc.csvに追記
        # → 別CSVにする
        fp_we = open(STAGING_DIR / "we.csv", "w", newline="", encoding="utf-8")
        files["WE"] = fp_we
        writers["WE"] = csv.writer(fp_we)

        # ブリッジ起動
        proc = _start_bridge(dataspec, fromtime, option)

        # stderr転送
        def forward_stderr():
            for line in proc.stderr:
                sys.stderr.buffer.write(line)
                sys.stderr.buffer.flush()
        threading.Thread(target=forward_stderr, daemon=True).start()

        # パイプ読取（メインスレッドで実行 — CSVへの書出は高速なのでキュー不要）
        reader = io.BufferedReader(proc.stdout, buffer_size=1048576)
        total_read = 0
        total_skipped = 0
        start_time = time.time()
        last_log = start_time

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

            total_read += 1
            record = parse_record(data)
            if record is None:
                total_skipped += 1
                continue

            rtype = record.get("_record_type")

            # WEレコードはtraining用CSVに書出
            if rtype == "WE":
                for c in TRAINING_COLS:
                    pass  # WEのフィールドはTRAINING_COLSと一致
                row = [_val(record.get(c)) for c in TRAINING_COLS]
                writers["WE"].writerow(row)
                counters["WE"] = counters.get("WE", 0) + 1
            else:
                _write_record_to_csv(record, writers, counters)

            # 進捗ログ
            now = time.time()
            if now - last_log >= 10.0:
                elapsed = now - start_time
                rate = total_read / elapsed if elapsed > 0 else 0
                logger.info(f"  読取中: {total_read:,}件 ({rate:.0f}件/秒) "
                            f"スキップ={total_skipped:,} | "
                            + " ".join(f"{k}={v:,}" for k, v in sorted(counters.items())))
                last_log = now

        proc.wait()
        elapsed = time.time() - start_time

        logger.info(f"Phase1完了: {total_read:,}件読取 ({total_skipped:,}スキップ) "
                    f"所要={elapsed:.1f}秒 ({total_read / elapsed:.0f}件/秒)")
        for k, v in sorted(counters.items()):
            logger.info(f"  {k}: {v:,}件")

        return counters

    finally:
        for fp in files.values():
            fp.close()


# ====================================================================
# Phase 2: CSV → ステージングテーブル → 本テーブルマージ
# ====================================================================

def _get_raw_conn():
    """psycopg2の生接続を取得（COPY用）"""
    import psycopg2
    url = settings.database_url
    # SQLAlchemy URLをpsycopg2用に変換
    if url.startswith("postgresql+psycopg2://"):
        url = url.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(url)
    conn.autocommit = False
    return conn


def phase2_csv_to_db():
    """CSVファイルをステージングテーブル経由で本テーブルにマージする"""
    conn = _get_raw_conn()
    cur = conn.cursor()

    try:
        # パフォーマンス設定
        cur.execute("SET synchronous_commit = off")
        cur.execute("SET work_mem = '256MB'")
        cur.execute("SET maintenance_work_mem = '512MB'")

        logger.info("Phase2開始: ステージングテーブル作成 → COPY → マージ")

        # --- ステージングテーブル作成 ---
        _create_staging_tables(cur)
        conn.commit()

        # --- COPY IN ---
        _copy_csvs_to_staging(cur)
        conn.commit()
        logger.info("COPY完了")

        # --- マージ（順序: UM→KS→CH→BT→RA→LAPS→SE→HR→O1→HC/WC/WE→WH） ---
        _merge_um(cur)
        conn.commit()
        _merge_ks(cur)
        conn.commit()
        _merge_ch(cur)
        conn.commit()
        _merge_bt(cur)
        conn.commit()
        _merge_ra(cur)
        conn.commit()
        _merge_laps(cur)
        conn.commit()
        _merge_se(cur)
        conn.commit()
        _merge_hr(cur)
        conn.commit()
        _merge_o1(cur)
        conn.commit()
        _merge_training(cur)
        conn.commit()
        _merge_wh(cur)
        conn.commit()

        logger.info("マージ完了")

        # --- ステージングテーブル削除 ---
        _drop_staging_tables(cur)
        conn.commit()

        logger.info("Phase2完了")

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def _create_staging_tables(cur):
    """UNLOGGED ステージングテーブルを作成（制約なし、インデックスなし）"""
    ddl = """
    DROP TABLE IF EXISTS stg_ra, stg_se, stg_um, stg_ks, stg_ch, stg_bt,
                         stg_hr, stg_laps, stg_training, stg_wh, stg_o1 CASCADE;

    CREATE UNLOGGED TABLE stg_ra (
        race_key TEXT, race_date DATE, venue_code TEXT, kai INT, nichi INT,
        race_num INT, race_name TEXT, race_name_sub TEXT, race_name_short TEXT,
        grade INT, distance INT, track_type INT, track_dir INT,
        horse_count INT, weather INT, track_cond INT, condition_code INT,
        is_female_only TEXT, is_mixed TEXT, is_handicap TEXT,
        start_time TEXT, prize_1st INT, prize_2nd INT, prize_3rd INT
    );

    CREATE UNLOGGED TABLE stg_se (
        race_key TEXT, horse_num INT, frame_num INT, blood_reg_num TEXT,
        horse_name TEXT, sex INT, age INT, belong_region INT,
        trainer_code TEXT, jockey_code TEXT, weight_carry NUMERIC,
        prev_weight_carry NUMERIC, blinker_code INT, prev_jockey_code TEXT,
        apprentice_code INT, horse_weight INT, weight_diff INT,
        abnormal_code INT, finish_order INT, finish_time INT, last_3f INT,
        margin INT, corner_1 INT, corner_2 INT, corner_3 INT, corner_4 INT,
        odds_win NUMERIC, popularity INT
    );

    CREATE UNLOGGED TABLE stg_um (
        blood_reg_num TEXT, name_kana TEXT, name_eng TEXT, birth_date TEXT,
        sex INT, coat_color INT, father_name TEXT, father_code TEXT,
        mother_name TEXT, mother_code TEXT, mother_father TEXT,
        mother_father_code TEXT, producer_name TEXT, area_name TEXT,
        owner_name TEXT, total_wins INT, total_races INT, total_earnings INT
    );

    CREATE UNLOGGED TABLE stg_ks (
        jockey_code TEXT, name_kanji TEXT, name_kana TEXT, birth_date TEXT,
        belong_code INT, total_1st INT, total_2nd INT, total_3rd INT,
        total_races INT
    );

    CREATE UNLOGGED TABLE stg_ch (
        trainer_code TEXT, name_kanji TEXT, name_kana TEXT,
        belong_code INT, total_1st INT, total_races INT
    );

    CREATE UNLOGGED TABLE stg_bt (
        breed_reg_num TEXT, lineage_id TEXT, lineage_name TEXT
    );

    CREATE UNLOGGED TABLE stg_hr (
        race_key TEXT, bet_type INT, combination TEXT, payout INT, popularity INT
    );

    CREATE UNLOGGED TABLE stg_laps (
        race_key TEXT, hallon_order INT, lap_time INT
    );

    CREATE UNLOGGED TABLE stg_training (
        blood_reg_num TEXT, training_date DATE, course_type INT,
        distance INT, lap_time INT, last_3f INT, last_1f INT, rank TEXT
    );

    CREATE UNLOGGED TABLE stg_wh (
        race_key TEXT, horse_num INT, weight INT, weight_diff INT
    );

    CREATE UNLOGGED TABLE stg_o1 (
        race_key TEXT, horse_num INT, snapshot_type INT,
        odds_win NUMERIC, odds_place_min NUMERIC, odds_place_max NUMERIC
    );
    """
    cur.execute(ddl)
    logger.info("ステージングテーブル作成完了")


def _copy_csvs_to_staging(cur):
    """CSVファイルをCOPY INでステージングテーブルに高速ロード"""
    copy_map = {
        "stg_ra": "ra.csv",
        "stg_se": "se.csv",
        "stg_um": "um.csv",
        "stg_ks": "ks.csv",
        "stg_ch": "ch.csv",
        "stg_bt": "bt.csv",
        "stg_hr": "hr.csv",
        "stg_laps": "laps.csv",
        "stg_wh": "wh.csv",
        "stg_o1": "o1.csv",
    }
    # 調教系: hc.csv, wc.csv, we.csv → stg_training に統合
    training_files = ["hc.csv", "wc.csv", "we.csv"]

    for table, fname in copy_map.items():
        fpath = STAGING_DIR / fname
        if not fpath.exists() or fpath.stat().st_size == 0:
            logger.info(f"  {fname}: スキップ（ファイルなしまたは空）")
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            cur.copy_expert(f"COPY {table} FROM STDIN WITH (FORMAT csv, NULL '')", f)
        # 行数確認
        cur.execute(f"SELECT count(*) FROM {table}")
        cnt = cur.fetchone()[0]
        logger.info(f"  {fname} → {table}: {cnt:,}件")

    # 調教系ファイルを統合COPY
    for fname in training_files:
        fpath = STAGING_DIR / fname
        if not fpath.exists() or fpath.stat().st_size == 0:
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            cur.copy_expert("COPY stg_training FROM STDIN WITH (FORMAT csv, NULL '')", f)
        logger.info(f"  {fname} → stg_training にCOPY完了")

    cur.execute("SELECT count(*) FROM stg_training")
    cnt = cur.fetchone()[0]
    logger.info(f"  stg_training 合計: {cnt:,}件")


def _merge_um(cur):
    """馬マスタ: stg_um → horses"""
    sql = """
    INSERT INTO horses (
        blood_reg_num, name_kana, name_eng, birth_date, sex, coat_color,
        father_name, father_code, mother_name, mother_code,
        mother_father, mother_father_code, producer_name, area_name,
        owner_name, total_wins, total_races, total_earnings
    )
    SELECT DISTINCT ON (blood_reg_num)
        blood_reg_num, name_kana, name_eng,
        CASE WHEN birth_date ~ '^\d{4}-\d{2}-\d{2}$' AND birth_date > '0000-00-00' THEN birth_date::date ELSE NULL END,
        sex, coat_color,
        father_name, father_code, mother_name, mother_code,
        mother_father, mother_father_code, producer_name, area_name,
        owner_name, COALESCE(total_wins, 0), COALESCE(total_races, 0),
        COALESCE(total_earnings, 0)
    FROM stg_um
    WHERE blood_reg_num IS NOT NULL AND blood_reg_num != ''
    ORDER BY blood_reg_num
    ON CONFLICT (blood_reg_num) DO UPDATE SET
        name_kana = EXCLUDED.name_kana,
        name_eng = EXCLUDED.name_eng,
        owner_name = EXCLUDED.owner_name,
        total_wins = EXCLUDED.total_wins,
        total_races = EXCLUDED.total_races,
        total_earnings = EXCLUDED.total_earnings,
        updated_at = now()
    """
    cur.execute(sql)
    logger.info(f"  horses マージ: {cur.rowcount:,}件")


def _merge_ks(cur):
    """騎手マスタ: stg_ks → jockeys"""
    sql = """
    INSERT INTO jockeys (
        jockey_code, name_kanji, name_kana, birth_date, belong_code,
        total_1st, total_2nd, total_3rd, total_races
    )
    SELECT DISTINCT ON (jockey_code)
        jockey_code, name_kanji, name_kana,
        CASE WHEN birth_date ~ '^\d{4}-\d{2}-\d{2}$' AND birth_date > '0000-00-00' THEN birth_date::date ELSE NULL END,
        belong_code,
        COALESCE(total_1st, 0), COALESCE(total_2nd, 0),
        COALESCE(total_3rd, 0), COALESCE(total_races, 0)
    FROM stg_ks
    WHERE jockey_code IS NOT NULL AND jockey_code != ''
    ORDER BY jockey_code
    ON CONFLICT (jockey_code) DO UPDATE SET
        name_kanji = EXCLUDED.name_kanji,
        total_1st = EXCLUDED.total_1st,
        total_2nd = EXCLUDED.total_2nd,
        total_3rd = EXCLUDED.total_3rd,
        total_races = EXCLUDED.total_races,
        updated_at = now()
    """
    cur.execute(sql)
    logger.info(f"  jockeys マージ: {cur.rowcount:,}件")


def _merge_ch(cur):
    """調教師マスタ: stg_ch → trainers"""
    sql = """
    INSERT INTO trainers (
        trainer_code, name_kanji, name_kana, belong_code,
        total_1st, total_races
    )
    SELECT DISTINCT ON (trainer_code)
        trainer_code, name_kanji, name_kana, belong_code,
        COALESCE(total_1st, 0), COALESCE(total_races, 0)
    FROM stg_ch
    WHERE trainer_code IS NOT NULL AND trainer_code != ''
    ORDER BY trainer_code
    ON CONFLICT (trainer_code) DO UPDATE SET
        name_kanji = EXCLUDED.name_kanji,
        total_1st = EXCLUDED.total_1st,
        total_races = EXCLUDED.total_races,
        updated_at = now()
    """
    cur.execute(sql)
    logger.info(f"  trainers マージ: {cur.rowcount:,}件")


def _merge_bt(cur):
    """系統情報: stg_bt → pedigree_lineages"""
    sql = """
    INSERT INTO pedigree_lineages (breed_reg_num, lineage_id, lineage_name)
    SELECT DISTINCT ON (breed_reg_num)
        breed_reg_num, lineage_id, lineage_name
    FROM stg_bt
    WHERE breed_reg_num IS NOT NULL AND breed_reg_num != ''
    ORDER BY breed_reg_num
    ON CONFLICT (breed_reg_num) DO UPDATE SET
        lineage_id = EXCLUDED.lineage_id,
        lineage_name = EXCLUDED.lineage_name
    """
    cur.execute(sql)
    logger.info(f"  pedigree_lineages マージ: {cur.rowcount:,}件")


def _merge_ra(cur):
    """レース: stg_ra → races"""
    sql = """
    INSERT INTO races (
        race_key, race_date, venue_code, kai, nichi, race_num,
        race_name, race_name_sub, grade, distance,
        track_type, track_dir, horse_count, weather, track_cond,
        condition_code, is_female_only, is_mixed, is_handicap, is_special,
        start_time, prize_1st, prize_2nd, prize_3rd
    )
    SELECT DISTINCT ON (race_key)
        race_key, race_date, venue_code, kai, nichi, race_num,
        race_name, race_name_sub, grade, distance,
        track_type, track_dir, horse_count, weather, track_cond,
        condition_code,
        CASE WHEN is_female_only = 't' THEN true ELSE false END,
        CASE WHEN is_mixed = 't' THEN true ELSE false END,
        CASE WHEN is_handicap = 't' THEN true ELSE false END,
        false,
        start_time, prize_1st, prize_2nd, prize_3rd
    FROM stg_ra
    WHERE race_key IS NOT NULL AND race_key != ''
    ORDER BY race_key
    ON CONFLICT (race_key) DO UPDATE SET
        race_name = EXCLUDED.race_name,
        grade = EXCLUDED.grade,
        horse_count = EXCLUDED.horse_count,
        weather = EXCLUDED.weather,
        track_cond = EXCLUDED.track_cond,
        start_time = EXCLUDED.start_time,
        prize_1st = EXCLUDED.prize_1st,
        prize_2nd = EXCLUDED.prize_2nd,
        prize_3rd = EXCLUDED.prize_3rd,
        updated_at = now()
    """
    cur.execute(sql)
    logger.info(f"  races マージ: {cur.rowcount:,}件")


def _merge_laps(cur):
    """ラップ: stg_laps → race_laps（race_keyからrace_idをJOINで解決）"""
    sql = """
    INSERT INTO race_laps (race_id, hallon_order, lap_time)
    SELECT r.id, s.hallon_order, s.lap_time
    FROM (
        SELECT DISTINCT ON (race_key, hallon_order) race_key, hallon_order, lap_time
        FROM stg_laps
        WHERE lap_time IS NOT NULL AND lap_time > 0
        ORDER BY race_key, hallon_order
    ) s
    JOIN races r ON r.race_key = s.race_key
    ON CONFLICT ON CONSTRAINT uq_lap DO UPDATE SET
        lap_time = EXCLUDED.lap_time
    """
    cur.execute(sql)
    logger.info(f"  race_laps マージ: {cur.rowcount:,}件")


def _merge_se(cur):
    """出走馬: stg_se → race_entries（JOINでrace_id/horse_id/jockey_id/trainer_idを一括解決）"""
    sql = """
    INSERT INTO race_entries (
        race_id, horse_num, frame_num, blood_reg_num, sex, age,
        belong_region, trainer_code, jockey_code,
        weight_carry, prev_weight_carry, blinker_code, prev_jockey_code,
        apprentice_code, horse_weight, weight_diff, abnormal_code,
        finish_order, finish_time, last_3f, margin,
        corner_1, corner_2, corner_3, corner_4,
        odds_win, popularity,
        horse_id, jockey_id, trainer_id
    )
    SELECT
        r.id,
        s.horse_num, s.frame_num, s.blood_reg_num, s.sex, s.age,
        s.belong_region, s.trainer_code, s.jockey_code,
        s.weight_carry, s.prev_weight_carry, s.blinker_code, s.prev_jockey_code,
        s.apprentice_code, s.horse_weight, s.weight_diff, s.abnormal_code,
        s.finish_order, s.finish_time, s.last_3f, s.margin,
        s.corner_1, s.corner_2, s.corner_3, s.corner_4,
        s.odds_win, s.popularity,
        h.id, j.id, t.id
    FROM (
        SELECT DISTINCT ON (race_key, horse_num) *
        FROM stg_se
        ORDER BY race_key, horse_num
    ) s
    JOIN races r ON r.race_key = s.race_key
    LEFT JOIN horses h ON h.blood_reg_num = s.blood_reg_num
    LEFT JOIN jockeys j ON j.jockey_code = s.jockey_code
    LEFT JOIN trainers t ON t.trainer_code = s.trainer_code
    ON CONFLICT ON CONSTRAINT uq_race_horse DO UPDATE SET
        horse_id = EXCLUDED.horse_id,
        jockey_id = EXCLUDED.jockey_id,
        trainer_id = EXCLUDED.trainer_id,
        finish_order = EXCLUDED.finish_order,
        finish_time = EXCLUDED.finish_time,
        last_3f = EXCLUDED.last_3f,
        odds_win = EXCLUDED.odds_win,
        popularity = EXCLUDED.popularity,
        corner_1 = EXCLUDED.corner_1,
        corner_2 = EXCLUDED.corner_2,
        corner_3 = EXCLUDED.corner_3,
        corner_4 = EXCLUDED.corner_4,
        weight_carry = EXCLUDED.weight_carry,
        prev_weight_carry = EXCLUDED.prev_weight_carry,
        horse_weight = EXCLUDED.horse_weight,
        weight_diff = EXCLUDED.weight_diff,
        blinker_code = EXCLUDED.blinker_code,
        prev_jockey_code = EXCLUDED.prev_jockey_code,
        apprentice_code = EXCLUDED.apprentice_code,
        belong_region = EXCLUDED.belong_region,
        blood_reg_num = EXCLUDED.blood_reg_num,
        jockey_code = EXCLUDED.jockey_code,
        trainer_code = EXCLUDED.trainer_code,
        updated_at = now()
    """
    cur.execute(sql)
    logger.info(f"  race_entries マージ: {cur.rowcount:,}件")


def _merge_hr(cur):
    """払戻: stg_hr → payouts"""
    sql = """
    INSERT INTO payouts (race_id, bet_type, combination, payout, popularity)
    SELECT r.id, s.bet_type, s.combination, s.payout, s.popularity
    FROM (
        SELECT DISTINCT ON (race_key, bet_type, combination) *
        FROM stg_hr
        ORDER BY race_key, bet_type, combination
    ) s
    JOIN races r ON r.race_key = s.race_key
    ON CONFLICT ON CONSTRAINT uq_payout DO UPDATE SET
        payout = EXCLUDED.payout,
        popularity = EXCLUDED.popularity
    """
    cur.execute(sql)
    logger.info(f"  payouts マージ: {cur.rowcount:,}件")


def _merge_o1(cur):
    """オッズ: stg_o1 → odds_snapshots（entry_idをJOINで解決）"""
    sql = """
    INSERT INTO odds_snapshots (entry_id, snapshot_type, odds_win, odds_place_min, odds_place_max)
    SELECT re.id, s.snapshot_type, s.odds_win, s.odds_place_min, s.odds_place_max
    FROM (
        SELECT DISTINCT ON (race_key, horse_num, snapshot_type) *
        FROM stg_o1
        WHERE odds_win IS NOT NULL
        ORDER BY race_key, horse_num, snapshot_type
    ) s
    JOIN races r ON r.race_key = s.race_key
    JOIN race_entries re ON re.race_id = r.id AND re.horse_num = s.horse_num
    ON CONFLICT ON CONSTRAINT uq_odds_snapshot DO UPDATE SET
        odds_win = EXCLUDED.odds_win,
        odds_place_min = EXCLUDED.odds_place_min,
        odds_place_max = EXCLUDED.odds_place_max
    """
    cur.execute(sql)
    logger.info(f"  odds_snapshots マージ: {cur.rowcount:,}件")


def _merge_training(cur):
    """調教: stg_training → training_times（horse_idをJOINで解決）"""
    # training_timesにはON CONFLICT制約がないのでINSERTのみ
    # 重複を避けるため、既存データと照合
    sql = """
    INSERT INTO training_times (
        horse_id, training_date, course_type, distance,
        lap_time, last_3f, last_1f, rank
    )
    SELECT h.id, s.training_date, s.course_type, s.distance,
           s.lap_time, s.last_3f, s.last_1f, s.rank
    FROM stg_training s
    JOIN horses h ON h.blood_reg_num = s.blood_reg_num
    WHERE s.training_date IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM training_times tt
          WHERE tt.horse_id = h.id
            AND tt.training_date = s.training_date
            AND tt.course_type = s.course_type
            AND COALESCE(tt.distance, 0) = COALESCE(s.distance, 0)
      )
    """
    cur.execute(sql)
    logger.info(f"  training_times マージ: {cur.rowcount:,}件")


def _merge_wh(cur):
    """馬体重: stg_wh → horse_weights"""
    sql = """
    INSERT INTO horse_weights (race_id, horse_num, weight, weight_diff)
    SELECT r.id, s.horse_num, s.weight, s.weight_diff
    FROM (
        SELECT DISTINCT ON (race_key, horse_num) *
        FROM stg_wh
        ORDER BY race_key, horse_num
    ) s
    JOIN races r ON r.race_key = s.race_key
    ON CONFLICT ON CONSTRAINT uq_weight_race_horse DO UPDATE SET
        weight = EXCLUDED.weight,
        weight_diff = EXCLUDED.weight_diff
    """
    cur.execute(sql)
    logger.info(f"  horse_weights マージ: {cur.rowcount:,}件")


def _drop_staging_tables(cur):
    """ステージングテーブルを削除"""
    cur.execute("""
        DROP TABLE IF EXISTS stg_ra, stg_se, stg_um, stg_ks, stg_ch, stg_bt,
                             stg_hr, stg_laps, stg_training, stg_wh, stg_o1 CASCADE
    """)
    logger.info("ステージングテーブル削除完了")


# ====================================================================
# Phase 3: 既存データID紐付け修正
# ====================================================================

def phase3_fix_links():
    """既存race_entriesのhorse_id/jockey_id/trainer_idを一括修正"""
    conn = _get_raw_conn()
    cur = conn.cursor()

    try:
        logger.info("Phase3開始: 既存データID紐付け修正")

        # horse_id紐付け
        cur.execute("""
            UPDATE race_entries re SET horse_id = h.id
            FROM horses h
            WHERE re.blood_reg_num = h.blood_reg_num
              AND re.horse_id IS NULL
              AND re.blood_reg_num IS NOT NULL
              AND re.blood_reg_num != ''
        """)
        logger.info(f"  horse_id紐付け: {cur.rowcount:,}件")
        conn.commit()

        # jockey_id紐付け
        cur.execute("""
            UPDATE race_entries re SET jockey_id = j.id
            FROM jockeys j
            WHERE re.jockey_code = j.jockey_code
              AND re.jockey_id IS NULL
              AND re.jockey_code IS NOT NULL
              AND re.jockey_code != ''
        """)
        logger.info(f"  jockey_id紐付け: {cur.rowcount:,}件")
        conn.commit()

        # trainer_id紐付け
        cur.execute("""
            UPDATE race_entries re SET trainer_id = t.id
            FROM trainers t
            WHERE re.trainer_code = t.trainer_code
              AND re.trainer_id IS NULL
              AND re.trainer_code IS NOT NULL
              AND re.trainer_code != ''
        """)
        logger.info(f"  trainer_id紐付け: {cur.rowcount:,}件")
        conn.commit()

        # 紐付け結果確認
        cur.execute("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE horse_id IS NOT NULL) AS horse_linked,
                COUNT(*) FILTER (WHERE horse_id IS NULL AND blood_reg_num IS NOT NULL AND blood_reg_num != '') AS horse_unlinked,
                COUNT(*) FILTER (WHERE jockey_id IS NOT NULL) AS jockey_linked,
                COUNT(*) FILTER (WHERE jockey_id IS NULL AND jockey_code IS NOT NULL AND jockey_code != '') AS jockey_unlinked,
                COUNT(*) FILTER (WHERE trainer_id IS NOT NULL) AS trainer_linked,
                COUNT(*) FILTER (WHERE trainer_id IS NULL AND trainer_code IS NOT NULL AND trainer_code != '') AS trainer_unlinked
            FROM race_entries
        """)
        row = cur.fetchone()
        logger.info(f"  紐付け結果: total={row[0]:,} "
                    f"horse={row[1]:,}(未={row[2]:,}) "
                    f"jockey={row[3]:,}(未={row[4]:,}) "
                    f"trainer={row[5]:,}(未={row[6]:,})")

        logger.info("Phase3完了")

    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


# ====================================================================
# メイン
# ====================================================================

def main():
    parser = argparse.ArgumentParser(description="COPY方式 高速データ取込")
    parser.add_argument("--mode", choices=["normal", "weekly", "setup"], default="setup",
                        help="取得モード (default: setup)")
    parser.add_argument("--dataspec", default="RACE",
                        help="JV-Linkデータ種別 (default: RACE)")
    parser.add_argument("--fromtime", default=None,
                        help="fromtime強制指定（例: 19860101000000）")
    parser.add_argument("--fix-links-only", action="store_true",
                        help="既存データのID紐付け修正のみ実行（JV-Link不使用）")
    parser.add_argument("--csv-only", action="store_true",
                        help="既存CSVファイルからDB取込のみ（JV-Link不使用）")
    parser.add_argument("--skip-phase1", action="store_true",
                        help="Phase1（JV-Link読取）をスキップ")
    args = parser.parse_args()

    start = time.time()
    logger.info("=" * 60)
    logger.info(f"COPY方式 高速取込開始: {datetime.now().isoformat()}")
    logger.info("=" * 60)

    if args.fix_links_only:
        # ID紐付け修正のみ
        phase3_fix_links()
    elif args.csv_only or args.skip_phase1:
        # CSVからDB取込 + 紐付け修正
        phase2_csv_to_db()
        phase3_fix_links()
    else:
        # フル実行: JV-Link → CSV → DB → 紐付け修正
        counters = phase1_jvlink_to_csv(args.dataspec, args.mode, args.fromtime)
        if any(v > 0 for v in counters.values()):
            phase2_csv_to_db()
            phase3_fix_links()
        else:
            logger.info("レコードなし — DB操作をスキップ")

    elapsed = time.time() - start
    logger.info("=" * 60)
    logger.info(f"全処理完了: 所要時間={elapsed:.1f}秒 ({elapsed / 60:.1f}分)")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
