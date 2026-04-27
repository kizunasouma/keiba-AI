"""
騎手API — 基本情報・条件別成績・直近成績推移・騎手×調教師コンビ成績を返す
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.race import Jockey

router = APIRouter(prefix="/jockeys", tags=["jockeys"])

VENUE_NAMES = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
}
TRACK_LABELS = {1: "芝", 2: "ダ", 3: "障"}
BELONG_LABELS = {1: "美浦", 2: "栗東", 3: "地方", 4: "外国"}


@router.get("/search")
def search_jockeys(
    q: str = Query(..., min_length=1, description="騎手名（部分一致）"),
    limit: int = Query(20, le=50),
    db: Session = Depends(get_db),
):
    """騎手名で検索"""
    jockeys = (
        db.query(Jockey)
        .filter(Jockey.name_kanji.ilike(f"%{q}%"))
        .order_by(Jockey.total_1st.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": j.id, "name": j.name_kanji, "name_kana": j.name_kana,
            "belong": BELONG_LABELS.get(j.belong_code, "") if j.belong_code else "",
            "total_1st": j.total_1st, "total_races": j.total_races,
            "win_rate": round(j.total_1st / j.total_races * 100, 1) if j.total_races else 0,
        }
        for j in jockeys
    ]


@router.get("/{jockey_id}")
def get_jockey(jockey_id: int, db: Session = Depends(get_db)):
    """騎手の基本情報を返す"""
    j = db.query(Jockey).filter(Jockey.id == jockey_id).first()
    if not j:
        raise HTTPException(status_code=404, detail="騎手が見つかりません")
    total = j.total_races or 0
    return {
        "id": j.id,
        "jockey_code": j.jockey_code,
        "name": j.name_kanji,
        "name_kana": j.name_kana,
        "birth_date": str(j.birth_date) if j.birth_date else None,
        "belong": BELONG_LABELS.get(j.belong_code, str(j.belong_code)) if j.belong_code else None,
        "total_1st": j.total_1st,
        "total_2nd": j.total_2nd,
        "total_3rd": j.total_3rd,
        "total_races": total,
        "win_rate": round(j.total_1st / total * 100, 1) if total > 0 else 0,
        "top3_rate": round((j.total_1st + j.total_2nd + j.total_3rd) / total * 100, 1) if total > 0 else 0,
    }


@router.get("/{jockey_id}/stats")
def get_jockey_stats(jockey_id: int, db: Session = Depends(get_db)):
    """騎手の条件別成績（芝/ダ、距離帯、競馬場、クラス）"""
    params = {"jockey_id": jockey_id}

    # 芝/ダート別
    track_sql = text("""
        SELECT r.track_type,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re JOIN races r ON r.id = re.race_id
        WHERE re.jockey_id = :jockey_id AND re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        GROUP BY r.track_type ORDER BY r.track_type
    """)
    # 距離帯別
    dist_sql = text("""
        SELECT CASE WHEN r.distance <= 1400 THEN '〜1400m'
                    WHEN r.distance <= 1800 THEN '1401-1800m'
                    WHEN r.distance <= 2200 THEN '1801-2200m'
                    ELSE '2201m〜' END AS dist_band,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re JOIN races r ON r.id = re.race_id
        WHERE re.jockey_id = :jockey_id AND re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        GROUP BY dist_band ORDER BY MIN(r.distance)
    """)
    # 競馬場別
    venue_sql = text("""
        SELECT r.venue_code,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re JOIN races r ON r.id = re.race_id
        WHERE re.jockey_id = :jockey_id AND re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        GROUP BY r.venue_code ORDER BY r.venue_code
    """)
    # グレード別
    grade_sql = text("""
        SELECT r.grade,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re JOIN races r ON r.id = re.race_id
        WHERE re.jockey_id = :jockey_id AND re.finish_order IS NOT NULL
          AND r.grade IS NOT NULL AND COALESCE(re.abnormal_code, 0) = 0
        GROUP BY r.grade ORDER BY r.grade
    """)

    GRADE_LABELS = {1: "G1", 2: "G2", 3: "G3", 4: "重賞", 5: "OP", 6: "L",
                    7: "3勝", 8: "2勝", 9: "1勝", 10: "新馬/未勝利"}

    def to_list(rows, label_fn):
        return [{"label": label_fn(r), "runs": r["runs"], "wins": r["wins"], "top3": r["top3"]} for r in rows]

    return {
        "by_track": to_list(db.execute(track_sql, params).mappings().all(),
                            lambda r: TRACK_LABELS.get(r["track_type"], str(r["track_type"]))),
        "by_distance": to_list(db.execute(dist_sql, params).mappings().all(),
                               lambda r: r["dist_band"]),
        "by_venue": to_list(db.execute(venue_sql, params).mappings().all(),
                            lambda r: VENUE_NAMES.get(r["venue_code"], r["venue_code"])),
        "by_grade": to_list(db.execute(grade_sql, params).mappings().all(),
                            lambda r: GRADE_LABELS.get(r["grade"], str(r["grade"]))),
    }


@router.get("/{jockey_id}/recent")
def get_jockey_recent(jockey_id: int, days: int = Query(90, le=365), db: Session = Depends(get_db)):
    """騎手の直近N日間の成績推移"""
    sql = text("""
        SELECT r.race_date,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re JOIN races r ON r.id = re.race_id
        WHERE re.jockey_id = :jockey_id
          AND r.race_date >= CURRENT_DATE - :days
          AND re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        GROUP BY r.race_date ORDER BY r.race_date
    """)
    rows = db.execute(sql, {"jockey_id": jockey_id, "days": days}).mappings().all()
    return [{"date": str(r["race_date"]), "runs": r["runs"], "wins": r["wins"], "top3": r["top3"]} for r in rows]


@router.get("/{jockey_id}/combo")
def get_jockey_trainer_combo(jockey_id: int, db: Session = Depends(get_db)):
    """騎手×調教師のコンビ成績"""
    sql = text("""
        SELECT t.name_kanji AS trainer_name, t.id AS trainer_id,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        JOIN trainers t ON t.id = re.trainer_id
        WHERE re.jockey_id = :jockey_id AND re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        GROUP BY t.id, t.name_kanji
        HAVING COUNT(*) >= 3
        ORDER BY COUNT(*) DESC LIMIT 20
    """)
    rows = db.execute(sql, {"jockey_id": jockey_id}).mappings().all()
    return [
        {"trainer_name": r["trainer_name"], "trainer_id": r["trainer_id"],
         "runs": r["runs"], "wins": r["wins"], "top3": r["top3"]}
        for r in rows
    ]
