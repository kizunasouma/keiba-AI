"""
統計・分析API
種牡馬別成績、枠番別成績、人気別成績、データマイニング、
馬場指数、対戦表、展開予想、荒れ予測、調教評価
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(prefix="/stats", tags=["statistics"])

VENUE_NAMES = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
}
TRACK_LABELS = {1: "芝", 2: "ダ", 3: "障"}


@router.get("/sire")
def get_sire_stats(
    track_type: int | None = Query(None, description="1=芝,2=ダ"),
    distance_min: int | None = Query(None),
    distance_max: int | None = Query(None),
    limit: int = Query(30, le=100),
    db: Session = Depends(get_db),
):
    """種牡馬別成績集計"""
    where = "re.finish_order IS NOT NULL AND COALESCE(re.abnormal_code, 0) = 0 AND h.father_name IS NOT NULL"
    params: dict = {}
    if track_type is not None:
        where += " AND r.track_type = :track_type"
        params["track_type"] = track_type
    if distance_min is not None:
        where += " AND r.distance >= :dmin"
        params["dmin"] = distance_min
    if distance_max is not None:
        where += " AND r.distance <= :dmax"
        params["dmax"] = distance_max

    sql = text(f"""
        SELECT h.father_name AS sire,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 2 THEN 1 ELSE 0 END) AS top2,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        JOIN horses h ON h.id = re.horse_id
        WHERE {where}
        GROUP BY h.father_name
        HAVING COUNT(*) >= 10
        ORDER BY SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END)::float / COUNT(*) DESC
        LIMIT :lim
    """)
    params["lim"] = limit
    rows = db.execute(sql, params).mappings().all()
    return [
        {"sire": r["sire"], "runs": r["runs"], "wins": r["wins"],
         "top2": r["top2"], "top3": r["top3"],
         "win_rate": round(r["wins"] / r["runs"] * 100, 1) if r["runs"] > 0 else 0}
        for r in rows
    ]


@router.get("/bms")
def get_bms_stats(
    track_type: int | None = Query(None),
    limit: int = Query(30, le=100),
    db: Session = Depends(get_db),
):
    """母父（BMS）別成績集計"""
    where = "re.finish_order IS NOT NULL AND COALESCE(re.abnormal_code, 0) = 0 AND h.mother_father IS NOT NULL"
    params: dict = {}
    if track_type is not None:
        where += " AND r.track_type = :track_type"
        params["track_type"] = track_type

    sql = text(f"""
        SELECT h.mother_father AS bms,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        JOIN horses h ON h.id = re.horse_id
        WHERE {where}
        GROUP BY h.mother_father
        HAVING COUNT(*) >= 10
        ORDER BY SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END)::float / COUNT(*) DESC
        LIMIT :lim
    """)
    params["lim"] = limit
    rows = db.execute(sql, params).mappings().all()
    return [
        {"bms": r["bms"], "runs": r["runs"], "wins": r["wins"], "top3": r["top3"],
         "win_rate": round(r["wins"] / r["runs"] * 100, 1) if r["runs"] > 0 else 0}
        for r in rows
    ]


@router.get("/frame")
def get_frame_stats(
    venue_code: str | None = Query(None),
    track_type: int | None = Query(None),
    distance_min: int | None = Query(None),
    distance_max: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """枠番別成績（競馬場×芝ダ×距離帯）"""
    where = "re.finish_order IS NOT NULL AND COALESCE(re.abnormal_code, 0) = 0"
    params: dict = {}
    if venue_code:
        where += " AND r.venue_code = :venue_code"
        params["venue_code"] = venue_code
    if track_type is not None:
        where += " AND r.track_type = :track_type"
        params["track_type"] = track_type
    if distance_min is not None:
        where += " AND r.distance >= :dmin"
        params["dmin"] = distance_min
    if distance_max is not None:
        where += " AND r.distance <= :dmax"
        params["dmax"] = distance_max

    sql = text(f"""
        SELECT re.frame_num,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re JOIN races r ON r.id = re.race_id
        WHERE {where}
        GROUP BY re.frame_num ORDER BY re.frame_num
    """)
    rows = db.execute(sql, params).mappings().all()
    return [
        {"frame": r["frame_num"], "runs": r["runs"], "wins": r["wins"], "top3": r["top3"],
         "win_rate": round(r["wins"] / r["runs"] * 100, 1) if r["runs"] > 0 else 0}
        for r in rows
    ]


@router.get("/popularity")
def get_popularity_stats(db: Session = Depends(get_db)):
    """人気別成績（的中率の相関）"""
    sql = text("""
        SELECT re.popularity,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3,
               AVG(re.odds_win) AS avg_odds
        FROM race_entries re JOIN races r ON r.id = re.race_id
        WHERE re.finish_order IS NOT NULL AND re.popularity IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        GROUP BY re.popularity
        HAVING COUNT(*) >= 10
        ORDER BY re.popularity
        LIMIT 18
    """)
    rows = db.execute(sql).mappings().all()
    return [
        {"popularity": r["popularity"], "runs": r["runs"], "wins": r["wins"], "top3": r["top3"],
         "win_rate": round(r["wins"] / r["runs"] * 100, 1) if r["runs"] > 0 else 0,
         "avg_odds": round(float(r["avg_odds"]), 1) if r["avg_odds"] else None}
        for r in rows
    ]


@router.get("/mining")
def data_mining(
    track_type: int | None = Query(None, description="1=芝,2=ダ"),
    distance_min: int | None = Query(None),
    distance_max: int | None = Query(None),
    venue_code: str | None = Query(None),
    track_cond: int | None = Query(None, description="1=良〜4=不良"),
    is_handicap: bool | None = Query(None),
    is_female_only: bool | None = Query(None),
    frame_num: int | None = Query(None),
    popularity_max: int | None = Query(None, description="人気上限"),
    corner4_max: int | None = Query(None, description="4角通過順上限"),
    sire: str | None = Query(None, description="父馬名（部分一致）"),
    db: Session = Depends(get_db),
):
    """データマイニング: 複合条件で過去レース統計を返す"""
    where = "re.finish_order IS NOT NULL AND COALESCE(re.abnormal_code, 0) = 0"
    params: dict = {}

    if track_type is not None:
        where += " AND r.track_type = :track_type"
        params["track_type"] = track_type
    if distance_min is not None:
        where += " AND r.distance >= :dmin"
        params["dmin"] = distance_min
    if distance_max is not None:
        where += " AND r.distance <= :dmax"
        params["dmax"] = distance_max
    if venue_code:
        where += " AND r.venue_code = :venue_code"
        params["venue_code"] = venue_code
    if track_cond is not None:
        where += " AND r.track_cond = :track_cond"
        params["track_cond"] = track_cond
    if is_handicap is not None:
        where += " AND r.is_handicap = :is_handicap"
        params["is_handicap"] = is_handicap
    if is_female_only is not None:
        where += " AND r.is_female_only = :is_female_only"
        params["is_female_only"] = is_female_only
    if frame_num is not None:
        where += " AND re.frame_num = :frame_num"
        params["frame_num"] = frame_num
    if popularity_max is not None:
        where += " AND re.popularity <= :pop_max"
        params["pop_max"] = popularity_max
    if corner4_max is not None:
        where += " AND re.corner_4 <= :c4_max"
        params["c4_max"] = corner4_max
    if sire:
        where += " AND h.father_name LIKE :sire"
        params["sire"] = f"%{sire}%"
        join_horse = "JOIN horses h ON h.id = re.horse_id"
    else:
        join_horse = "LEFT JOIN horses h ON h.id = re.horse_id"

    sql = text(f"""
        SELECT
            COUNT(*) AS total_runs,
            SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN re.finish_order <= 2 THEN 1 ELSE 0 END) AS top2,
            SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3,
            AVG(re.odds_win) AS avg_odds,
            AVG(re.finish_order) AS avg_finish
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        {join_horse}
        WHERE {where}
    """)
    row = db.execute(sql, params).mappings().first()
    total = row["total_runs"] if row else 0

    if total == 0:
        return {"total_runs": 0, "wins": 0, "top2": 0, "top3": 0,
                "win_rate": 0, "top2_rate": 0, "top3_rate": 0,
                "avg_odds": None, "avg_finish": None}

    return {
        "total_runs": total,
        "wins": row["wins"],
        "top2": row["top2"],
        "top3": row["top3"],
        "win_rate": round(row["wins"] / total * 100, 1),
        "top2_rate": round(row["top2"] / total * 100, 1),
        "top3_rate": round(row["top3"] / total * 100, 1),
        "avg_odds": round(float(row["avg_odds"]), 1) if row["avg_odds"] else None,
        "avg_finish": round(float(row["avg_finish"]), 1) if row["avg_finish"] else None,
    }


# ---------------------------------------------------------------------------
# 回収率分析（オッズ帯別・人気帯別の単勝回収率）
# ---------------------------------------------------------------------------

@router.get("/roi/by_odds")
def get_roi_by_odds(
    days: int = Query(365, le=3650, description="過去N日間"),
    track_type: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """オッズ帯別の単勝回収率"""
    where = "r.race_date >= CURRENT_DATE - :days AND re.finish_order IS NOT NULL AND re.odds_win IS NOT NULL AND re.odds_win > 0"
    params: dict = {"days": days}
    if track_type:
        where += " AND r.track_type = :tt"
        params["tt"] = track_type

    rows = db.execute(text(f"""
        SELECT
            CASE
                WHEN re.odds_win < 2 THEN '1.0-1.9'
                WHEN re.odds_win < 5 THEN '2.0-4.9'
                WHEN re.odds_win < 10 THEN '5.0-9.9'
                WHEN re.odds_win < 20 THEN '10-19.9'
                WHEN re.odds_win < 50 THEN '20-49.9'
                ELSE '50+'
            END AS odds_range,
            COUNT(*) AS bets,
            SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS hits,
            SUM(100) AS invest,
            SUM(CASE WHEN re.finish_order = 1 THEN ROUND(re.odds_win * 100) ELSE 0 END) AS ret
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE {where}
        GROUP BY odds_range
        ORDER BY MIN(re.odds_win)
    """), params).mappings().all()

    return [
        {
            "odds_range": r["odds_range"],
            "bets": r["bets"],
            "hits": r["hits"],
            "hit_rate": round(r["hits"] / r["bets"] * 100, 1) if r["bets"] else 0,
            "invest": int(r["invest"]),
            "return": int(r["ret"]),
            "roi": round(int(r["ret"]) / int(r["invest"]) * 100, 1) if r["invest"] else 0,
        }
        for r in rows
    ]


@router.get("/roi/by_popularity")
def get_roi_by_popularity(
    days: int = Query(365, le=3650),
    track_type: int | None = Query(None),
    db: Session = Depends(get_db),
):
    """人気順別の単勝回収率"""
    where = "r.race_date >= CURRENT_DATE - :days AND re.finish_order IS NOT NULL AND re.odds_win IS NOT NULL AND re.popularity IS NOT NULL"
    params: dict = {"days": days}
    if track_type:
        where += " AND r.track_type = :tt"
        params["tt"] = track_type

    rows = db.execute(text(f"""
        SELECT
            re.popularity,
            COUNT(*) AS bets,
            SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS hits,
            SUM(100) AS invest,
            SUM(CASE WHEN re.finish_order = 1 THEN ROUND(re.odds_win * 100) ELSE 0 END) AS ret,
            AVG(re.odds_win) AS avg_odds
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE {where}
        GROUP BY re.popularity
        HAVING re.popularity <= 18
        ORDER BY re.popularity
    """), params).mappings().all()

    return [
        {
            "popularity": r["popularity"],
            "bets": r["bets"],
            "hits": r["hits"],
            "hit_rate": round(r["hits"] / r["bets"] * 100, 1) if r["bets"] else 0,
            "invest": int(r["invest"]),
            "return": int(r["ret"]),
            "roi": round(int(r["ret"]) / int(r["invest"]) * 100, 1) if r["invest"] else 0,
            "avg_odds": round(float(r["avg_odds"]), 1) if r["avg_odds"] else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 馬場指数（日別の馬場の速さ）
# ---------------------------------------------------------------------------

@router.get("/track_bias")
def get_track_bias(
    race_date: str = Query(..., description="開催日 YYYY-MM-DD"),
    venue_code: str = Query(..., description="場コード 01-10"),
    db: Session = Depends(get_db),
):
    """
    指定日・競馬場の馬場指数を算出。
    基準タイムとの差分で馬場の速さを数値化（負=速い、正=遅い）。
    """
    rows = db.execute(text("""
        WITH day_races AS (
            SELECT r.track_type, r.distance,
                   AVG(re.finish_time) AS avg_time,
                   COUNT(*) AS race_count
            FROM race_entries re
            JOIN races r ON r.id = re.race_id
            WHERE r.race_date = :race_date
              AND r.venue_code = :venue_code
              AND re.finish_order BETWEEN 1 AND 3
              AND re.finish_time > 0
              AND COALESCE(re.abnormal_code, 0) = 0
            GROUP BY r.track_type, r.distance
        ),
        base AS (
            SELECT r.track_type, r.distance,
                   AVG(re.finish_time) AS base_time
            FROM race_entries re
            JOIN races r ON r.id = re.race_id
            WHERE r.venue_code = :venue_code
              AND re.finish_order BETWEEN 1 AND 3
              AND re.finish_time > 0
              AND COALESCE(re.abnormal_code, 0) = 0
              AND r.race_date BETWEEN (CAST(:race_date AS date) - INTERVAL '365 days') AND (CAST(:race_date AS date) - INTERVAL '1 day')
            GROUP BY r.track_type, r.distance
            HAVING COUNT(*) >= 10
        )
        SELECT d.track_type, d.distance, d.avg_time, d.race_count,
               b.base_time,
               ROUND((d.avg_time - b.base_time)::numeric, 1) AS bias
        FROM day_races d
        JOIN base b ON b.track_type = d.track_type AND b.distance = d.distance
        ORDER BY d.track_type, d.distance
    """), {"race_date": race_date, "venue_code": venue_code}).mappings().all()

    track_labels = {1: "芝", 2: "ダ", 3: "障"}
    return [
        {
            "track": track_labels.get(r["track_type"], "?"),
            "distance": r["distance"],
            "avg_time": round(float(r["avg_time"]), 1),
            "base_time": round(float(r["base_time"]), 1),
            "bias": float(r["bias"]),  # 負=速い、正=遅い
            "label": "高速" if float(r["bias"]) < -5 else "やや速" if float(r["bias"]) < 0 else "標準" if float(r["bias"]) < 5 else "やや重" if float(r["bias"]) < 10 else "重い",
            "race_count": r["race_count"],
        }
        for r in rows
    ]


@router.get("/track_bias_detail")
def get_track_bias_detail(
    race_date: str = Query(..., description="開催日 YYYY-MM-DD"),
    venue_code: str = Query(..., description="場コード 01-10"),
    track_type: int | None = Query(None, description="コース種別 1=芝 2=ダート"),
    db: Session = Depends(get_db),
):
    """
    トラックバイアス詳細: 枠番バイアス + 脚質バイアスの2軸分析。
    人気と着順の差分で実力差を除去し、純粋なバイアスを測定する。
    過去30日の同会場・同条件データをベースに算出。
    """
    track_filter = "AND r2.track_type = :track_type" if track_type else ""
    params: dict = {"race_date": race_date, "venue_code": venue_code}
    if track_type:
        params["track_type"] = track_type

    # --- 枠番バイアス: 内枠(1-4)と外枠(5-8)のoutperformance差分 ---
    frame_sql = text(f"""
        WITH base AS (
            SELECT
                AVG(CASE WHEN re.frame_num <= 4
                    THEN re.popularity - re.finish_order END) AS inner_op,
                AVG(CASE WHEN re.frame_num >= 5
                    THEN re.popularity - re.finish_order END) AS outer_op,
                COUNT(DISTINCT r2.id) AS race_count
            FROM races r2
            JOIN race_entries re ON re.race_id = r2.id
            WHERE r2.venue_code = :venue_code {track_filter}
              AND r2.race_date BETWEEN (CAST(:race_date AS date) - 30)
                                    AND CAST(:race_date AS date)
              AND re.finish_order IS NOT NULL AND re.popularity IS NOT NULL
              AND COALESCE(re.abnormal_code, 0) = 0
        )
        SELECT
            ROUND((COALESCE(inner_op, 0) - COALESCE(outer_op, 0))::numeric, 2) AS score,
            race_count
        FROM base
    """)
    frame_row = db.execute(frame_sql, params).mappings().first()
    frame_score = float(frame_row["score"]) if frame_row and frame_row["score"] else 0.0
    frame_races = int(frame_row["race_count"]) if frame_row else 0

    # --- 脚質バイアス: 先行馬と後方馬の上がり3F差 ---
    pace_sql = text(f"""
        WITH base AS (
            SELECT
                AVG(CASE WHEN re.corner_4 <= 3 THEN re.last_3f END) AS front_3f,
                AVG(CASE WHEN re.corner_4 > r2.horse_count / 2 THEN re.last_3f END) AS back_3f,
                COUNT(DISTINCT r2.id) AS race_count
            FROM races r2
            JOIN race_entries re ON re.race_id = r2.id
            WHERE r2.venue_code = :venue_code {track_filter}
              AND r2.race_date BETWEEN (CAST(:race_date AS date) - 30)
                                    AND CAST(:race_date AS date)
              AND re.finish_order IS NOT NULL
              AND re.corner_4 IS NOT NULL AND re.corner_4 > 0
              AND re.last_3f IS NOT NULL AND re.last_3f > 0
              AND COALESCE(re.abnormal_code, 0) = 0
        )
        SELECT
            ROUND((-(COALESCE(front_3f, 0) - COALESCE(back_3f, 0)))::numeric, 2) AS score,
            race_count
        FROM base
    """)
    pace_row = db.execute(pace_sql, params).mappings().first()
    pace_score = float(pace_row["score"]) if pace_row and pace_row["score"] else 0.0
    pace_races = int(pace_row["race_count"]) if pace_row else 0

    # --- 信頼度判定（サンプルレース数に基づく） ---
    sample = max(frame_races, pace_races)
    confidence = "高" if sample >= 10 else "中" if sample >= 5 else "低"

    # --- ラベル生成 ---
    def _frame_label(s: float) -> str:
        if s > 0.5: return "内枠有利"
        if s > 0.2: return "やや内枠有利"
        if s < -0.5: return "外枠有利"
        if s < -0.2: return "やや外枠有利"
        return "均等"

    def _pace_label(s: float) -> str:
        if s > 3.0: return "先行有利"
        if s > 1.0: return "やや先行有利"
        if s < -3.0: return "差し有利"
        if s < -1.0: return "やや差し有利"
        return "均等"

    # --- サマリー文生成 ---
    parts = []
    if abs(frame_score) > 0.2:
        parts.append("内枠" if frame_score > 0 else "外枠")
    if abs(pace_score) > 1.0:
        parts.append("先行馬" if pace_score > 0 else "差し馬")
    summary = "の".join(parts) + "が有利な馬場" if parts else "バイアス少なめ（フラット）"

    return {
        "frame_bias": {
            "score": frame_score,
            "label": _frame_label(frame_score),
            "sample_races": frame_races,
        },
        "pace_bias": {
            "score": pace_score,
            "label": _pace_label(pace_score),
            "sample_races": pace_races,
        },
        "confidence": confidence,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# 対戦表（2頭の直接対決成績）
# ---------------------------------------------------------------------------

@router.get("/matchup")
def get_matchup(
    horse_id_1: int = Query(..., description="馬1のID"),
    horse_id_2: int = Query(..., description="馬2のID"),
    db: Session = Depends(get_db),
):
    """2頭が同じレースに出走した全レースの対戦成績を返す"""
    rows = db.execute(text("""
        SELECT
            r.race_key, r.race_date, r.race_name, r.venue_code, r.distance, r.track_type,
            re1.horse_num AS num1, re1.finish_order AS order1, re1.finish_time AS time1,
            re2.horse_num AS num2, re2.finish_order AS order2, re2.finish_time AS time2
        FROM race_entries re1
        JOIN race_entries re2 ON re1.race_id = re2.race_id
        JOIN races r ON r.id = re1.race_id
        WHERE re1.horse_id = :h1
          AND re2.horse_id = :h2
          AND re1.finish_order IS NOT NULL
          AND re2.finish_order IS NOT NULL
        ORDER BY r.race_date DESC
        LIMIT 20
    """), {"h1": horse_id_1, "h2": horse_id_2}).mappings().all()

    wins_1 = sum(1 for r in rows if r["order1"] < r["order2"])
    wins_2 = sum(1 for r in rows if r["order2"] < r["order1"])

    return {
        "total_matchups": len(rows),
        "horse1_wins": wins_1,
        "horse2_wins": wins_2,
        "draws": len(rows) - wins_1 - wins_2,
        "races": [
            {
                "race_key": r["race_key"],
                "race_date": str(r["race_date"]),
                "race_name": r["race_name"],
                "venue": VENUE_NAMES.get(r["venue_code"], r["venue_code"]),
                "distance": r["distance"],
                "track": TRACK_LABELS.get(r["track_type"], "?"),
                "horse1": {"num": r["num1"], "order": r["order1"]},
                "horse2": {"num": r["num2"], "order": r["order2"]},
                "winner": 1 if r["order1"] < r["order2"] else 2 if r["order2"] < r["order1"] else 0,
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# 展開予想（脚質分布からレースペースを予測）
# ---------------------------------------------------------------------------

@router.get("/pace_prediction")
def predict_pace(
    race_key: str = Query(..., description="レースキー"),
    db: Session = Depends(get_db),
):
    """出走馬の脚質傾向からペースを予測"""
    rows = db.execute(text("""
        SELECT re.horse_num, re.horse_id,
               re.corner_1, re.corner_2, re.corner_3, re.corner_4
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE r.race_key = :rk
    """), {"rk": race_key}).mappings().all()

    if not rows:
        return {"race_key": race_key, "pace": "unknown", "runners": []}

    # 各馬の過去走からの脚質を推定
    runners = []
    style_counts = {"逃": 0, "先": 0, "差": 0, "追": 0}

    for r in rows:
        # 今走のコーナー通過がなければ過去走から推定
        positions = [r["corner_1"], r["corner_2"], r["corner_3"], r["corner_4"]]
        positions = [p for p in positions if p and p > 0]

        if not positions and r["horse_id"]:
            # 過去3走のコーナー通過平均
            past = db.execute(text("""
                SELECT AVG(sub.corner_4) FROM (
                    SELECT re2.corner_4
                    FROM race_entries re2
                    JOIN races r2 ON r2.id = re2.race_id
                    WHERE re2.horse_id = :hid
                      AND re2.corner_4 IS NOT NULL AND re2.corner_4 > 0
                    ORDER BY r2.race_date DESC LIMIT 3
                ) sub
            """), {"hid": r["horse_id"]}).scalar()
            if past:
                positions = [float(past)]

        n = len(rows)
        if positions:
            avg = sum(positions) / len(positions)
            first = positions[0]
            if first == 1:
                style = "逃"
            elif avg <= n * 0.33:
                style = "先"
            elif avg <= n * 0.66:
                style = "差"
            else:
                style = "追"
        else:
            style = "不明"

        if style in style_counts:
            style_counts[style] += 1
        runners.append({"horse_num": r["horse_num"], "style": style})

    # ペース判定
    escape_count = style_counts["逃"]
    front_count = style_counts["逃"] + style_counts["先"]
    total = len(rows)

    if escape_count >= 3 or front_count >= total * 0.5:
        pace = "ハイペース"
        pace_score = min(100, int(front_count / total * 150))
    elif escape_count == 0:
        pace = "超スロー"
        pace_score = 10
    elif escape_count == 1 and front_count <= total * 0.25:
        pace = "スロー"
        pace_score = 30
    else:
        pace = "ミドル"
        pace_score = 50

    return {
        "race_key": race_key,
        "pace": pace,
        "pace_score": pace_score,
        "style_distribution": style_counts,
        "advantage": "差し・追込有利" if pace == "ハイペース" else "逃げ・先行有利" if pace in ("スロー", "超スロー") else "展開次第",
        "runners": runners,
    }


# ---------------------------------------------------------------------------
# 荒れ予測（波乱度スコア）
# ---------------------------------------------------------------------------

@router.get("/upset_score")
def predict_upset(
    race_key: str = Query(..., description="レースキー"),
    db: Session = Depends(get_db),
):
    """レースの荒れやすさを過去データから予測"""
    # レース条件を取得
    race = db.execute(text("""
        SELECT distance, track_type, track_cond, horse_count, grade,
               is_handicap, is_female_only, venue_code
        FROM races WHERE race_key = :rk
    """), {"rk": race_key}).mappings().first()

    if not race:
        return {"race_key": race_key, "upset_score": 50}

    # 同条件過去レースの1番人気敗退率
    row = db.execute(text("""
        WITH fav AS (
            SELECT r.race_key,
                   MIN(re.odds_win) AS min_odds,
                   MIN(CASE WHEN re.popularity = 1 THEN re.finish_order END) AS fav_order
            FROM race_entries re
            JOIN races r ON r.id = re.race_id
            WHERE r.track_type = :tt
              AND r.distance BETWEEN :dist - 200 AND :dist + 200
              AND re.finish_order IS NOT NULL
              AND re.odds_win IS NOT NULL
              AND r.race_date >= CURRENT_DATE - 730
            GROUP BY r.race_key
        )
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN fav_order > 3 THEN 1 ELSE 0 END) AS fav_lose
        FROM fav
    """), {
        "tt": race["track_type"],
        "dist": race["distance"],
    }).mappings().first()

    total = row["total"] if row else 0
    fav_lose = row["fav_lose"] if row else 0
    fav_lose_rate = fav_lose / total if total > 0 else 0.3

    # 荒れ要因の加算
    score = int(fav_lose_rate * 100)
    factors = []

    if race["is_handicap"]:
        score += 15
        factors.append("ハンデ戦")
    if race["horse_count"] and race["horse_count"] >= 16:
        score += 10
        factors.append(f"多頭数({race['horse_count']}頭)")
    if race["track_cond"] and race["track_cond"] >= 3:
        score += 10
        factors.append("重馬場以上")
    if race["is_female_only"]:
        score += 5
        factors.append("牝馬限定")
    if race["grade"] and race["grade"] >= 5:
        score += 5
        factors.append("条件戦")

    score = min(100, max(0, score))

    return {
        "race_key": race_key,
        "upset_score": score,
        "label": "大荒れ注意" if score >= 70 else "荒れ傾向" if score >= 50 else "平穏" if score < 30 else "やや荒れ",
        "fav_lose_rate": round(fav_lose_rate * 100, 1),
        "factors": factors,
        "sample_races": total,
    }


# ---------------------------------------------------------------------------
# 調教評価（坂路/ウッドの偏差値化）
# ---------------------------------------------------------------------------

@router.get("/training_rating")
def get_training_rating(
    race_key: str = Query(..., description="レースキー"),
    db: Session = Depends(get_db),
):
    """出走馬の直近調教タイムを母集団と比較してS〜C評価"""
    # 出走馬の直近調教タイムを取得
    rows = db.execute(text("""
        SELECT DISTINCT ON (re.horse_num)
            re.horse_num, re.horse_id,
            tt.training_date, tt.course_type, tt.distance,
            tt.lap_time, tt.last_3f, tt.last_1f
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        JOIN training_times tt ON tt.horse_id = re.horse_id
        WHERE r.race_key = :rk
          AND tt.training_date < r.race_date
          AND tt.training_date >= r.race_date - 30
          AND tt.last_3f IS NOT NULL AND tt.last_3f > 0
        ORDER BY re.horse_num, tt.training_date DESC
    """), {"rk": race_key}).mappings().all()

    if not rows:
        return {"race_key": race_key, "ratings": []}

    # 母集団の統計（直近1年の全調教データ）
    stats = db.execute(text("""
        SELECT course_type,
               AVG(last_3f) AS mean_3f, STDDEV(last_3f) AS std_3f,
               AVG(last_1f) AS mean_1f, STDDEV(last_1f) AS std_1f
        FROM training_times
        WHERE last_3f IS NOT NULL AND last_3f > 0
          AND training_date >= CURRENT_DATE - 365
        GROUP BY course_type
    """)).mappings().all()

    stat_map = {s["course_type"]: s for s in stats}
    course_labels = {1: "坂路", 2: "ウッド", 3: "芝", 4: "ダ"}

    ratings = []
    for r in rows:
        ct = r["course_type"]
        s = stat_map.get(ct)
        if not s or not s["std_3f"] or float(s["std_3f"]) == 0:
            ratings.append({"horse_num": r["horse_num"], "rating": "C", "score": 50})
            continue

        # 偏差値算出（タイムが短いほど良い → 反転）
        z = (float(s["mean_3f"]) - float(r["last_3f"])) / float(s["std_3f"])
        score = round(z * 10 + 50, 1)

        if score >= 65:
            rating = "S"
        elif score >= 58:
            rating = "A"
        elif score >= 50:
            rating = "B"
        elif score >= 42:
            rating = "C"
        else:
            rating = "D"

        ratings.append({
            "horse_num": r["horse_num"],
            "rating": rating,
            "score": score,
            "course": course_labels.get(ct, "不明"),
            "training_date": str(r["training_date"]),
            "last_3f": r["last_3f"],
            "last_1f": r["last_1f"],
        })

    return {"race_key": race_key, "ratings": ratings}
