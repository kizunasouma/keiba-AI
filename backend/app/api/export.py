"""
CSVエクスポートAPI — レース結果・予測結果をCSVでダウンロード
"""
import csv
import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(prefix="/export", tags=["export"])

VENUE_NAMES = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
}


@router.get("/race/{race_key}")
def export_race_csv(race_key: str, db: Session = Depends(get_db)):
    """レース結果をCSVでエクスポート"""
    sql = text("""
        SELECT
            r.race_date, r.venue_code, r.race_num, r.race_name,
            r.distance, r.track_type, r.track_cond,
            re.horse_num, re.frame_num,
            h.name_kana AS horse_name,
            j.name_kanji AS jockey_name,
            t.name_kanji AS trainer_name,
            re.age, re.sex, re.weight_carry,
            re.horse_weight, re.weight_diff,
            re.odds_win, re.popularity,
            re.finish_order, re.finish_time, re.last_3f,
            h.father_name, h.mother_father
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        LEFT JOIN horses h ON h.id = re.horse_id
        LEFT JOIN jockeys j ON j.id = re.jockey_id
        LEFT JOIN trainers t ON t.id = re.trainer_id
        WHERE r.race_key = :race_key
        ORDER BY re.horse_num
    """)
    rows = db.execute(sql, {"race_key": race_key}).mappings().all()
    if not rows:
        raise HTTPException(status_code=404, detail="レースが見つかりません")

    output = io.StringIO()
    writer = csv.writer(output)
    # ヘッダー
    writer.writerow([
        "日付", "場", "R", "レース名", "距離", "芝ダ", "馬場",
        "馬番", "枠番", "馬名", "騎手", "調教師",
        "齢", "性", "斤量", "体重", "増減",
        "単勝", "人気", "着順", "タイム", "上3F",
        "父", "母父",
    ])
    track_l = {1: "芝", 2: "ダ", 3: "障"}
    cond_l = {1: "良", 2: "稍", 3: "重", 4: "不"}
    sex_l = {1: "牡", 2: "牝", 3: "騸"}
    for r in rows:
        writer.writerow([
            r["race_date"], VENUE_NAMES.get(r["venue_code"], r["venue_code"]),
            r["race_num"], r["race_name"], r["distance"],
            track_l.get(r["track_type"], ""), cond_l.get(r["track_cond"], ""),
            r["horse_num"], r["frame_num"], r["horse_name"],
            r["jockey_name"], r["trainer_name"],
            r["age"], sex_l.get(r["sex"], ""), r["weight_carry"],
            r["horse_weight"], r["weight_diff"],
            r["odds_win"], r["popularity"], r["finish_order"],
            r["finish_time"], r["last_3f"],
            r["father_name"], r["mother_father"],
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=race_{race_key}.csv"},
    )
