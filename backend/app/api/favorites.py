"""
お気に入り馬API — 注目馬の登録・一覧・出走チェック
JSONファイルで管理（DB不要のシンプル方式）
"""
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(prefix="/favorites", tags=["favorites"])

FAVORITES_FILE = Path(__file__).parent.parent.parent / "data" / "favorites.json"


def _load() -> list[dict]:
    if not FAVORITES_FILE.exists():
        return []
    return json.loads(FAVORITES_FILE.read_text(encoding="utf-8"))


def _save(favorites: list[dict]):
    FAVORITES_FILE.parent.mkdir(parents=True, exist_ok=True)
    FAVORITES_FILE.write_text(json.dumps(favorites, ensure_ascii=False, indent=2), encoding="utf-8")


class FavoriteRequest(BaseModel):
    horse_id: int
    horse_name: str | None = None
    note: str | None = None


@router.get("")
def list_favorites():
    """お気に入り馬一覧"""
    return _load()


@router.post("")
def add_favorite(req: FavoriteRequest):
    """お気に入り馬を追加"""
    favs = _load()
    # 重複チェック
    if any(f["horse_id"] == req.horse_id for f in favs):
        return {"message": "既に登録されています", "favorites": favs}
    favs.append({
        "horse_id": req.horse_id,
        "horse_name": req.horse_name,
        "note": req.note,
    })
    _save(favs)
    return {"message": "追加しました", "favorites": favs}


@router.delete("/{horse_id}")
def remove_favorite(horse_id: int):
    """お気に入り馬を削除"""
    favs = _load()
    favs = [f for f in favs if f["horse_id"] != horse_id]
    _save(favs)
    return {"message": "削除しました", "favorites": favs}


@router.get("/upcoming")
def check_upcoming(db: Session = Depends(get_db)):
    """お気に入り馬の直近出走予定をチェック"""
    favs = _load()
    if not favs:
        return []

    horse_ids = [f["horse_id"] for f in favs]
    sql = text("""
        SELECT h.id AS horse_id, h.name_kana AS horse_name,
               r.race_key, r.race_date, r.race_name, r.venue_code,
               r.distance, r.track_type, r.race_num
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        JOIN horses h ON h.id = re.horse_id
        WHERE re.horse_id = ANY(:ids)
          AND r.race_date >= CURRENT_DATE
        ORDER BY r.race_date, r.race_num
    """)
    rows = db.execute(sql, {"ids": horse_ids}).mappings().all()

    VENUE = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
             "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉"}
    TRACK = {1: "芝", 2: "ダ", 3: "障"}

    return [
        {
            "horse_id": row["horse_id"],
            "horse_name": row["horse_name"],
            "race_key": row["race_key"],
            "race_date": str(row["race_date"]),
            "race_name": row["race_name"],
            "venue": VENUE.get(row["venue_code"], row["venue_code"]),
            "distance": row["distance"],
            "track": TRACK.get(row["track_type"], ""),
            "race_num": row["race_num"],
        }
        for row in rows
    ]
