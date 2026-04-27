"""
馬カルテAPI — 馬の基本情報・全戦績・コース別成績・血統・体重推移を返す
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.race import Horse

router = APIRouter(prefix="/horses", tags=["horses"])

VENUE_NAMES = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
}
TRACK_LABELS = {1: "芝", 2: "ダ", 3: "障"}
COND_LABELS = {1: "良", 2: "稍", 3: "重", 4: "不"}


@router.get("/search")
def search_horses(
    q: str = Query(..., min_length=1, description="馬名（部分一致）"),
    limit: int = Query(20, le=50),
    db: Session = Depends(get_db),
):
    """馬名で検索"""
    horses = (
        db.query(Horse)
        .filter(Horse.name_kana.ilike(f"%{q}%"))
        .order_by(Horse.total_earnings.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": h.id,
            "name": h.name_kana,
            "name_eng": h.name_eng,
            "sex": h.sex,
            "father": h.father_name,
            "total_wins": h.total_wins,
            "total_races": h.total_races,
            "total_earnings": h.total_earnings,
        }
        for h in horses
    ]


@router.get("/{horse_id}")
def get_horse(horse_id: int, db: Session = Depends(get_db)):
    """馬の基本情報と血統を返す"""
    horse = db.query(Horse).filter(Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="馬が見つかりません")

    # 3代血統（父/母/父父/父母/母父/母母はDBに名前のみ）
    pedigree = {
        "father": horse.father_name,
        "mother": horse.mother_name,
        "mother_father": horse.mother_father,
        "father_code": horse.father_code,
        "mother_code": horse.mother_code,
        "mother_father_code": horse.mother_father_code,
    }

    return {
        "id": horse.id,
        "blood_reg_num": horse.blood_reg_num,
        "name": horse.name_kana,
        "name_eng": horse.name_eng,
        "birth_date": str(horse.birth_date) if horse.birth_date else None,
        "sex": horse.sex,
        "coat_color": horse.coat_color,
        "producer": horse.producer_name,
        "area": horse.area_name,
        "owner": horse.owner_name,
        "total_wins": horse.total_wins,
        "total_races": horse.total_races,
        "total_earnings": horse.total_earnings,
        "pedigree": pedigree,
    }


@router.get("/{horse_id}/results")
def get_horse_results(horse_id: int, db: Session = Depends(get_db)):
    """馬の全戦績を返す"""
    sql = text("""
        SELECT
            r.race_key, r.race_date, r.race_name, r.venue_code,
            r.distance, r.track_type, r.track_cond, r.grade, r.horse_count,
            re.horse_num, re.frame_num, re.finish_order, re.finish_time,
            re.last_3f, re.weight_carry, re.horse_weight, re.weight_diff,
            re.odds_win, re.popularity, re.margin, re.speed_index,
            re.corner_1, re.corner_2, re.corner_3, re.corner_4,
            re.abnormal_code,
            j.name_kanji AS jockey_name
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        LEFT JOIN jockeys j ON j.id = re.jockey_id
        WHERE re.horse_id = :horse_id
        ORDER BY r.race_date DESC
    """)
    rows = db.execute(sql, {"horse_id": horse_id}).mappings().all()

    results = []
    for row in rows:
        corners = [row["corner_1"], row["corner_2"], row["corner_3"], row["corner_4"]]
        corner_text = "-".join(str(c) for c in corners if c and c > 0) or None
        results.append({
            "race_key":     row["race_key"],
            "race_date":    str(row["race_date"]),
            "race_name":    row["race_name"],
            "venue":        VENUE_NAMES.get(row["venue_code"], row["venue_code"]),
            "distance":     row["distance"],
            "track":        TRACK_LABELS.get(row["track_type"], ""),
            "cond":         COND_LABELS.get(row["track_cond"], ""),
            "grade":        row["grade"],
            "horse_count":  row["horse_count"],
            "horse_num":    row["horse_num"],
            "frame_num":    row["frame_num"],
            "finish_order": row["finish_order"],
            "finish_time":  row["finish_time"],
            "last_3f":      row["last_3f"],
            "weight_carry": float(row["weight_carry"]) if row["weight_carry"] else None,
            "horse_weight": row["horse_weight"],
            "weight_diff":  row["weight_diff"],
            "odds_win":     float(row["odds_win"]) if row["odds_win"] else None,
            "popularity":   row["popularity"],
            "speed_index":  float(row["speed_index"]) if row["speed_index"] else None,
            "corner_text":  corner_text,
            "jockey_name":  row["jockey_name"],
            "abnormal_code": row["abnormal_code"],
        })
    return results


@router.get("/{horse_id}/stats")
def get_horse_stats(horse_id: int, db: Session = Depends(get_db)):
    """馬のコース別・距離別・馬場別成績を返す"""
    # 芝/ダート別
    track_sql = text("""
        SELECT r.track_type,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 2 THEN 1 ELSE 0 END) AS top2,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE re.horse_id = :horse_id AND re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        GROUP BY r.track_type ORDER BY r.track_type
    """)
    # 距離帯別
    dist_sql = text("""
        SELECT
            CASE
                WHEN r.distance <= 1400 THEN '〜1400m'
                WHEN r.distance <= 1800 THEN '1401-1800m'
                WHEN r.distance <= 2200 THEN '1801-2200m'
                ELSE '2201m〜'
            END AS dist_band,
            COUNT(*) AS runs,
            SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE re.horse_id = :horse_id AND re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        GROUP BY dist_band ORDER BY MIN(r.distance)
    """)
    # 馬場状態別
    cond_sql = text("""
        SELECT r.track_cond,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE re.horse_id = :horse_id AND re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        GROUP BY r.track_cond ORDER BY r.track_cond
    """)
    # 競馬場別
    venue_sql = text("""
        SELECT r.venue_code,
               COUNT(*) AS runs,
               SUM(CASE WHEN re.finish_order = 1 THEN 1 ELSE 0 END) AS wins,
               SUM(CASE WHEN re.finish_order <= 3 THEN 1 ELSE 0 END) AS top3
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE re.horse_id = :horse_id AND re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        GROUP BY r.venue_code ORDER BY r.venue_code
    """)

    params = {"horse_id": horse_id}

    def to_list(rows, label_fn):
        return [{"label": label_fn(r), "runs": r["runs"], "wins": r["wins"], "top3": r["top3"]} for r in rows]

    return {
        "by_track": to_list(
            db.execute(track_sql, params).mappings().all(),
            lambda r: TRACK_LABELS.get(r["track_type"], str(r["track_type"])),
        ),
        "by_distance": to_list(
            db.execute(dist_sql, params).mappings().all(),
            lambda r: r["dist_band"],
        ),
        "by_condition": to_list(
            db.execute(cond_sql, params).mappings().all(),
            lambda r: COND_LABELS.get(r["track_cond"], str(r["track_cond"])),
        ),
        "by_venue": to_list(
            db.execute(venue_sql, params).mappings().all(),
            lambda r: VENUE_NAMES.get(r["venue_code"], r["venue_code"]),
        ),
    }


@router.get("/{horse_id}/weight_history")
def get_weight_history(horse_id: int, db: Session = Depends(get_db)):
    """馬体重推移を返す"""
    sql = text("""
        SELECT r.race_date, re.horse_weight, re.weight_diff, re.finish_order
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        WHERE re.horse_id = :horse_id AND re.horse_weight IS NOT NULL
        ORDER BY r.race_date
    """)
    rows = db.execute(sql, {"horse_id": horse_id}).mappings().all()
    return [
        {
            "race_date": str(row["race_date"]),
            "weight": row["horse_weight"],
            "diff": row["weight_diff"],
            "finish_order": row["finish_order"],
        }
        for row in rows
    ]
