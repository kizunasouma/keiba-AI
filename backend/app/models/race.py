"""
レース・出走・馬・騎手・調教師のSQLAlchemyモデル
JV-Linkのデータ構造に対応したテーブル定義

【v2 変更点 - 予想ファクター再検討後】
- races: レース条件コード・ハンデフラグ等を追加
- race_entries: 複勝オッズ・タイム指数を追加
- race_laps: ハロンラップタイムを新規追加（ペース分析用）
- odds_snapshots: オッズ時系列を新規追加（変動分析用）
- training_times: 調教詳細を拡充
"""
from datetime import datetime
from sqlalchemy import (
    BigInteger, SmallInteger, Integer, Numeric,
    String, Date, DateTime, Boolean,
    ForeignKey, UniqueConstraint, Index,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Race(Base):
    """
    レース基本情報テーブル（RAレコード対応）
    race_key = YYYYMMDD + 場コード(JJ) + 回次(KK) + 日次(HH) + レース番号(RR)
    """
    __tablename__ = "races"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # レース識別キー（16桁）
    race_key: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    race_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    venue_code: Mapped[str] = mapped_column(String(2), nullable=False)   # 01=札幌〜10=小倉
    kai: Mapped[int] = mapped_column(SmallInteger, nullable=False)        # 回次
    nichi: Mapped[int] = mapped_column(SmallInteger, nullable=False)      # 日次
    race_num: Mapped[int] = mapped_column(SmallInteger, nullable=False)   # レース番号

    # レース情報
    race_name: Mapped[str | None] = mapped_column(String(60))
    race_name_sub: Mapped[str | None] = mapped_column(String(60))
    # 1=G1,2=G2,3=G3,4=重賞,5=OP,6=3勝,7=2勝,8=1勝,9=新馬,10=未勝利
    grade: Mapped[int | None] = mapped_column(SmallInteger)
    distance: Mapped[int] = mapped_column(SmallInteger, nullable=False)   # 距離(m)
    track_type: Mapped[int] = mapped_column(SmallInteger, nullable=False) # 1=芝,2=ダート,3=障害
    track_dir: Mapped[int | None] = mapped_column(SmallInteger)           # 1=右,2=左,3=直線
    horse_count: Mapped[int | None] = mapped_column(SmallInteger)         # 出走頭数

    # 当日条件
    weather: Mapped[int | None] = mapped_column(SmallInteger)    # 1=晴〜6=小雪
    track_cond: Mapped[int | None] = mapped_column(SmallInteger) # 1=良〜4=不良

    # レース条件（期待値計算・適性分析に必要）
    condition_code: Mapped[int | None] = mapped_column(SmallInteger)
    # 2歳新馬=1, 2歳未勝利=2, 3歳未勝利=3, 1勝クラス=5, 2勝=6, 3勝=7, OP=8 等
    is_female_only: Mapped[bool] = mapped_column(Boolean, default=False)  # 牝馬限定
    is_mixed: Mapped[bool] = mapped_column(Boolean, default=False)        # 混合
    is_handicap: Mapped[bool] = mapped_column(Boolean, default=False)     # ハンデ戦
    is_special: Mapped[bool] = mapped_column(Boolean, default=False)      # 特別競走

    # 発走時刻（HHMM形式の文字列、例: "1510"）
    start_time: Mapped[str | None] = mapped_column(String(4))

    # 賞金（万円）
    prize_1st: Mapped[int | None] = mapped_column(Integer)
    prize_2nd: Mapped[int | None] = mapped_column(Integer)
    prize_3rd: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # リレーション
    entries: Mapped[list["RaceEntry"]] = relationship("RaceEntry", back_populates="race")
    payouts: Mapped[list["Payout"]] = relationship("Payout", back_populates="race")
    laps: Mapped[list["RaceLap"]] = relationship("RaceLap", back_populates="race")

    __table_args__ = (
        Index("idx_races_date", "race_date"),
        Index("idx_races_venue", "venue_code", "race_date"),
        Index("idx_races_grade", "grade"),
        Index("idx_races_track", "track_type", "distance"),
    )


class Horse(Base):
    """
    競走馬マスタテーブル（UMレコード対応）
    """
    __tablename__ = "horses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    blood_reg_num: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)  # 血統登録番号
    name_kana: Mapped[str | None] = mapped_column(String(36))
    name_eng: Mapped[str | None] = mapped_column(String(60))
    birth_date: Mapped[datetime | None] = mapped_column(Date)
    sex: Mapped[int | None] = mapped_column(SmallInteger)        # 1=牡,2=牝,3=騸
    coat_color: Mapped[int | None] = mapped_column(SmallInteger)

    # 血統（名前＋コード。コードはAIの特徴量として使いやすい）
    father_name: Mapped[str | None] = mapped_column(String(36))
    father_code: Mapped[str | None] = mapped_column(String(10))  # 父馬の血統登録番号
    mother_name: Mapped[str | None] = mapped_column(String(36))
    mother_code: Mapped[str | None] = mapped_column(String(10))  # 母馬の血統登録番号
    mother_father: Mapped[str | None] = mapped_column(String(36))
    mother_father_code: Mapped[str | None] = mapped_column(String(10))  # 母父の血統登録番号

    # 所属・所有
    producer_name: Mapped[str | None] = mapped_column(String(60))
    area_name: Mapped[str | None] = mapped_column(String(20))    # 産地
    owner_name: Mapped[str | None] = mapped_column(String(60))

    # 通算成績
    total_wins: Mapped[int] = mapped_column(SmallInteger, default=0)
    total_races: Mapped[int] = mapped_column(SmallInteger, default=0)
    total_earnings: Mapped[int] = mapped_column(Integer, default=0)  # 獲得賞金（万円）

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    entries: Mapped[list["RaceEntry"]] = relationship("RaceEntry", back_populates="horse")
    training_times: Mapped[list["TrainingTime"]] = relationship("TrainingTime", back_populates="horse")

    __table_args__ = (
        Index("idx_horses_father", "father_code"),
        Index("idx_horses_mother_father", "mother_father_code"),
    )


class Jockey(Base):
    """
    騎手マスタテーブル（KSレコード対応）
    """
    __tablename__ = "jockeys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    jockey_code: Mapped[str] = mapped_column(String(5), unique=True, nullable=False)
    name_kanji: Mapped[str | None] = mapped_column(String(20))
    name_kana: Mapped[str | None] = mapped_column(String(30))
    birth_date: Mapped[datetime | None] = mapped_column(Date)
    # 1=美浦,2=栗東,3=地方,4=外国（短期免許外国人騎手の判定に使用）
    belong_code: Mapped[int | None] = mapped_column(SmallInteger)

    # 通算成績
    total_1st: Mapped[int] = mapped_column(Integer, default=0)
    total_2nd: Mapped[int] = mapped_column(Integer, default=0)
    total_3rd: Mapped[int] = mapped_column(Integer, default=0)
    total_races: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    entries: Mapped[list["RaceEntry"]] = relationship("RaceEntry", back_populates="jockey")


class Trainer(Base):
    """
    調教師マスタテーブル（CHレコード対応）
    """
    __tablename__ = "trainers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trainer_code: Mapped[str] = mapped_column(String(5), unique=True, nullable=False)
    name_kanji: Mapped[str | None] = mapped_column(String(20))
    name_kana: Mapped[str | None] = mapped_column(String(30))
    belong_code: Mapped[int | None] = mapped_column(SmallInteger)  # 1=美浦,2=栗東

    # 通算成績
    total_1st: Mapped[int] = mapped_column(Integer, default=0)
    total_races: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    entries: Mapped[list["RaceEntry"]] = relationship("RaceEntry", back_populates="trainer")


class RaceEntry(Base):
    """
    馬毎レース情報テーブル（SEレコード対応）
    ★AIモデルの学習データの中心となるテーブル
    1レース × 1頭 = 1レコード

    【v2追加】
    - 複勝オッズ（odds_place_min/max）: 期待値計算に必須
    - speed_index: タイム指数（馬場差補正済み）
    """
    __tablename__ = "race_entries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("races.id"), nullable=False)
    horse_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("horses.id"))
    jockey_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("jockeys.id"))
    trainer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("trainers.id"))

    # 出走情報
    horse_num: Mapped[int] = mapped_column(SmallInteger, nullable=False)   # 馬番
    frame_num: Mapped[int] = mapped_column(SmallInteger, nullable=False)   # 枠番
    weight_carry: Mapped[float | None] = mapped_column(Numeric(4, 1))      # 斤量(kg)
    age: Mapped[int | None] = mapped_column(SmallInteger)                  # 馬齢
    sex: Mapped[int | None] = mapped_column(SmallInteger)                  # 1=牡,2=牝,3=騸

    # 馬体重（発走前）
    horse_weight: Mapped[int | None] = mapped_column(SmallInteger)         # 体重(kg)
    weight_diff: Mapped[int | None] = mapped_column(SmallInteger)          # 増減(kg)

    # オッズ（確定）
    odds_win: Mapped[float | None] = mapped_column(Numeric(6, 1))          # 単勝オッズ
    odds_place_min: Mapped[float | None] = mapped_column(Numeric(6, 1))    # 複勝オッズ 下限
    odds_place_max: Mapped[float | None] = mapped_column(Numeric(6, 1))    # 複勝オッズ 上限
    popularity: Mapped[int | None] = mapped_column(SmallInteger)           # 単勝人気順位

    # レース結果
    finish_order: Mapped[int | None] = mapped_column(SmallInteger)         # 着順（失格等はNULL）
    finish_time: Mapped[int | None] = mapped_column(Integer)               # 走破タイム(1/10秒)
    last_3f: Mapped[int | None] = mapped_column(Integer)                   # 上がり3F(1/10秒)
    margin: Mapped[int | None] = mapped_column(SmallInteger)               # 着差コード
    corner_1: Mapped[int | None] = mapped_column(SmallInteger)             # 1コーナー通過順
    corner_2: Mapped[int | None] = mapped_column(SmallInteger)
    corner_3: Mapped[int | None] = mapped_column(SmallInteger)
    corner_4: Mapped[int | None] = mapped_column(SmallInteger)
    abnormal_code: Mapped[int | None] = mapped_column(SmallInteger)        # 競走除外・取消等

    # 紐付け用コード（horse_id/jockey_id/trainer_id解決に使用）
    blood_reg_num: Mapped[str | None] = mapped_column(String(10))            # 血統登録番号→horses.id
    jockey_code: Mapped[str | None] = mapped_column(String(5))               # 騎手コード→jockeys.id
    trainer_code: Mapped[str | None] = mapped_column(String(5))              # 調教師コード→trainers.id

    # SE拡張フィールド（v4追加）
    blinker_code: Mapped[int | None] = mapped_column(SmallInteger)       # ブリンカー使用(0=未使用,1=使用)
    prev_jockey_code: Mapped[str | None] = mapped_column(String(5))      # 変更前騎手コード
    prev_weight_carry: Mapped[float | None] = mapped_column(Numeric(4, 1))  # 変更前負担重量(kg)
    apprentice_code: Mapped[int | None] = mapped_column(SmallInteger)    # 騎手見習コード(0-3)
    belong_region: Mapped[int | None] = mapped_column(SmallInteger)      # 東西所属(1=関東,2=関西,3=地方)

    # タイム指数（馬場差・距離を補正した相対スピード値）
    # JV-Linkから直接取得できないため、取り込み後に計算して保存する
    speed_index: Mapped[float | None] = mapped_column(Numeric(6, 2))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # リレーション
    race: Mapped["Race"] = relationship("Race", back_populates="entries")
    horse: Mapped["Horse | None"] = relationship("Horse", back_populates="entries")
    jockey: Mapped["Jockey | None"] = relationship("Jockey", back_populates="entries")
    trainer: Mapped["Trainer | None"] = relationship("Trainer", back_populates="entries")
    odds_snapshots: Mapped[list["OddsSnapshot"]] = relationship("OddsSnapshot", back_populates="entry")

    __table_args__ = (
        UniqueConstraint("race_id", "horse_num", name="uq_race_horse"),
        Index("idx_entries_race", "race_id"),
        Index("idx_entries_horse", "horse_id"),
        Index("idx_entries_jockey", "jockey_id"),
        Index("idx_entries_finish", "finish_order"),
        Index("idx_entries_speed", "speed_index"),
    )


class RaceLap(Base):
    """
    ハロンラップタイムテーブル（RAレコード内のラップ情報）
    ペース分析・スピード指数算出の基礎データ

    1レースにつき最大18ハロン（3600m）分のレコードが存在する。
    hallon_order=1 が最初の200m、order=Nが最後の200m。

    活用例:
    - 前半3F = hallon_order 1〜3 の合計
    - 後半3F = 最後の3ハロン の合計
    - ペース判定: 前半3F < 35.0秒 → ハイペース
    """
    __tablename__ = "race_laps"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("races.id"), nullable=False)
    hallon_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1始まり
    lap_time: Mapped[int | None] = mapped_column(SmallInteger)               # ラップタイム(1/10秒)

    race: Mapped["Race"] = relationship("Race", back_populates="laps")

    __table_args__ = (
        UniqueConstraint("race_id", "hallon_order", name="uq_lap"),
        Index("idx_laps_race", "race_id"),
    )


class Payout(Base):
    """
    払戻情報テーブル（RAレコード内の払戻部分）
    全券種の払戻を保存。期待値計算のベースデータ。
    """
    __tablename__ = "payouts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("races.id"), nullable=False)
    # 1=単勝,2=複勝,3=枠連,4=馬連,5=ワイド,6=馬単,7=三連複,8=三連単
    bet_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    combination: Mapped[str] = mapped_column(String(20), nullable=False)  # 例: "1-3-5"
    payout: Mapped[int] = mapped_column(Integer, nullable=False)          # 払戻金額（円）
    popularity: Mapped[int | None] = mapped_column(SmallInteger)          # 人気順位

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    race: Mapped["Race"] = relationship("Race", back_populates="payouts")

    __table_args__ = (
        UniqueConstraint("race_id", "bet_type", "combination", name="uq_payout"),
        Index("idx_payouts_race", "race_id"),
    )


class OddsSnapshot(Base):
    """
    オッズスナップショットテーブル
    前日・当日の時系列オッズを保存。オッズ変動から大口資金の流入を検出する。

    【期待値との関連】
    - 前日オッズ → 確定オッズへの変化が大きい馬は要注意（インサイダー的資金流入）
    - 確定直前に単勝オッズが急落 → 信頼できる情報がある可能性
    - 複勝オッズの幅 → 連対率の市場評価の幅
    """
    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("race_entries.id"), nullable=False)

    # スナップショット種別
    # 1=前日9時, 2=前日17時, 3=当日発売開始, 4=締切15分前, 5=確定
    snapshot_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime)

    # オッズ
    odds_win: Mapped[float | None] = mapped_column(Numeric(6, 1))       # 単勝
    odds_place_min: Mapped[float | None] = mapped_column(Numeric(6, 1)) # 複勝 下限
    odds_place_max: Mapped[float | None] = mapped_column(Numeric(6, 1)) # 複勝 上限
    popularity: Mapped[int | None] = mapped_column(SmallInteger)        # 単勝人気

    entry: Mapped["RaceEntry"] = relationship("RaceEntry", back_populates="odds_snapshots")

    __table_args__ = (
        UniqueConstraint("entry_id", "snapshot_type", name="uq_odds_snapshot"),
        Index("idx_odds_entry", "entry_id"),
    )


class HorseWeight(Base):
    """
    馬体重速報テーブル（0B11リアルタイムデータ）
    """
    __tablename__ = "horse_weights"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    race_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("races.id"), nullable=False)
    horse_num: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    weight: Mapped[int | None] = mapped_column(SmallInteger)
    weight_diff: Mapped[int | None] = mapped_column(SmallInteger)
    announced_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("race_id", "horse_num", name="uq_weight_race_horse"),
    )


class TrainingTime(Base):
    """
    調教タイムテーブル（WOODレコード対応）
    追い切り内容から仕上がり状態を判定する

    【v2拡充】
    - weeks_before: レース何週前の追い切りか（最終=1, 一週前=2）
    - partner: 追い切り相手（同時スタートの馬）
    - note: 調教コメント
    """
    __tablename__ = "training_times"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    horse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("horses.id"), nullable=False)
    race_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("races.id"))  # 対象レース

    training_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    weeks_before: Mapped[int | None] = mapped_column(SmallInteger)  # レースの何週前か（1=最終）

    # コース種別: 1=坂路, 2=ウッド, 3=芝, 4=ダート, 5=プール, 6=障害
    course_type: Mapped[int | None] = mapped_column(SmallInteger)
    distance: Mapped[int | None] = mapped_column(SmallInteger)  # 追い切り距離(m)

    # タイム（1/10秒）
    lap_time: Mapped[int | None] = mapped_column(Integer)        # 全体タイム
    last_3f: Mapped[int | None] = mapped_column(Integer)         # 上がり3F
    last_1f: Mapped[int | None] = mapped_column(Integer)         # 上がり1F

    # 評価・状態
    rank: Mapped[str | None] = mapped_column(String(1))          # A/B/C 等
    note: Mapped[str | None] = mapped_column(String(200))        # 調教コメント

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    horse: Mapped["Horse"] = relationship("Horse", back_populates="training_times")

    __table_args__ = (
        Index("idx_training_horse_date", "horse_id", "training_date"),
        Index("idx_training_race", "race_id"),
    )


class PedigreeLineage(Base):
    """
    血統系統テーブル（BTレコード対応）
    繁殖馬の系統分類（サンデーサイレンス系、キングカメハメハ系等）
    AI特徴量のカテゴリ変数として使用
    """
    __tablename__ = "pedigree_lineages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    breed_reg_num: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)  # 繁殖登録番号
    lineage_id: Mapped[str | None] = mapped_column(String(30))    # 系統ID（2桁区切り系譜コード）
    lineage_name: Mapped[str | None] = mapped_column(String(36))  # 系統名（サンデーサイレンス系等）

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_lineage_name", "lineage_name"),
    )


class JVLinkSyncLog(Base):
    """
    JV-Link同期ログテーブル
    dataspec ごとに lastfiletimestamp を管理する
    """
    __tablename__ = "jvlink_sync_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dataspec: Mapped[str] = mapped_column(String(4), unique=True, nullable=False)
    last_timestamp: Mapped[str] = mapped_column(String(14), nullable=False)  # YYYYMMDDhhmmss
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
