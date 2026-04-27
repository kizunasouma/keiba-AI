"""
JV-DataのDB保存サービス（v2: 高速バルクUPSERT版）

【高速化ポイント】
1. IdCache: race_key/blood_reg_num/jockey_code/trainer_code → id をメモリキャッシュ
2. RecordBuffer: レコードタイプ別に1000件単位でバッファリング
3. バルクUPSERT: INSERT ... VALUES (...), (...) ... ON CONFLICT DO UPDATE
4. commit頻度: 5000件ごと
"""
import logging
from datetime import datetime, date as date_type
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.race import (
    Race, Horse, Jockey, Trainer,
    RaceEntry, RaceLap, Payout, HorseWeight, TrainingTime,
    PedigreeLineage, JVLinkSyncLog, OddsSnapshot,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# インメモリキャッシュ（自然キー → DB内部ID）
# ---------------------------------------------------------------------------

class IdCache:
    """SELECTクエリを排除するためのインメモリキャッシュ"""

    def __init__(self):
        self.race: dict[str, int] = {}       # race_key → races.id
        self.horse: dict[str, int] = {}      # blood_reg_num → horses.id
        self.jockey: dict[str, int] = {}     # jockey_code → jockeys.id
        self.trainer: dict[str, int] = {}    # trainer_code → trainers.id


def preload_cache(db: Session) -> IdCache:
    """同期開始時にDB既存データからキャッシュをプレロード"""
    cache = IdCache()
    for row in db.query(Race.race_key, Race.id).all():
        cache.race[row[0]] = row[1]
    for row in db.query(Horse.blood_reg_num, Horse.id).all():
        cache.horse[row[0]] = row[1]
    for row in db.query(Jockey.jockey_code, Jockey.id).all():
        cache.jockey[row[0]] = row[1]
    for row in db.query(Trainer.trainer_code, Trainer.id).all():
        cache.trainer[row[0]] = row[1]
    logger.info(
        f"キャッシュプレロード完了: races={len(cache.race)}, "
        f"horses={len(cache.horse)}, jockeys={len(cache.jockey)}, "
        f"trainers={len(cache.trainer)}"
    )
    return cache


# ---------------------------------------------------------------------------
# レコードバッファ
# ---------------------------------------------------------------------------

class RecordBuffer:
    """レコードタイプ別バッファ。batch_size に達したらフラッシュ対象を返す。"""

    def __init__(self, batch_size: int = 1000):
        self.batch_size = batch_size
        self._bufs: dict[str, list[dict]] = {}

    def add(self, record: dict) -> str | None:
        rtype = record.get("_record_type", "")
        buf = self._bufs.setdefault(rtype, [])
        buf.append(record)
        if len(buf) >= self.batch_size:
            return rtype
        return None

    def take(self, rtype: str) -> list[dict]:
        records = self._bufs.get(rtype, [])
        self._bufs[rtype] = []
        return records

    def take_all(self) -> dict[str, list[dict]]:
        result = {k: v for k, v in self._bufs.items() if v}
        self._bufs = {}
        return result


# ---------------------------------------------------------------------------
# フラッシュ順序（依存関係: マスタ→RA→SE）
# ---------------------------------------------------------------------------
FLUSH_ORDER = ["UM", "KS", "CH", "BT", "RA", "SE", "HR", "O1", "HC", "WC", "WH", "WE"]

_BULK_SAVERS: dict[str, Any] = {}  # 下で登録


def flush_in_order(db: Session, buffer: RecordBuffer, cache: IdCache) -> tuple[int, int]:
    """依存順にバッファをフラッシュ。(saved, skipped) を返す。"""
    saved = skipped = 0
    for rtype in FLUSH_ORDER:
        batch = buffer.take(rtype)
        if not batch:
            continue
        saver = _BULK_SAVERS.get(rtype)
        if saver is None:
            skipped += len(batch)
            continue
        s, sk = saver(db, batch, cache)
        saved += s
        skipped += sk
    # FLUSH_ORDER に含まれない型はスキップ
    for rtype, batch in buffer.take_all().items():
        skipped += len(batch)
    return saved, skipped


# ---------------------------------------------------------------------------
# バルクUPSERT: RA レコード
# ---------------------------------------------------------------------------

def _save_ra_bulk(db: Session, records: list[dict], cache: IdCache) -> tuple[int, int]:
    values_list = []
    laps_by_key: dict[str, list[int]] = {}
    now = datetime.now()

    for r in records:
        race_key = r.get("race_key")
        if not race_key:
            continue
        values_list.append(dict(
            race_key=race_key,
            race_date=_to_date(r.get("race_date")),
            venue_code=r.get("venue_code"),
            kai=r.get("kai") or 0,
            nichi=r.get("nichi") or 0,
            race_num=r.get("race_num") or 0,
            race_name=r.get("race_name"),
            race_name_sub=r.get("race_name_sub"),
            grade=r.get("grade"),
            distance=r.get("distance") or 0,
            track_type=r.get("track_type") or 0,
            track_dir=r.get("track_dir"),
            horse_count=r.get("horse_count"),
            weather=r.get("weather"),
            track_cond=r.get("track_cond"),
            condition_code=r.get("condition_code"),
            is_female_only=r.get("is_female_only", False),
            is_mixed=r.get("is_mixed", False),
            is_handicap=r.get("is_handicap", False),
            is_special=False,
            start_time=r.get("start_time"),
            prize_1st=r.get("prize_1st"),
            prize_2nd=r.get("prize_2nd"),
            prize_3rd=r.get("prize_3rd"),
            created_at=now,
            updated_at=now,
        ))
        laps = r.get("laps", [])
        if laps:
            laps_by_key[race_key] = laps

    if not values_list:
        return 0, len(records)

    values_list = _dedup_values(values_list, "race_key")

    for chunk in _chunks(values_list, 1000):
        stmt = insert(Race).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["race_key"],
            set_={
                "race_name":   stmt.excluded.race_name,
                "grade":       stmt.excluded.grade,
                "horse_count": stmt.excluded.horse_count,
                "weather":     stmt.excluded.weather,
                "track_cond":  stmt.excluded.track_cond,
                "start_time":  stmt.excluded.start_time,
                "prize_1st":   stmt.excluded.prize_1st,
                "updated_at":  now,
            },
        )
        db.execute(stmt)

    # キャッシュ更新: UPSERTしたrace_keyのidを一括取得
    keys = [v["race_key"] for v in values_list]
    for row in db.query(Race.race_key, Race.id).filter(Race.race_key.in_(keys)).all():
        cache.race[row[0]] = row[1]

    # ラップタイム一括保存
    lap_values = []
    for race_key, laps in laps_by_key.items():
        race_id = cache.race.get(race_key)
        if not race_id:
            continue
        for i, lap_time in enumerate(laps, start=1):
            lap_values.append(dict(race_id=race_id, hallon_order=i, lap_time=lap_time))
    if lap_values:
        for chunk in _chunks(lap_values, 1000):
            lap_stmt = insert(RaceLap).values(chunk)
            lap_stmt = lap_stmt.on_conflict_do_update(
                constraint="uq_lap",
                set_={"lap_time": lap_stmt.excluded.lap_time},
            )
            db.execute(lap_stmt)

    return len(values_list), len(records) - len(values_list)


# ---------------------------------------------------------------------------
# バルクUPSERT: SE レコード（最大のボリューム）
# ---------------------------------------------------------------------------

def _save_se_bulk(db: Session, records: list[dict], cache: IdCache) -> tuple[int, int]:
    values_list = []
    skipped = 0
    now = datetime.now()

    for r in records:
        race_key = r.get("race_key")
        horse_num = r.get("horse_num")
        if not race_key or not horse_num:
            skipped += 1
            continue

        # キャッシュからid解決（SELECTゼロ）
        race_id = cache.race.get(race_key)
        if race_id is None:
            # キャッシュミス: フォールバック
            race = db.query(Race.id).filter_by(race_key=race_key).first()
            if race:
                race_id = race[0]
                cache.race[race_key] = race_id
            else:
                skipped += 1
                continue

        horse_id = cache.horse.get(r.get("blood_reg_num") or "")
        jockey_id = cache.jockey.get(r.get("jockey_code") or "")
        trainer_id = cache.trainer.get(r.get("trainer_code") or "")

        values_list.append(dict(
            race_id=race_id,
            horse_id=horse_id,
            jockey_id=jockey_id,
            trainer_id=trainer_id,
            blood_reg_num=r.get("blood_reg_num") or None,
            jockey_code=r.get("jockey_code") or None,
            trainer_code=r.get("trainer_code") or None,
            horse_num=horse_num,
            frame_num=r.get("frame_num") or 0,
            weight_carry=r.get("weight_carry"),
            age=r.get("age"),
            sex=r.get("sex"),
            horse_weight=r.get("horse_weight"),
            weight_diff=r.get("weight_diff"),
            odds_win=r.get("odds_win"),
            odds_place_min=r.get("odds_place_min"),
            odds_place_max=r.get("odds_place_max"),
            popularity=r.get("popularity"),
            finish_order=r.get("finish_order"),
            finish_time=r.get("finish_time"),
            last_3f=r.get("last_3f"),
            margin=r.get("margin"),
            corner_1=r.get("corner_1"),
            corner_2=r.get("corner_2"),
            corner_3=r.get("corner_3"),
            corner_4=r.get("corner_4"),
            abnormal_code=r.get("abnormal_code"),
            # SE拡張フィールド（v4追加）
            blinker_code=r.get("blinker_code"),
            prev_jockey_code=r.get("prev_jockey_code"),
            prev_weight_carry=r.get("prev_weight_carry"),
            apprentice_code=r.get("apprentice_code"),
            belong_region=r.get("belong_region"),
            created_at=now,
            updated_at=now,
        ))

    if not values_list:
        return 0, skipped

    values_list = _dedup_values_multi(values_list, ["race_id", "horse_num"])

    # バルクUPSERT（チャンク分割）
    saved = 0
    for chunk in _chunks(values_list, 1000):
        stmt = insert(RaceEntry).values(chunk)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_race_horse",
            set_={
                "horse_id":     stmt.excluded.horse_id,
                "jockey_id":    stmt.excluded.jockey_id,
                "trainer_id":   stmt.excluded.trainer_id,
                "blood_reg_num": stmt.excluded.blood_reg_num,
                "jockey_code":  stmt.excluded.jockey_code,
                "trainer_code": stmt.excluded.trainer_code,
                "finish_order": stmt.excluded.finish_order,
                "finish_time":  stmt.excluded.finish_time,
                "last_3f":      stmt.excluded.last_3f,
                "odds_win":     stmt.excluded.odds_win,
                "odds_place_min": stmt.excluded.odds_place_min,
                "odds_place_max": stmt.excluded.odds_place_max,
                "popularity":   stmt.excluded.popularity,
                "horse_weight": stmt.excluded.horse_weight,
                "weight_diff":  stmt.excluded.weight_diff,
                "corner_1":     stmt.excluded.corner_1,
                "corner_2":     stmt.excluded.corner_2,
                "corner_3":     stmt.excluded.corner_3,
                "corner_4":     stmt.excluded.corner_4,
                # SE拡張フィールド（v4追加）
                "blinker_code":     stmt.excluded.blinker_code,
                "prev_jockey_code": stmt.excluded.prev_jockey_code,
                "prev_weight_carry": stmt.excluded.prev_weight_carry,
                "apprentice_code":  stmt.excluded.apprentice_code,
                "belong_region":    stmt.excluded.belong_region,
                "updated_at":   now,
            },
        )
        db.execute(stmt)
        saved += len(chunk)

    return saved, skipped


# ---------------------------------------------------------------------------
# バルクUPSERT: UM レコード
# ---------------------------------------------------------------------------

def _save_um_bulk(db: Session, records: list[dict], cache: IdCache) -> tuple[int, int]:
    values_list = []
    now = datetime.now()

    for r in records:
        brn = r.get("blood_reg_num")
        if not brn:
            continue
        values_list.append(dict(
            blood_reg_num=brn,
            name_kana=r.get("name_kana"),
            name_eng=r.get("name_eng"),
            birth_date=_to_date(r.get("birth_date")),
            sex=r.get("sex"),
            coat_color=r.get("coat_color"),
            father_name=r.get("father_name"),
            father_code=r.get("father_code"),
            mother_name=r.get("mother_name"),
            mother_code=r.get("mother_code"),
            mother_father=r.get("mother_father"),
            mother_father_code=r.get("mother_father_code"),
            producer_name=r.get("producer_name"),
            area_name=r.get("area_name"),
            owner_name=r.get("owner_name"),
            total_wins=r.get("total_wins") or 0,
            total_races=r.get("total_races") or 0,
            total_earnings=r.get("total_earnings") or 0,
            created_at=now,
            updated_at=now,
        ))

    if not values_list:
        return 0, len(records)

    values_list = _dedup_values(values_list, "blood_reg_num")

    for chunk in _chunks(values_list, 1000):
        stmt = insert(Horse).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["blood_reg_num"],
            set_={
                "name_kana":      stmt.excluded.name_kana,
                "owner_name":     stmt.excluded.owner_name,
                "total_wins":     stmt.excluded.total_wins,
                "total_races":    stmt.excluded.total_races,
                "total_earnings": stmt.excluded.total_earnings,
                "updated_at":     now,
            },
        )
        db.execute(stmt)

    brns = [v["blood_reg_num"] for v in values_list]
    for row in db.query(Horse.blood_reg_num, Horse.id).filter(Horse.blood_reg_num.in_(brns)).all():
        cache.horse[row[0]] = row[1]

    return len(values_list), len(records) - len(values_list)


# ---------------------------------------------------------------------------
# バルクUPSERT: KS レコード
# ---------------------------------------------------------------------------

def _save_ks_bulk(db: Session, records: list[dict], cache: IdCache) -> tuple[int, int]:
    values_list = []
    now = datetime.now()

    for r in records:
        jc = r.get("jockey_code")
        if not jc:
            continue
        values_list.append(dict(
            jockey_code=jc,
            name_kanji=r.get("name_kanji"),
            name_kana=r.get("name_kana"),
            birth_date=_to_date(r.get("birth_date")),
            belong_code=r.get("belong_code"),
            total_1st=r.get("total_1st") or 0,
            total_2nd=r.get("total_2nd") or 0,
            total_3rd=r.get("total_3rd") or 0,
            total_races=r.get("total_races") or 0,
            created_at=now,
            updated_at=now,
        ))

    if not values_list:
        return 0, len(records)

    values_list = _dedup_values(values_list, "jockey_code")

    for chunk in _chunks(values_list, 1000):
        stmt = insert(Jockey).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["jockey_code"],
            set_={
                "name_kanji":  stmt.excluded.name_kanji,
                "total_1st":   stmt.excluded.total_1st,
                "total_2nd":   stmt.excluded.total_2nd,
                "total_3rd":   stmt.excluded.total_3rd,
                "total_races": stmt.excluded.total_races,
                "updated_at":  now,
            },
        )
        db.execute(stmt)

    codes = [v["jockey_code"] for v in values_list]
    for row in db.query(Jockey.jockey_code, Jockey.id).filter(Jockey.jockey_code.in_(codes)).all():
        cache.jockey[row[0]] = row[1]

    return len(values_list), len(records) - len(values_list)


# ---------------------------------------------------------------------------
# バルクUPSERT: CH レコード
# ---------------------------------------------------------------------------

def _save_ch_bulk(db: Session, records: list[dict], cache: IdCache) -> tuple[int, int]:
    values_list = []
    now = datetime.now()

    for r in records:
        tc = r.get("trainer_code")
        if not tc:
            continue
        values_list.append(dict(
            trainer_code=tc,
            name_kanji=r.get("name_kanji"),
            name_kana=r.get("name_kana"),
            belong_code=r.get("belong_code"),
            total_1st=r.get("total_1st") or 0,
            total_races=r.get("total_races") or 0,
            created_at=now,
            updated_at=now,
        ))

    if not values_list:
        return 0, len(records)

    values_list = _dedup_values(values_list, "trainer_code")

    for chunk in _chunks(values_list, 1000):
        stmt = insert(Trainer).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["trainer_code"],
            set_={
                "name_kanji":  stmt.excluded.name_kanji,
                "total_1st":   stmt.excluded.total_1st,
                "total_races": stmt.excluded.total_races,
                "updated_at":  now,
            },
        )
        db.execute(stmt)

    codes = [v["trainer_code"] for v in values_list]
    for row in db.query(Trainer.trainer_code, Trainer.id).filter(Trainer.trainer_code.in_(codes)).all():
        cache.trainer[row[0]] = row[1]

    return len(values_list), len(records) - len(values_list)


# ---------------------------------------------------------------------------
# バルクUPSERT: WH レコード
# ---------------------------------------------------------------------------

def _save_wh_bulk(db: Session, records: list[dict], cache: IdCache) -> tuple[int, int]:
    values_list = []
    skipped = 0
    now = datetime.now()

    for r in records:
        race_key = r.get("race_key")
        horse_num = r.get("horse_num")
        if not race_key or not horse_num:
            skipped += 1
            continue
        race_id = cache.race.get(race_key)
        if not race_id:
            skipped += 1
            continue
        values_list.append(dict(
            race_id=race_id,
            horse_num=horse_num,
            weight=r.get("weight"),
            weight_diff=r.get("weight_diff"),
            announced_at=now,
        ))

    if not values_list:
        return 0, skipped

    for chunk in _chunks(values_list, 1000):
        stmt = insert(HorseWeight).values(chunk)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_weight_race_horse",
            set_={"weight": stmt.excluded.weight, "weight_diff": stmt.excluded.weight_diff},
        )
        db.execute(stmt)

    return len(values_list), skipped


# ---------------------------------------------------------------------------
# WE レコード（調教タイム）— バルクINSERT（重複は無視）
# ---------------------------------------------------------------------------

def _save_we_bulk(db: Session, records: list[dict], cache: IdCache) -> tuple[int, int]:
    skipped = 0
    now = datetime.now()
    rows = []

    for r in records:
        brn = r.get("blood_reg_num")
        training_date = r.get("training_date")
        if not brn or not training_date:
            skipped += 1
            continue
        horse_id = cache.horse.get(brn)
        if not horse_id:
            skipped += 1
            continue
        rows.append(TrainingTime(
            horse_id=horse_id,
            training_date=_to_date(training_date),
            course_type=r.get("course_type"),
            distance=r.get("distance"),
            lap_time=r.get("lap_time"),
            last_3f=r.get("last_3f"),
            last_1f=r.get("last_1f"),
            rank=r.get("rank"),
            created_at=now,
        ))

    if rows:
        db.add_all(rows)

    return len(rows), skipped


# ---------------------------------------------------------------------------
# バルクUPSERT: HR レコード（払戻）
# ---------------------------------------------------------------------------

def _save_hr_bulk(db: Session, records: list[dict], cache: IdCache) -> tuple[int, int]:
    values_list = []
    skipped = 0
    now = datetime.now()

    for r in records:
        race_key = r.get("race_key")
        if not race_key:
            skipped += 1
            continue
        race_id = cache.race.get(race_key)
        if race_id is None:
            race = db.query(Race.id).filter_by(race_key=race_key).first()
            if race:
                race_id = race[0]
                cache.race[race_key] = race_id
            else:
                skipped += 1
                continue

        for p in r.get("payouts", []):
            values_list.append(dict(
                race_id=race_id,
                bet_type=p["bet_type"],
                combination=p["combination"],
                payout=p["payout"],
                popularity=p.get("popularity"),
                created_at=now,
            ))

    if not values_list:
        return 0, skipped

    saved = 0
    for chunk in _chunks(values_list, 1000):
        stmt = insert(Payout).values(chunk)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_payout",
            set_={
                "payout": stmt.excluded.payout,
                "popularity": stmt.excluded.popularity,
            },
        )
        db.execute(stmt)
        saved += len(chunk)

    return saved, skipped


# ---------------------------------------------------------------------------
# バルクUPSERT: BT レコード（系統情報）
# ---------------------------------------------------------------------------

def _save_bt_bulk(db: Session, records: list[dict], cache: IdCache) -> tuple[int, int]:
    values_list = []
    now = datetime.now()
    for r in records:
        brn = r.get("breed_reg_num")
        if not brn:
            continue
        values_list.append(dict(
            breed_reg_num=brn,
            lineage_id=r.get("lineage_id"),
            lineage_name=r.get("lineage_name"),
            created_at=now,
            updated_at=now,
        ))
    if not values_list:
        return 0, len(records)

    values_list = _dedup_values(values_list, "breed_reg_num")

    for chunk in _chunks(values_list, 1000):
        stmt = insert(PedigreeLineage).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["breed_reg_num"],
            set_={
                "lineage_id": stmt.excluded.lineage_id,
                "lineage_name": stmt.excluded.lineage_name,
                "updated_at": now,
            },
        )
        db.execute(stmt)

    return len(values_list), len(records) - len(values_list)


# ---------------------------------------------------------------------------
# バルクINSERT: HC レコード（坂路調教）/ WC レコード（ウッドチップ調教）
# → training_times テーブルに��存（course_type で区別）
# ---------------------------------------------------------------------------

def _save_training_bulk(db: Session, records: list[dict], cache: IdCache) -> tuple[int, int]:
    """HC/WC共通の調教データ保存"""
    skipped = 0
    now = datetime.now()
    rows = []
    for r in records:
        brn = r.get("blood_reg_num")
        td = r.get("training_date")
        if not brn or not td:
            skipped += 1
            continue
        horse_id = cache.horse.get(brn)
        if not horse_id:
            skipped += 1
            continue
        rows.append(TrainingTime(
            horse_id=horse_id,
            training_date=_to_date(td),
            course_type=r.get("course_type"),
            distance=r.get("distance"),
            lap_time=r.get("lap_time"),
            last_3f=r.get("last_3f"),
            last_1f=r.get("last_1f"),
            created_at=now,
        ))
    if rows:
        db.add_all(rows)
    return len(rows), skipped


# ---------------------------------------------------------------------------
# バルクUPSERT: O1 レコード（単勝・複勝オッズ）
# → odds_snapshots テーブルに保存
# ---------------------------------------------------------------------------

def _save_o1_bulk(db: Session, records: list[dict], cache: IdCache) -> tuple[int, int]:
    """O1レコード（単勝・複勝オッズ）をバルクUPSERTで保存"""
    skipped = 0
    saved = 0
    now = datetime.now()

    # entry_id 解決用: race_key + horse_num → entry_id のキャッシュ（バッチ内）
    entry_cache: dict[str, int] = {}

    for r in records:
        race_key = r.get("race_key")
        snapshot_type = r.get("snapshot_type")
        odds_entries = r.get("odds_entries", [])
        if not race_key or not odds_entries:
            skipped += 1
            continue

        # race_id を取得
        race_id = cache.race.get(race_key)
        if race_id is None:
            race = db.query(Race.id).filter_by(race_key=race_key).first()
            if race:
                race_id = race[0]
                cache.race[race_key] = race_id
            else:
                skipped += 1
                continue

        # entry_id が未キャッシュなら一括取得
        cache_prefix = f"{race_key}:"
        if not any(k.startswith(cache_prefix) for k in entry_cache):
            for row in db.query(RaceEntry.horse_num, RaceEntry.id).filter(
                RaceEntry.race_id == race_id
            ).all():
                entry_cache[f"{race_key}:{row[0]}"] = row[1]

        # 各馬のオッズをUPSERT用に変換
        values_list = []
        for oe in odds_entries:
            horse_num = oe.get("horse_num")
            if not horse_num:
                continue
            entry_id = entry_cache.get(f"{race_key}:{horse_num}")
            if not entry_id:
                continue

            # recorded_at: make_date から生成（YYYYMMDD → datetime）
            recorded_at = None
            make_date = r.get("make_date")
            if make_date and len(make_date) == 8 and make_date.isdigit():
                try:
                    recorded_at = datetime.strptime(make_date, "%Y%m%d")
                except ValueError:
                    pass

            values_list.append(dict(
                entry_id=entry_id,
                snapshot_type=snapshot_type,
                recorded_at=recorded_at or now,
                odds_win=oe.get("odds_win"),
                odds_place_min=oe.get("odds_place_min"),
                odds_place_max=oe.get("odds_place_max"),
                popularity=None,  # O1レコードには人気順が含まれないため
            ))

        if not values_list:
            skipped += 1
            continue

        # バルクUPSERT
        for chunk in _chunks(values_list, 1000):
            stmt = insert(OddsSnapshot).values(chunk)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_odds_snapshot",
                set_={
                    "odds_win": stmt.excluded.odds_win,
                    "odds_place_min": stmt.excluded.odds_place_min,
                    "odds_place_max": stmt.excluded.odds_place_max,
                    "recorded_at": stmt.excluded.recorded_at,
                },
            )
            db.execute(stmt)
            saved += len(chunk)

    return saved, skipped


# バルクセーバー登録
_BULK_SAVERS = {
    "RA": _save_ra_bulk,
    "SE": _save_se_bulk,
    "HR": _save_hr_bulk,
    "O1": _save_o1_bulk,
    "UM": _save_um_bulk,
    "KS": _save_ks_bulk,
    "CH": _save_ch_bulk,
    "BT": _save_bt_bulk,
    "HC": _save_training_bulk,
    "WC": _save_training_bulk,
    "WH": _save_wh_bulk,
    "WE": _save_we_bulk,
}


# ---------------------------------------------------------------------------
# 後方互換: 1件ずつの save_record（API等から使用）
# ---------------------------------------------------------------------------

def save_record(db: Session, record: dict) -> bool:
    """1件ずつ保存（低速だがAPI等の少量処理用に残す）"""
    rtype = record.get("_record_type")
    saver = _BULK_SAVERS.get(rtype)
    if not saver:
        return False
    try:
        cache = IdCache()
        # 簡易キャッシュ: このレコードに必要なidだけ引く
        s, _ = saver(db, [record], cache)
        return s > 0
    except Exception as e:
        logger.warning(f"save_record失敗 ({rtype}): {e}")
        return False


# ---------------------------------------------------------------------------
# JVLinkSyncLog 管理
# ---------------------------------------------------------------------------

def get_last_timestamp(db: Session, dataspec: str) -> str:
    log = db.query(JVLinkSyncLog).filter_by(dataspec=dataspec).first()
    return log.last_timestamp if log else "19860101000000"


def update_last_timestamp(db: Session, dataspec: str, timestamp: str) -> None:
    stmt = insert(JVLinkSyncLog).values(
        dataspec=dataspec,
        last_timestamp=timestamp,
        synced_at=datetime.now(),
    ).on_conflict_do_update(
        index_elements=["dataspec"],
        set_={"last_timestamp": timestamp, "synced_at": datetime.now()},
    )
    db.execute(stmt)
    db.commit()


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def _to_date(value: Any) -> date_type | None:
    if value is None:
        return None
    if isinstance(value, str) and len(value) == 10:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return None
    return value


def _chunks(lst: list, n: int):
    """リストをn件ずつのチャンクに分割"""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def _dedup_values(values_list: list[dict], key_field: str) -> list[dict]:
    """同一バッチ内の重複除去（指定キーが同じレコードは後勝ち）"""
    seen: dict[Any, int] = {}
    for i, v in enumerate(values_list):
        seen[v.get(key_field)] = i
    return [values_list[i] for i in sorted(seen.values())]


def _dedup_values_multi(values_list: list[dict], key_fields: list[str]) -> list[dict]:
    """同一バッチ内の重複除去（複数キーの組み合わせ）"""
    seen: dict[tuple, int] = {}
    for i, v in enumerate(values_list):
        key = tuple(v.get(k) for k in key_fields)
        seen[key] = i
    return [values_list[i] for i in sorted(seen.values())]
