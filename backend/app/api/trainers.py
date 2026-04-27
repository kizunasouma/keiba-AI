"""
調教師API — 基���情報・条件別成績・直近成績推移を返す
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.race import Trainer

router = APIRouter(prefix="/trainers", tags=["trainers"])

VENUE_NAMES = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "���京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
}
TRACK_LABELS = {1: "芝", 2: "ダ", 3: "障"}
BELONG_LABELS = {1: "美浦", 2: "栗東"}


@router.get("/search")
def search_trainers(
    q: str = Query(..., min_length=1, description="調教師名（部分一致）"),
    limit: int = Query(20, le=50),
    db: Session = Depends(get_db),
):
    """調教師名で検索"""
    trainers = (
        db.query(Trainer)
        .filter(Trainer.name_kanji.ilike(f"%{q}%"))
        .order_by(Trainer.total_1st.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": t.id, "name": t.name_kanji, "name_kana": t.name_kana,
            "belong": BELONG_LABELS.get(t.belong_code, "") if t.belong_code else "",
            "total_1st": t.total_1st, "total_races": t.total_races,
            "win_rate": round(t.total_1st / t.total_races * 100, 1) if t.total_races else 0,
        }
        for t in trainers
    ]


@router.get("/{trainer_id}")
def get_trainer(trainer_id: int, db: Session = Depends(get_db)):
    """調教師の基本情報を返す"""
    t = db.query(Trainer).filter(Trainer.id == trainer_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="調教師が見つかりません")
    total = t.total_races or 0
    return {
        "id": t.id,
        "trainer_code": t.trainer_code,
        "name": t.name_kanji,
        "name_kana": t.name_kana,
        "belong": BELONG_LABELS.get(t.belong_code, str(t.belong_code)) if t.belong_code else None,
        "total_1st": t.total_1st,
        "total_races": total,
        "win_rate": round(t.total_1st / total * 100, 1) if total > 0 else 0,
    }


@router.get("/{trainer_id}/stats")
def get_trainer_stats(trainer_id: int, db: Session = Depends(get_db)):
    """調教師の条件別成績"""
    params = {"trainer_id": trainer_id}

    track_sql = text("""
        SELECT r.track_type,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re JOIN races r ON r.id = re.race_id
        WHERE re.trainer_id = :trainer_id AND re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        GROUP BY r.track_type ORDER BY r.track_type
    """)
    dist_sql = text("""
        SELECT CASE WHEN r.distance <= 1400 THEN '〜1400m'
                    WHEN r.distance <= 1800 THEN '1401-1800m'
                    WHEN r.distance <= 2200 THEN '1801-2200m'
                    ELSE '2201m〜' END AS dist_band,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re JOIN races r ON r.id = re.race_id
        WHERE re.trainer_id = :trainer_id AND re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        GROUP BY dist_band ORDER BY MIN(r.distance)
    """)
    venue_sql = text("""
        SELECT r.venue_code,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re JOIN races r ON r.id = re.race_id
        WHERE re.trainer_id = :trainer_id AND re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        GROUP BY r.venue_code ORDER BY r.venue_code
    """)

    def to_list(rows, label_fn):
        return [{"label": label_fn(r), "runs": r["runs"], "wins": r["wins"], "top3": r["top3"]} for r in rows]

    return {
        "by_track": to_list(db.execute(track_sql, params).mappings().all(),
                            lambda r: TRACK_LABELS.get(r["track_type"], str(r["track_type"]))),
        "by_distance": to_list(db.execute(dist_sql, params).mappings().all(),
                               lambda r: r["dist_band"]),
        "by_venue": to_list(db.execute(venue_sql, params).mappings().all(),
                            lambda r: VENUE_NAMES.get(r["venue_code"], r["venue_code"])),
    }


@router.get("/{trainer_id}/recent")
def get_trainer_recent(trainer_id: int, days: int = Query(90, le=365), db: Session = Depends(get_db)):
    """調教師の直近N日間の成績推移"""
    sql = text("""
        SELECT r.race_date,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re JOIN races r ON r.id = re.race_id
        WHERE re.trainer_id = :trainer_id
          AND r.race_date >= CURRENT_DATE - :days
          AND re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        GROUP BY r.race_date ORDER BY r.race_date
    """)
    rows = db.execute(sql, {"trainer_id": trainer_id, "days": days}).mappings().all()
    return [{"date": str(r["race_date"]), "runs": r["runs"], "wins": r["wins"], "top3": r["top3"]} for r in rows]
