"""
スピード指数（speed_index）算出バッチ
走破タイムを距離・馬場差で補正し、相対的な能力値に変換する

【計算式】
  基準タイム = 同距離・同コース種別・同馬場状態の平均走破タイム（直近2年）
  speed_index = (基準タイム - 走破タイム) / 基準タイム × 100 + 50
  → 50が平均。高いほど速い。

使い方:
    python scripts/calc_speed_index.py
    python scripts/calc_speed_index.py --since 2024-01-01  # 指定日以降のみ
"""
import sys
import argparse
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.database import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def calc_speed_index(db, since: str | None = None):
    """speed_indexを計算してrace_entriesテーブルを更新"""

    # 1. 基準タイム算出: 距離×コース種別×馬場状態ごとの平均走破タイム
    logger.info("基準タイム算出中...")
    db.execute(text("""
        CREATE TEMP TABLE IF NOT EXISTS base_times AS
        SELECT
            r.distance,
            r.track_type,
            COALESCE(r.track_cond, 1) AS track_cond,
            AVG(re.finish_time) AS avg_time,
            STDDEV(re.finish_time) AS std_time,
            COUNT(*) AS sample_count
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE re.finish_time IS NOT NULL
          AND re.finish_time > 0
          AND re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
          AND r.race_date >= CURRENT_DATE - INTERVAL '2 years'
        GROUP BY r.distance, r.track_type, COALESCE(r.track_cond, 1)
        HAVING COUNT(*) >= 10
    """))

    # 2. speed_index を算出して更新
    where_clause = ""
    if since:
        where_clause = f"AND r.race_date >= '{since}'"

    logger.info("speed_index 算出・更新中...")
    result = db.execute(text(f"""
        UPDATE race_entries re
        SET speed_index = ROUND(
            (bt.avg_time - re.finish_time)::numeric / NULLIF(bt.avg_time, 0) * 100 + 50,
            2
        )
        FROM races r, base_times bt
        WHERE re.race_id = r.id
          AND r.distance = bt.distance
          AND r.track_type = bt.track_type
          AND COALESCE(r.track_cond, 1) = bt.track_cond
          AND re.finish_time IS NOT NULL
          AND re.finish_time > 0
          AND COALESCE(re.abnormal_code, 0) = 0
          {where_clause}
    """))

    updated = result.rowcount
    db.execute(text("DROP TABLE IF EXISTS base_times"))
    db.commit()

    logger.info(f"speed_index 更新完了: {updated:,}件")
    return updated


def show_stats(db):
    """speed_indexの統計を表示"""
    row = db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE speed_index IS NOT NULL) AS has_si,
            COUNT(*) AS total,
            AVG(speed_index) AS avg_si,
            MIN(speed_index) AS min_si,
            MAX(speed_index) AS max_si
        FROM race_entries
    """)).first()
    logger.info(f"統計: {row.has_si:,}/{row.total:,}件にSI設定済み "
                f"(avg={row.avg_si:.1f}, min={row.min_si:.1f}, max={row.max_si:.1f})"
                if row.has_si else f"統計: 0/{row.total:,}件")


def main():
    parser = argparse.ArgumentParser(description="スピード指数算出バッチ")
    parser.add_argument("--since", type=str, default=None, help="指定日以降のみ計算 (YYYY-MM-DD)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        calc_speed_index(db, args.since)
        show_stats(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
