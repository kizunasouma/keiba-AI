"""
レース・出走のPydanticスキーマ
FastAPIのリクエスト/レスポンスの型定義
"""
from datetime import date
from typing import Optional
from pydantic import BaseModel


class RaceBase(BaseModel):
    race_key: str
    race_date: date
    venue_code: str
    race_num: int
    race_name: Optional[str] = None
    race_name_sub: Optional[str] = None       # レース副題
    grade: Optional[int] = None
    distance: int
    track_type: int
    track_dir: Optional[int] = None
    weather: Optional[int] = None
    track_cond: Optional[int] = None
    condition_code: Optional[int] = None      # 競走条件コード
    horse_count: Optional[int] = None
    is_handicap: bool = False
    is_female_only: bool = False
    is_special: bool = False
    start_time: Optional[str] = None          # 発走時刻（HHMM形式）


class RaceResponse(RaceBase):
    id: int
    kai: int
    nichi: int
    prize_1st: Optional[int] = None

    class Config:
        from_attributes = True


class EntryBase(BaseModel):
    horse_num: int
    frame_num: int
    age: Optional[int] = None
    sex: Optional[int] = None
    weight_carry: Optional[float] = None
    horse_weight: Optional[int] = None
    weight_diff: Optional[int] = None
    odds_win: Optional[float] = None
    odds_place_min: Optional[float] = None
    odds_place_max: Optional[float] = None
    popularity: Optional[int] = None
    finish_order: Optional[int] = None
    finish_time: Optional[int] = None
    last_3f: Optional[int] = None
    speed_index: Optional[float] = None
    abnormal_code: Optional[int] = None       # 異常区分（0=正常, 1=取消, 2=除外, 3=中止, 4=失格）
    margin: Optional[int] = None              # 着差コード（数値）


class EntryResponse(EntryBase):
    id: int
    race_id: int
    horse_id: Optional[int] = None
    jockey_id: Optional[int] = None
    trainer_id: Optional[int] = None

    class Config:
        from_attributes = True


class RaceDetailResponse(RaceResponse):
    """レース詳細（出走馬リスト付き）"""
    entries: list[EntryResponse] = []


class OddsSnapshotItem(BaseModel):
    """オッズスナップショット（1馬・1時点）"""
    horse_num: int
    snapshot_type: int
    snapshot_label: str
    odds_win: Optional[float] = None
    odds_place_min: Optional[float] = None
    odds_place_max: Optional[float] = None
    recorded_at: Optional[str] = None


class OddsTimelineResponse(BaseModel):
    """オッズ推移レスポンス（レース単位）"""
    race_key: str
    snapshots: list[OddsSnapshotItem] = []
