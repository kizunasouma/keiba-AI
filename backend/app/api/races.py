"""
レースAPIルーター
レース一覧・詳細・出走馬（過去走・血統・脚質・調教含む）を返すエンドポイント
ラップタイム・ペース分析・払戻情報も提供
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.security import validate_race_key, validate_venue_code, sanitize_string
from app.models.race import Race, RaceEntry, RaceLap, Payout, OddsSnapshot
from app.schemas.race import RaceResponse, RaceDetailResponse, OddsTimelineResponse, OddsSnapshotItem

router = APIRouter(prefix="/races", tags=["races"])

# 場コード→名称
VENUE_NAMES = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
}
TRACK_LABELS = {1: "芝", 2: "ダ", 3: "障"}
COND_LABELS = {1: "良", 2: "稍", 3: "重", 4: "不"}
# 着差コード→テキスト変換マップ
# JV-Dataの着差コード: 0=同着(1着), 1=ハナ, 2=アタマ, ... 21=大差
MARGIN_LABELS = {
    0: "同着", 1: "ハナ", 2: "アタマ", 3: "クビ", 4: "1/2", 5: "3/4", 6: "1",
    7: "1 1/4", 8: "1 1/2", 9: "1 3/4", 10: "2", 11: "2 1/2", 12: "3",
    13: "3 1/2", 14: "4", 15: "5", 16: "6", 17: "7", 18: "8", 19: "9",
    20: "10", 21: "大差",
}


def margin_to_text(code: int | None) -> str | None:
    """着差コード（数値）をテキストに変換する関数"""
    if code is None:
        return None
    return MARGIN_LABELS.get(code)


@router.get("", response_model=list[RaceResponse])
def get_races(
    race_date: Optional[date] = Query(None, description="開催日（YYYY-MM-DD）"),
    date_from: Optional[date] = Query(None, description="開催日（開始）"),
    date_to: Optional[date] = Query(None, description="開催日（終了）"),
    venue_code: Optional[str] = Query(None, description="場コード（01〜10、カンマ区切りで複数可）"),
    grade: Optional[int] = Query(None, description="グレード（1=G1,...）"),
    track_type: Optional[int] = Query(None, description="1=芝,2=ダート,3=障害"),
    distance_min: Optional[int] = Query(None, description="距離下限(m)"),
    distance_max: Optional[int] = Query(None, description="距離上限(m)"),
    track_cond: Optional[int] = Query(None, description="馬場状態（1=良〜4=不良）"),
    is_handicap: Optional[bool] = Query(None, description="ハンデ戦のみ"),
    is_female_only: Optional[bool] = Query(None, description="牝馬限定のみ"),
    race_name: Optional[str] = Query(None, description="レース名（部分一致）"),
    condition_code: Optional[int] = Query(None, description="競走条件コード"),
    limit: int = Query(50, le=5000),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """レース一覧を返す（高度な検索フィルター対応）"""
    query = db.query(Race)
    # 日付フィルター
    if race_date:
        query = query.filter(Race.race_date == race_date)
    if date_from:
        query = query.filter(Race.race_date >= date_from)
    if date_to:
        query = query.filter(Race.race_date <= date_to)
    # 競馬場フィルター（カンマ区切りで複数可）
    if venue_code:
        codes = [c.strip() for c in venue_code.split(",")]
        if len(codes) == 1:
            query = query.filter(Race.venue_code == codes[0])
        else:
            query = query.filter(Race.venue_code.in_(codes))
    if grade:
        query = query.filter(Race.grade == grade)
    # 芝/ダート/障害
    if track_type is not None:
        query = query.filter(Race.track_type == track_type)
    # 距離範囲
    if distance_min is not None:
        query = query.filter(Race.distance >= distance_min)
    if distance_max is not None:
        query = query.filter(Race.distance <= distance_max)
    # 馬場状態
    if track_cond is not None:
        query = query.filter(Race.track_cond == track_cond)
    # ハンデ戦
    if is_handicap is not None:
        query = query.filter(Race.is_handicap == is_handicap)
    # 牝馬限定
    if is_female_only is not None:
        query = query.filter(Race.is_female_only == is_female_only)
    # 競走条件コード
    if condition_code is not None:
        query = query.filter(Race.condition_code == condition_code)
    # レース名検索
    if race_name:
        race_name = sanitize_string(race_name, max_length=50)
        query = query.filter(Race.race_name.ilike(f"%{race_name}%"))
    return query.order_by(Race.race_date.desc(), Race.race_num).offset(offset).limit(limit).all()


@router.get("/{race_key}", response_model=RaceDetailResponse)
def get_race(race_key: str, db: Session = Depends(get_db)):
    """レース詳細（出走馬リスト付き）を返す"""
    validate_race_key(race_key)
    race = (
        db.query(Race)
        .options(joinedload(Race.entries))
        .filter(Race.race_key == race_key)
        .first()
    )
    if not race:
        raise HTTPException(status_code=404, detail="レースが見つかりません")
    return race


def _detect_running_style(c1: int | None, c2: int | None, c3: int | None, c4: int | None, horse_count: int | None) -> str | None:
    """コーナー通過順位から脚質を推定"""
    positions = [p for p in [c1, c2, c3, c4] if p is not None and p > 0]
    if not positions:
        return None
    n = horse_count or 18
    avg = sum(positions) / len(positions)
    first = positions[0]
    # 逃げ: 先頭
    if first == 1:
        return "逃"
    # 先行: 前1/3
    if avg <= n * 0.33:
        return "先"
    # 差し: 中団
    if avg <= n * 0.66:
        return "差"
    # 追込
    return "追"


def _get_past_races(db: Session, horse_id: int | None, current_race_date: date, limit: int = 5) -> list[dict]:
    """指定馬の過去N走を取得（着差・通過順・レース名・頭数含む）"""
    if not horse_id:
        return []

    sql = text("""
        SELECT
            r.race_date,
            r.race_name,
            r.venue_code,
            r.distance,
            r.track_type,
            r.track_cond,
            r.horse_count,
            r.grade,
            re.horse_num,
            re.popularity,
            re.finish_order,
            re.finish_time,
            re.last_3f,
            re.weight_carry,
            re.horse_weight,
            re.weight_diff,
            re.corner_1, re.corner_2, re.corner_3, re.corner_4,
            re.odds_win,
            re.margin,
            re.abnormal_code,
            re.speed_index,
            j.name_kanji AS jockey_name
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        LEFT JOIN jockeys j ON j.id = re.jockey_id
        WHERE re.horse_id = :horse_id
          AND r.race_date < :race_date
          AND re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        ORDER BY r.race_date DESC
        LIMIT :lim
    """)
    rows = db.execute(sql, {
        "horse_id": horse_id,
        "race_date": current_race_date,
        "lim": limit,
    }).mappings().all()

    result = []
    for row in rows:
        venue = VENUE_NAMES.get(row["venue_code"], row["venue_code"])
        track = TRACK_LABELS.get(row["track_type"], "")
        cond = COND_LABELS.get(row["track_cond"], "")
        style = _detect_running_style(
            row["corner_1"], row["corner_2"], row["corner_3"], row["corner_4"],
            row["horse_count"],
        )
        # 通過順をテキスト化（例: "3-3-2-1"）
        corners = [row["corner_1"], row["corner_2"], row["corner_3"], row["corner_4"]]
        corner_text = "-".join(str(c) for c in corners if c is not None and c > 0) or None
        result.append({
            "race_date":    str(row["race_date"]),
            "race_name":    row["race_name"],
            "venue":        venue,
            "distance":     row["distance"],
            "track":        track,
            "cond":         cond,
            "horse_count":  row["horse_count"],
            "grade":        row["grade"],
            "horse_num":    row["horse_num"],
            "popularity":   row["popularity"],
            "finish_order": row["finish_order"],
            "finish_time":  row["finish_time"],
            "last_3f":      row["last_3f"],
            "weight_carry": float(row["weight_carry"]) if row["weight_carry"] else None,
            "horse_weight": row["horse_weight"],
            "weight_diff":  row["weight_diff"],
            "odds_win":     float(row["odds_win"]) if row["odds_win"] else None,
            "margin":       margin_to_text(row["margin"]),
            "corner_text":  corner_text,
            "speed_index":  float(row["speed_index"]) if row["speed_index"] else None,
            "jockey_name":  row["jockey_name"],
            "running_style": style,
        })
    return result


def _get_training_data(db: Session, horse_id: int | None, race_id: int | None) -> list[dict]:
    """指定馬の調教データを取得（最終週〜一週前）"""
    if not horse_id:
        return []

    sql = text("""
        SELECT
            training_date,
            weeks_before,
            course_type,
            distance,
            lap_time,
            last_3f,
            last_1f,
            rank,
            note
        FROM training_times
        WHERE horse_id = :horse_id
          AND (race_id = :race_id OR race_id IS NULL)
        ORDER BY training_date DESC
        LIMIT 5
    """)
    rows = db.execute(sql, {"horse_id": horse_id, "race_id": race_id}).mappings().all()

    course_labels = {1: "坂路", 2: "W", 3: "芝", 4: "ダ", 5: "プール", 6: "障害"}
    result = []
    for row in rows:
        result.append({
            "training_date": str(row["training_date"]),
            "weeks_before":  row["weeks_before"],
            "course_type":   course_labels.get(row["course_type"], str(row["course_type"])) if row["course_type"] else None,
            "distance":      row["distance"],
            "lap_time":      row["lap_time"],
            "last_3f":       row["last_3f"],
            "last_1f":       row["last_1f"],
            "rank":          row["rank"],
            "note":          row["note"],
        })
    return result


@router.get("/{race_key}/entries", response_model=list[dict])
def get_race_entries(race_key: str, db: Session = Depends(get_db)):
    """出走馬一覧（血統・過去走・脚質含む）を返す"""
    validate_race_key(race_key)
    race = db.query(Race).filter(Race.race_key == race_key).first()
    if not race:
        raise HTTPException(status_code=404, detail="レースが見つかりません")

    entries = (
        db.query(RaceEntry)
        .options(
            joinedload(RaceEntry.horse),
            joinedload(RaceEntry.jockey),
            joinedload(RaceEntry.trainer),
        )
        .filter(RaceEntry.race_id == race.id)
        .order_by(RaceEntry.horse_num)
        .all()
    )

    # odds_win=0（未確定）の場合、odds_snapshotsから最新オッズを取得
    entry_ids = [e.id for e in entries]
    snapshot_odds_map: dict[int, dict] = {}
    if entry_ids:
        sql = text("""
            SELECT DISTINCT ON (os.entry_id)
                os.entry_id, os.odds_win, os.odds_place_min, os.odds_place_max
            FROM odds_snapshots os
            WHERE os.entry_id = ANY(:ids) AND os.odds_win > 0
            ORDER BY os.entry_id, os.snapshot_type DESC
        """)
        for row in db.execute(sql, {"ids": entry_ids}).mappings():
            snapshot_odds_map[row["entry_id"]] = {
                "odds_win": float(row["odds_win"]),
                "odds_place_min": float(row["odds_place_min"]) if row["odds_place_min"] else None,
                "odds_place_max": float(row["odds_place_max"]) if row["odds_place_max"] else None,
            }

    # 前走の騎手IDを調べるための一括クエリ
    horse_ids = [e.horse_id for e in entries if e.horse_id]
    prev_jockey_map: dict[int, int | None] = {}
    if horse_ids:
        sql = text("""
            SELECT DISTINCT ON (re.horse_id)
                re.horse_id, re.jockey_id
            FROM race_entries re
            JOIN races r ON r.id = re.race_id
            WHERE re.horse_id = ANY(:ids)
              AND r.race_date < :race_date
            ORDER BY re.horse_id, r.race_date DESC
        """)
        for row in db.execute(sql, {"ids": horse_ids, "race_date": race.race_date}).mappings():
            prev_jockey_map[row["horse_id"]] = row["jockey_id"]

    # 前走日付を調べる（レース間隔算出用）
    prev_date_map: dict[int, date] = {}
    if horse_ids:
        sql = text("""
            SELECT DISTINCT ON (re.horse_id)
                re.horse_id, r.race_date
            FROM race_entries re
            JOIN races r ON r.id = re.race_id
            WHERE re.horse_id = ANY(:ids)
              AND r.race_date < :race_date
            ORDER BY re.horse_id, r.race_date DESC
        """)
        for row in db.execute(sql, {"ids": horse_ids, "race_date": race.race_date}).mappings():
            prev_date_map[row["horse_id"]] = row["race_date"]

    # 過去5走を一括取得（N+1クエリ防止）
    past_races_map: dict[int, list[dict]] = {}
    training_map: dict[int, list[dict]] = {}
    if horse_ids:
        for hid in horse_ids:
            past_races_map[hid] = []
        # 全馬の過去走を一度に取得
        for hid in horse_ids:
            past_races_map[hid] = _get_past_races(db, hid, race.race_date, limit=5)
        # 調教データも一括（horse_idがある馬のみ）
        if hasattr(race, 'id'):
            for hid in horse_ids:
                training_map[hid] = _get_training_data(db, hid, race.id) if hid else []

    result = []
    for e in entries:
        # 脚質判定
        style = _detect_running_style(e.corner_1, e.corner_2, e.corner_3, e.corner_4, race.horse_count)

        # 騎手乗り替わり判定
        jockey_change = False
        if e.horse_id and e.jockey_id:
            prev_jid = prev_jockey_map.get(e.horse_id)
            if prev_jid is not None and prev_jid != e.jockey_id:
                jockey_change = True

        # レース間隔（日数）
        interval_days: int | None = None
        if e.horse_id:
            prev_d = prev_date_map.get(e.horse_id)
            if prev_d:
                interval_days = (race.race_date - prev_d).days

        # 血統
        h = e.horse
        father = h.father_name if h else None
        mother_father = h.mother_father if h else None
        mother_name = h.mother_name if h else None

        # 過去5走（バッチ取得済み）
        past_races = past_races_map.get(e.horse_id, []) if e.horse_id else []

        # 調教データ（バッチ取得済み）
        training = training_map.get(e.horse_id, []) if e.horse_id else []

        # 通算成績
        total_wins = h.total_wins if h else None
        total_races_count = h.total_races if h else None
        total_earnings = h.total_earnings if h else None

        # 通過順テキスト（今走）
        corners = [e.corner_1, e.corner_2, e.corner_3, e.corner_4]
        corner_text = "-".join(str(c) for c in corners if c is not None and c > 0) or None

        # 騎手所属
        jockey_belong = e.jockey.belong_code if e.jockey else None
        is_foreign_jockey = jockey_belong == 4

        result.append({
            "horse_num":      e.horse_num,
            "frame_num":      e.frame_num,
            "horse_name":     h.name_kana if h else None,
            "horse_name_eng": h.name_eng if h else None,
            "horse_id":       e.horse_id,
            "jockey_name":    e.jockey.name_kanji if e.jockey else None,
            "jockey_id":      e.jockey_id,
            "trainer_name":   e.trainer.name_kanji if e.trainer else None,
            "trainer_id":     e.trainer_id,
            "age":            e.age,
            "sex":            e.sex,
            "weight_carry":   float(e.weight_carry) if e.weight_carry else None,
            "horse_weight":   e.horse_weight,
            "weight_diff":    e.weight_diff,
            "odds_win":       (float(e.odds_win) if e.odds_win is not None and float(e.odds_win) > 0
                              else snapshot_odds_map.get(e.id, {}).get("odds_win")),
            "odds_place_min": (float(e.odds_place_min) if e.odds_place_min is not None and float(e.odds_place_min) > 0
                              else snapshot_odds_map.get(e.id, {}).get("odds_place_min")),
            "odds_place_max": (float(e.odds_place_max) if e.odds_place_max is not None and float(e.odds_place_max) > 0
                              else snapshot_odds_map.get(e.id, {}).get("odds_place_max")),
            "popularity":     e.popularity,
            "finish_order":   e.finish_order,
            "finish_time":    e.finish_time,
            "last_3f":        e.last_3f,
            "margin_code":    e.margin,                  # 着差コード（数値）
            "margin":         margin_to_text(e.margin),  # 着差テキスト
            "corner_text":    corner_text,
            "speed_index":    float(e.speed_index) if e.speed_index else None,
            "abnormal_code":  e.abnormal_code,
            # 血統
            "father":         father,
            "mother_father":  mother_father,
            "mother_name":    mother_name,
            # 脚質・状態
            "running_style":  style,
            "jockey_change":  jockey_change,
            "is_foreign_jockey": is_foreign_jockey,
            "interval_days":  interval_days,
            # 通算成績
            "total_wins":     total_wins,
            "total_races":    total_races_count,
            "total_record":   f"{total_wins}-{(total_races_count or 0) - (total_wins or 0)}" if total_wins is not None else None,
            "total_earnings": total_earnings,
            # 過去走・調教
            "past_races":     past_races,
            "training":       training,
        })
    return result


@router.get("/{race_key}/laps")
def get_race_laps(race_key: str, db: Session = Depends(get_db)):
    """レースのラップタイムとペース分析を返す"""
    race = db.query(Race).filter(Race.race_key == race_key).first()
    if not race:
        raise HTTPException(status_code=404, detail="レースが見つかりません")

    laps = (
        db.query(RaceLap)
        .filter(RaceLap.race_id == race.id)
        .order_by(RaceLap.hallon_order)
        .all()
    )

    lap_data = [{"order": lap.hallon_order, "time": lap.lap_time} for lap in laps]

    # ペース分析
    pace_analysis = None
    if len(lap_data) >= 6:
        # 前半3F・後半3F
        first_3f = sum(l["time"] for l in lap_data[:3] if l["time"])
        last_3f = sum(l["time"] for l in lap_data[-3:] if l["time"])
        if first_3f > 0 and last_3f > 0:
            pci = round(first_3f / last_3f * 100, 1) if last_3f > 0 else None
            if pci:
                if pci >= 105:
                    pace_label = "H"  # ハイペース
                elif pci <= 95:
                    pace_label = "S"  # スローペース
                else:
                    pace_label = "M"  # ミドルペース
            else:
                pace_label = None
            pace_analysis = {
                "first_3f": first_3f,
                "last_3f": last_3f,
                "pci": pci,
                "pace_label": pace_label,
            }

    return {
        "race_key": race_key,
        "distance": race.distance,
        "laps": lap_data,
        "pace_analysis": pace_analysis,
    }


@router.get("/{race_key}/payouts")
def get_race_payouts(race_key: str, db: Session = Depends(get_db)):
    """レースの払戻情報を返す"""
    race = db.query(Race).filter(Race.race_key == race_key).first()
    if not race:
        raise HTTPException(status_code=404, detail="レースが見つかりません")

    payouts = db.query(Payout).filter(Payout.race_id == race.id).order_by(Payout.bet_type, Payout.popularity).all()

    bet_labels = {1: "単勝", 2: "複勝", 3: "枠連", 4: "馬連", 5: "ワイド", 6: "馬単", 7: "三連複", 8: "三連単"}
    result: dict[str, list] = {}
    for p in payouts:
        label = bet_labels.get(p.bet_type, str(p.bet_type))
        if label not in result:
            result[label] = []
        result[label].append({
            "combination": p.combination,
            "payout": p.payout,
            "popularity": p.popularity,
        })
    return {"race_key": race_key, "payouts": result}


# snapshot_type → ラベル
_SNAPSHOT_LABELS = {
    1: "前日9時",
    2: "前日17時",
    3: "当日発売中",
    4: "締切直前",
    5: "確定",
}


@router.get("/{race_key}/odds", response_model=OddsTimelineResponse)
def get_race_odds(race_key: str, db: Session = Depends(get_db)):
    """
    指定レースのオッズ推移データを返す。
    馬番 × スナップショット種別 のマトリクスで、
    単勝/複勝オッズの時系列変化を確認できる。
    """
    validate_race_key(race_key)
    race = db.query(Race).filter(Race.race_key == race_key).first()
    if not race:
        raise HTTPException(status_code=404, detail="レースが見つかりません")

    # race_id に紐づく出走馬の全オッズスナップショットを取得
    sql = text("""
        SELECT
            re.horse_num,
            os.snapshot_type,
            os.odds_win,
            os.odds_place_min,
            os.odds_place_max,
            os.recorded_at
        FROM odds_snapshots os
        JOIN race_entries re ON re.id = os.entry_id
        WHERE re.race_id = :race_id
        ORDER BY re.horse_num, os.snapshot_type
    """)
    rows = db.execute(sql, {"race_id": race.id}).mappings().all()

    snapshots = []
    for row in rows:
        st = row["snapshot_type"]
        snapshots.append(OddsSnapshotItem(
            horse_num=row["horse_num"],
            snapshot_type=st,
            snapshot_label=_SNAPSHOT_LABELS.get(st, f"種別{st}"),
            odds_win=float(row["odds_win"]) if row["odds_win"] else None,
            odds_place_min=float(row["odds_place_min"]) if row["odds_place_min"] else None,
            odds_place_max=float(row["odds_place_max"]) if row["odds_place_max"] else None,
            recorded_at=str(row["recorded_at"]) if row["recorded_at"] else None,
        ))

    return OddsTimelineResponse(race_key=race_key, snapshots=snapshots)
