"""
特徴量エンジニアリングモジュール
DBからレース・出走馬の特徴量を抽出してDataFrameを構築する

【特徴量カテゴリ】v2: 19→35項目に拡充
1. レース条件: 距離・コース・グレード・馬場状態・天候・頭数
2. 馬の基本情報: 年齢・性別・通算成績
3. 騎手・調教師の成績（通算＋外国人フラグ）
4. 市場情報: オッズ・人気
5. 直近成績: 直近3走/5走の着順・上がり3F・脚質・レース間隔
6. 馬体重・斤量
7. コース適性: 同距離帯勝率・同コース種別勝率
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

# SQLパラメータ上限対策: entry_idsをバッチ分割してクエリ実行
_BATCH_IDS = 50000  # 1回のSQLに渡すID数の上限


def _query_in_batches(db: Session, sql: text, ids: list, id_param: str = "ids") -> pd.DataFrame:
    """IDリストをバッチ分割してSQLを実行し、結果を結合して返す"""
    if not ids:
        return pd.DataFrame()
    results = []
    for i in range(0, len(ids), _BATCH_IDS):
        chunk = ids[i:i + _BATCH_IDS]
        df_chunk = pd.read_sql(sql, db.bind, params={id_param: chunk})
        if not df_chunk.empty:
            results.append(df_chunk)
    return pd.concat(results, ignore_index=True) if results else pd.DataFrame()


def _safe_merge(df: pd.DataFrame, right: pd.DataFrame, on: str = "entry_id", how: str = "left") -> pd.DataFrame:
    """空DataFrameとの安全なmerge（右側が空の場合はカラム不在でKeyErrorになるのを防ぐ）"""
    if right.empty or on not in right.columns:
        return df
    return df.merge(right, on=on, how=how)


# --- 特徴量名リスト ---
# オッズ・人気はレース前に公開される情報のため特徴量に含める。
# ただし学習データのオッズは確定値のため、予測時の暫定オッズとは乖離がある点に注意。
FEATURE_COLS = [
    # レース条件
    "distance", "track_type", "grade", "is_handicap", "is_female_only",
    "track_cond", "weather", "track_dir", "horse_count", "venue_code",
    # 馬番・枠番
    "horse_num", "frame_num",
    # 馬の基本情報
    "age", "sex",
    # 馬の通算成績
    "horse_win_rate", "horse_earnings_per_race",
    # 斤量・体重
    "weight_carry", "horse_weight", "weight_diff",
    # 騎手・調教師成績
    "jockey_win_rate", "trainer_win_rate", "is_foreign_jockey",
    # 市場シグナル
    "odds_win", "popularity",
    # 直近成績（過去3走）
    "recent_avg_finish", "recent_avg_speed_index", "recent_win_count",
    "recent_avg_last_3f", "recent_avg_corner4",
    # 直近成績（過去5走）
    "recent_5_avg_finish", "recent_5_best_finish",
    # レース間隔・騎手乗り替わり
    "race_interval_days", "jockey_change",
    # コース適性（同距離帯・同コース種別での勝率）
    "same_distance_win_rate", "same_track_win_rate",
    # 血統系統（カテゴリ特徴量、LightGBMネイティブ対応）
    "father_lineage_id", "mother_father_lineage_id",
    # 調教データ（直近の坂路/ウッド追い切り）
    "training_last_3f", "training_last_1f", "training_days_before",
    # 市場調査で効果が確認された追加特徴量
    "jockey_horse_combo_rate",   # 騎手×馬コンビの過去勝率
    "lineage_cond_rate",         # 父系統×馬場状態の勝率
    "class_change",              # クラス変動（前走比: 昇級=1, 同級=0, 降級=-1）
    "weight_carry_diff",         # 同レース内の斤量偏差
    # v3追加: 6項目
    "track_bias_score",          # 馬場指数（当日タイム - 過去365日基準タイムの差分）
    "race_pace_score",           # 展開予想（脚質分布からペース0-100）
    "upset_score",               # 荒れ予測（波乱度0-100）
    "training_rating_score",     # 調教評価（z-scoreベース偏差値）
    "pace_change_index",         # PCI（前半3F/後半3Fのペース変化率）
    "lineage_track_aptitude",    # 血統×馬場適性（父系統×馬場状態の過去勝率）
    # v4追加: SEパーサー拡張由来の4項目
    "blinker_flag",              # ブリンカー使用フラグ（0/1）
    "is_apprentice",             # 見習騎手フラグ（0/1）
    "has_jockey_change_official", # 公式騎手変更フラグ（prev_jockey_codeが空でない場合1）
    "belong_region",             # 東西所属（1=関東, 2=関西, 3=地方）
    # ── v5追加: フェーズ1拡張 ──
    # 複勝オッズ関連
    "odds_place_avg",            # 複勝オッズ中央値（(min+max)/2）
    "odds_place_range",          # 複勝オッズ幅（市場の不確実性指標）
    "odds_win_place_ratio",      # 単勝/複勝比（穴馬検出用）
    # 斤量の高度分析
    "weight_carry_per_kg",       # 斤量÷馬体重（負荷率）
    "prev_weight_carry_diff",    # 斤量変更幅（前走比）
    # コーナー通過の多角分析（過去走ベース）
    "recent_avg_corner1",        # 直近3走の1コーナー通過順位平均
    "recent_corner_improvement", # 直近3走の1角→4角の順位改善度平均
    "recent_corner4_std",        # 直近3走の4角通過順位の標準偏差（脚質安定性）
    # パフォーマンス指標
    "recent_avg_margin",         # 直近3走の着差平均（勝ち馬との差）
    "recent_speed_index_std",    # 直近3走のタイム指数の標準偏差（安定性）
    "recent_best_speed_index",   # 直近5走のタイム指数最高値
    "recent_last_3f_best",       # 直近5走の上がり3F最速
    # 騎手・調教師の効率性
    "jockey_place_rate",         # 騎手の複勝率
    "jockey_experience_years",   # 騎手の経験年数
    "trainer_place_rate",        # 調教師の複勝率
    # 条件別適性の拡張
    "same_venue_win_rate",       # 同会場での過去3年勝率
    "track_cond_aptitude",       # 馬場状態別の過去勝率
    # レース条件の追加
    "condition_code",            # 競走条件コード（クラス詳細）
    "prize_1st_log",             # 1着賞金の対数（レースの格）
    "nichi_in_kai",              # 開催日次（開催の前半/後半 = 馬場の荒れ具合）
    # ── v6追加: 精度向上特徴量 ──
    "recent_win_trend",          # 直近成績のトレンド（上昇=正, 下降=負）
    "jockey_trainer_combo_rate", # 騎手×調教師コンビ勝率
    "pace_style_fit",            # 脚質×展開適合度スコア
]

# オッズなし特徴量（後方互換用、FEATURE_COLSと同一）
# オッズなし特徴量（期待値ベース戦略用）
FEATURE_COLS_NO_ODDS = [c for c in FEATURE_COLS if c not in ("odds_win", "popularity", "odds_place_avg", "odds_place_range", "odds_win_place_ratio")]

# 目的変数
TARGET_COL = "is_win"

# ランキング学習用の目的変数（着順を反転したスコア）
RANK_TARGET_COL = "rank_label"


# --- 距離帯の分類 ---
def _distance_band_sql() -> str:
    """距離帯を4分類するSQL CASE式"""
    return """
        CASE
            WHEN distance <= 1400 THEN 1  -- 短距離
            WHEN distance <= 1800 THEN 2  -- マイル
            WHEN distance <= 2200 THEN 3  -- 中距離
            ELSE 4                         -- 長距離
        END
    """


def _base_select_sql() -> str:
    """学習・推論共通のSELECT句"""
    return f"""
        -- 識別子（モデル学習には使わないが後処理用に残す）
        re.id                           AS entry_id,
        r.race_key,
        r.race_date,
        re.horse_id,
        re.jockey_id,

        -- レース条件
        r.distance,
        r.track_type,
        COALESCE(r.grade, 10)           AS grade,
        r.is_handicap::int              AS is_handicap,
        r.is_female_only::int           AS is_female_only,
        COALESCE(r.track_cond, 1)       AS track_cond,
        COALESCE(r.weather, 1)          AS weather,
        COALESCE(r.track_dir, 1)        AS track_dir,
        COALESCE(r.horse_count, 16)     AS horse_count,
        CASE WHEN r.venue_code ~ '^[0-9]+$'
             THEN r.venue_code::int
             ELSE 99 END                AS venue_code,

        -- 距離帯（適性集計のキー）
        ({_distance_band_sql()}) AS distance_band,

        -- 馬番・枠番
        re.horse_num,
        re.frame_num,

        -- 馬の基本情報
        COALESCE(re.age, 3)             AS age,
        COALESCE(re.sex, 1)             AS sex,

        -- 馬の通算成績
        CASE WHEN h.total_races > 0
             THEN h.total_wins::float / h.total_races
             ELSE 0.0 END               AS horse_win_rate,
        CASE WHEN h.total_races > 0
             THEN h.total_earnings::float / h.total_races
             ELSE 0.0 END               AS horse_earnings_per_race,

        -- 斤量・体重
        COALESCE(re.weight_carry, 55.0) AS weight_carry,
        COALESCE(re.horse_weight, 480)  AS horse_weight,
        COALESCE(re.weight_diff, 0)     AS weight_diff,

        -- 騎手成績
        CASE WHEN j.total_races > 0
             THEN j.total_1st::float / j.total_races
             ELSE 0.0 END               AS jockey_win_rate,
        -- 外国人騎手フラグ（短期免許含む）
        CASE WHEN j.belong_code = 4 THEN 1 ELSE 0 END AS is_foreign_jockey,

        -- 調教師成績
        CASE WHEN t.total_races > 0
             THEN t.total_1st::float / t.total_races
             ELSE 0.0 END               AS trainer_win_rate,

        -- 市場シグナル（0はオッズ未確定→中間値で代替）
        CASE WHEN re.odds_win > 0 THEN re.odds_win
             ELSE 10.0 END                                AS odds_win,
        CASE WHEN re.popularity > 0 THEN re.popularity
             ELSE 8 END                                   AS popularity,

        -- 血統系統（カテゴリ特徴量）
        COALESCE(pl_f.lineage_name, 'unknown')  AS father_lineage_name,
        COALESCE(pl_mf.lineage_name, 'unknown') AS mother_father_lineage_name,

        -- SE拡張フィールド（v4追加: ブリンカー/見習/騎手変更/所属）
        COALESCE(re.blinker_code, 0)    AS blinker_code,
        COALESCE(re.apprentice_code, 0) AS apprentice_code,
        re.prev_jockey_code,
        COALESCE(re.belong_region, 0)   AS belong_region,

        -- 複勝オッズ（v5追加）
        COALESCE(re.odds_place_min, 0)  AS odds_place_min,
        COALESCE(re.odds_place_max, 0)  AS odds_place_max,
        -- 斤量変更（v5追加）
        re.prev_weight_carry,
        -- レース条件の追加（v5追加）
        COALESCE(r.condition_code, 0)   AS condition_code,
        COALESCE(r.prize_1st, 0)        AS prize_1st,
        r.nichi,
        -- 騎手の通算成績詳細（v5追加）
        COALESCE(j.total_2nd, 0)        AS jockey_total_2nd,
        COALESCE(j.total_3rd, 0)        AS jockey_total_3rd,
        COALESCE(j.total_races, 0)      AS jockey_total_races,
        j.birth_date                    AS jockey_birth_date,
        -- 調教師の通算成績詳細（v5追加、trainersにはtotal_2nd/3rdなし）
        COALESCE(t.total_races, 0)      AS trainer_total_races,

        -- 実際のオッズ（期待値計算用、特徴量には含めない。0は未確定）
        NULLIF(re.odds_win, 0)          AS odds_win_raw
    """


def _base_from_sql() -> str:
    """学習・推論共通のFROM句"""
    return """
        FROM race_entries re
        JOIN races r ON r.id = re.race_id
        LEFT JOIN horses h ON h.id = re.horse_id
        LEFT JOIN jockeys j ON j.id = re.jockey_id
        LEFT JOIN trainers t ON t.id = re.trainer_id
        LEFT JOIN pedigree_lineages pl_f ON pl_f.breed_reg_num = h.father_code
        LEFT JOIN pedigree_lineages pl_mf ON pl_mf.breed_reg_num = h.mother_father_code
    """


def build_training_dataset(db: Session) -> pd.DataFrame:
    """
    全過去レース（結果が出ているもの）から学習データを構築する。
    finish_order が NULL でないエントリのみ対象。
    """
    sql = text(f"""
        SELECT
            {_base_select_sql()},

            -- 目的変数
            (re.finish_order = 1)::int      AS is_win,
            re.finish_order

        {_base_from_sql()}

        WHERE re.finish_order IS NOT NULL
          AND COALESCE(re.abnormal_code, 0) = 0
        ORDER BY r.race_date, r.race_key, re.horse_num
    """)

    df = pd.read_sql(sql, db.bind)

    # ランキング学習用ラベル（着順を反転: 1着=最大、最下位=0）
    if "finish_order" in df.columns and "horse_count" in df.columns:
        df[RANK_TARGET_COL] = (df["horse_count"] - df["finish_order"]).clip(lower=0)

    # 追加特徴量を計算
    # 大量データ判定を先に行い、重いクエリをスキップ
    _skip_heavy = len(df) > 10000  # 学習データ（大量）の場合はスキップ
    df = _add_recent_form(db, df)
    df = _add_race_interval(db, df)
    df = _add_jockey_change(db, df)
    df = _add_course_aptitude(db, df)
    df = _add_lineage_features(df)
    df = _add_training_features(db, df)
    df = _add_combo_features(db, df, skip_heavy=_skip_heavy)
    # v5追加: 騎手・調教師・馬の成績を直近期間で上書き（精度向上施策）
    # 学習時は大量データのため重いサブクエリをスキップ
    if not _skip_heavy:
        df = _add_recent_jockey_stats(db, df, years=3)
        df = _add_recent_trainer_stats(db, df, years=3)
        df = _add_weighted_horse_stats(db, df)
    # v3追加特徴量（学習時は重いクエリをスキップしデフォルト値を使用）
    # 推論時（build_prediction_features）では少数レコードなので実行可能
    if not _skip_heavy:
        df = _add_track_bias_score(db, df)
        df = _add_race_pace_score(db, df)
        df = _add_pace_change_index(db, df)
        df = _add_lineage_track_aptitude(db, df)
    else:
        # デフォルト値で埋める（学習時の高速化）
        for col, default in [("track_bias_score", 0.0), ("race_pace_score", 50.0),
                             ("pace_change_index", 100.0), ("lineage_track_aptitude", 0.0)]:
            if col not in df.columns:
                df[col] = default
    df = _add_upset_score(db, df)  # これはSQL不要（DataFrame内計算のみ）
    df = _add_training_rating_score(db, df) if not _skip_heavy else df.assign(training_rating_score=50.0) if "training_rating_score" not in df.columns else df
    # v4追加: SEパーサー拡張由来
    df = _add_se_extended_features(df)
    # v5追加: フェーズ1拡張（+20項目）
    df = _add_v5_odds_features(df)
    df = _add_v5_weight_features(df)
    if not _skip_heavy:
        df = _add_v5_corner_features(db, df)
        df = _add_v5_performance_features(db, df)
        df = _add_v5_venue_cond_aptitude(db, df)
    else:
        # 学習時のデフォルト値
        for col, val in [("recent_avg_corner1", 8.0), ("recent_corner_improvement", 0.0),
                         ("recent_corner4_std", 3.0), ("recent_avg_margin", 5.0),
                         ("recent_speed_index_std", 5.0), ("recent_best_speed_index", 0.0),
                         ("recent_last_3f_best", 0.0), ("same_venue_win_rate", 0.0),
                         ("track_cond_aptitude", 0.0)]:
            if col not in df.columns:
                df[col] = val
    df = _add_v5_jockey_trainer_efficiency(df)
    df = _add_v5_race_condition_features(df)
    # v6追加
    if not _skip_heavy:
        df = _add_v6_trend_features(db, df)
        df = _add_v6_jockey_trainer_combo(db, df)
    df = _add_v6_pace_style_fit(df)

    # 全特徴量カラムを数値型に強制変換（バッチ結合時のobject型混入対策）
    for col in FEATURE_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df


def build_prediction_features(db: Session, race_key: str) -> pd.DataFrame:
    """
    指定レースの全出走馬について予測用特徴量を構築する。
    （結果未確定のレースでも動作する）
    """
    sql = text(f"""
        SELECT
            {_base_select_sql()},

            -- 表示用（特徴量ではない）
            h.name_kana                     AS horse_name,
            j.name_kanji                    AS jockey_name

        {_base_from_sql()}

        WHERE r.race_key = :race_key
        ORDER BY re.horse_num
    """)

    df = pd.read_sql(sql, db.bind, params={"race_key": race_key})

    # 追加特徴量を計算
    df = _add_recent_form(db, df)
    df = _add_race_interval(db, df)
    df = _add_jockey_change(db, df)
    df = _add_course_aptitude(db, df)
    df = _add_lineage_features(df)
    df = _add_training_features(db, df)
    df = _add_combo_features(db, df)
    # v5追加: 騎手・調教師・馬の成績を直近期間で上書き（精度向上施策）
    df = _add_recent_jockey_stats(db, df, years=3)
    df = _add_recent_trainer_stats(db, df, years=3)
    df = _add_weighted_horse_stats(db, df)
    # v3追加特徴量
    df = _add_track_bias_score(db, df)
    df = _add_race_pace_score(db, df)
    df = _add_upset_score(db, df)
    df = _add_training_rating_score(db, df)
    df = _add_pace_change_index(db, df)
    df = _add_lineage_track_aptitude(db, df)
    # v4追加: SEパーサー拡張由来
    df = _add_se_extended_features(df)
    # v5追加: フェーズ1拡張（+20項目）
    df = _add_v5_odds_features(df)
    df = _add_v5_weight_features(df)
    df = _add_v5_corner_features(db, df)
    df = _add_v5_performance_features(db, df)
    df = _add_v5_jockey_trainer_efficiency(df)
    df = _add_v5_venue_cond_aptitude(db, df)
    df = _add_v5_race_condition_features(df)
    # v6追加: 精度向上特徴量
    df = _add_v6_trend_features(db, df)
    df = _add_v6_jockey_trainer_combo(db, df)
    df = _add_v6_pace_style_fit(df)

    # オッズ未確定時のインテリジェント代替（未勝利戦対応）
    df = _fill_missing_odds_signal(df)

    return df


def _fill_missing_odds_signal(df: pd.DataFrame) -> pd.DataFrame:
    """
    オッズ・人気が未確定（0 or デフォルト値）の場合、
    他の特徴量から疑似的なオッズ・人気を推定する。
    血統・調教・騎手・過去走など利用可能な情報で馬の能力をスコアリングし、
    レース内順位として人気、逆数としてオッズを割り当てる。
    """
    if df.empty:
        return df

    # オッズが未確定かどうかの判定（全馬同じデフォルト値 or 0）
    odds_col = df["odds_win"]
    has_real_odds = (odds_col > 0) & (odds_col != 10.0)  # デフォルト10.0でない
    if has_real_odds.any():
        return df  # 実オッズがある馬がいれば何もしない

    # === 能力スコア算出（利用可能な情報を総動員） ===
    score = pd.Series(0.0, index=df.index)

    # 1. 馬の通算成績（最重要）
    score += df.get("horse_win_rate", pd.Series(0.0, index=df.index)).fillna(0) * 100
    score += df.get("horse_earnings_per_race", pd.Series(0.0, index=df.index)).fillna(0) * 0.001

    # 2. 騎手力（新馬戦では有力馬に上位騎手が騎乗する傾向）
    score += df.get("jockey_win_rate", pd.Series(0.0, index=df.index)).fillna(0) * 50
    score += df.get("jockey_place_rate", pd.Series(0.0, index=df.index)).fillna(0) * 20

    # 3. 調教師力
    score += df.get("trainer_win_rate", pd.Series(0.0, index=df.index)).fillna(0) * 30

    # 4. 調教評価
    score += (df.get("training_rating_score", pd.Series(50.0, index=df.index)).fillna(50) - 50) * 0.5

    # 5. 血統適性
    score += df.get("lineage_track_aptitude", pd.Series(0.0, index=df.index)).fillna(0) * 30
    score += df.get("lineage_cond_rate", pd.Series(0.0, index=df.index)).fillna(0) * 20

    # 6. 直近成績（少ないかもしれないが0でなければ使う）
    recent = df.get("recent_avg_finish", pd.Series(5.0, index=df.index)).fillna(5.0)
    score += (10 - recent) * 3  # 着順が良いほど高スコア

    # 7. タイム指数
    score += df.get("recent_best_speed_index", pd.Series(0.0, index=df.index)).fillna(0) * 0.5

    # スコア順にランキング → 疑似人気
    rank = score.rank(ascending=False, method='first').astype(int)
    n = len(df)

    # 疑似オッズ（人気順に応じた典型的オッズ分布）
    # JRA統計: 1番人気≒2.5倍, 2番人気≒5倍, ... 最下位≒100倍
    typical_odds = {1: 2.5, 2: 4.5, 3: 7.0, 4: 10.0, 5: 15.0,
                    6: 20.0, 7: 30.0, 8: 40.0, 9: 50.0, 10: 60.0}
    df["popularity"] = rank
    df["odds_win"] = rank.map(lambda r: typical_odds.get(r, min(70 + r * 5, 200)))

    # 複勝オッズ関連も更新
    if "odds_place_avg" in df.columns:
        df["odds_place_avg"] = df["odds_win"] * 0.3
    if "odds_place_range" in df.columns:
        df["odds_place_range"] = df["odds_win"] * 0.1
    if "odds_win_place_ratio" in df.columns:
        df["odds_win_place_ratio"] = 3.3  # 典型値

    return df


def _add_recent_form(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    各エントリの直近3走/5走成績をサブクエリで追加する。
    - 直近3走: 平均着順・タイム指数平均・勝利数・上がり3F平均・4角通過順位平均
    - 直近5走: 平均着順・最高着順
    """
    defaults = {
        "recent_avg_finish": 5.0,
        "recent_avg_speed_index": 0.0,
        "recent_win_count": 0,
        "recent_avg_last_3f": 0.0,
        "recent_avg_corner4": 8.0,
        "recent_5_avg_finish": 5.0,
        "recent_5_best_finish": 5,
    }

    if df.empty:
        for col, val in defaults.items():
            df[col] = val
        return df

    entry_ids = df["entry_id"].tolist()

    # 直近5走までの成績（3走集計と5走集計を同時に取得）
    recent_sql = text("""
        WITH ranked AS (
            SELECT
                h_entry.id                  AS entry_id,
                re_past.finish_order,
                re_past.speed_index,
                re_past.last_3f,
                re_past.corner_4,
                ROW_NUMBER() OVER (
                    PARTITION BY h_entry.id
                    ORDER BY r_past.race_date DESC, r_past.race_key DESC
                )                           AS rn
            FROM race_entries h_entry
            JOIN races r_curr ON r_curr.id = h_entry.race_id
            JOIN race_entries re_past ON re_past.horse_id = h_entry.horse_id
            JOIN races r_past ON r_past.id = re_past.race_id
            WHERE h_entry.id = ANY(:ids)
              AND r_past.race_date < r_curr.race_date
              AND re_past.finish_order IS NOT NULL
              AND COALESCE(re_past.abnormal_code, 0) = 0
        )
        SELECT
            entry_id,
            -- 直近3走
            AVG(CASE WHEN rn <= 3 THEN finish_order END)
                AS recent_avg_finish,
            AVG(CASE WHEN rn <= 3 THEN COALESCE(speed_index, 0) END)
                AS recent_avg_speed_index,
            SUM(CASE WHEN rn <= 3 AND finish_order = 1 THEN 1 ELSE 0 END)
                AS recent_win_count,
            AVG(CASE WHEN rn <= 3 AND last_3f > 0 THEN last_3f END)
                AS recent_avg_last_3f,
            AVG(CASE WHEN rn <= 3 AND corner_4 > 0 THEN corner_4 END)
                AS recent_avg_corner4,
            -- 直近5走
            AVG(CASE WHEN rn <= 5 THEN finish_order END)
                AS recent_5_avg_finish,
            MIN(CASE WHEN rn <= 5 THEN finish_order END)
                AS recent_5_best_finish
        FROM ranked
        WHERE rn <= 5
        GROUP BY entry_id
    """)
    recent_df = _query_in_batches(db, recent_sql, entry_ids)

    df = _safe_merge(df, recent_df, on="entry_id")
    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(val)
    df["recent_win_count"] = df["recent_win_count"].astype(int)
    df["recent_5_best_finish"] = df["recent_5_best_finish"].astype(int)

    return df


def _add_race_interval(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    前走からのレース間隔（日数）を追加する。
    休み明け（間隔が長い）は成績に大きく影響する重要特徴量。
    """
    if df.empty:
        df["race_interval_days"] = 30
        return df

    entry_ids = df["entry_id"].tolist()

    interval_sql = text("""
        SELECT
            h_entry.id AS entry_id,
            (r_curr.race_date - MAX(r_past.race_date)) AS race_interval_days
        FROM race_entries h_entry
        JOIN races r_curr ON r_curr.id = h_entry.race_id
        JOIN race_entries re_past ON re_past.horse_id = h_entry.horse_id
        JOIN races r_past ON r_past.id = re_past.race_id
        WHERE h_entry.id = ANY(:ids)
          AND r_past.race_date < r_curr.race_date
          AND re_past.finish_order IS NOT NULL
        GROUP BY h_entry.id, r_curr.race_date
    """)
    interval_df = _query_in_batches(db, interval_sql, entry_ids)

    df = _safe_merge(df, interval_df, on="entry_id")
    # デフォルト30日（初出走や前走不明の場合）
    if "race_interval_days" not in df.columns:
        df["race_interval_days"] = 30
    else:
        df["race_interval_days"] = df["race_interval_days"].fillna(30).astype(int)

    return df


def _add_jockey_change(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    前走から騎手が変わったかどうかのフラグを追加する。
    騎手乗り替わりは成績に影響する重要ファクター。
    """
    if df.empty:
        df["jockey_change"] = 0
        return df

    entry_ids = df["entry_id"].tolist()

    # jockey_codeベースで比較（jockey_idがNULLでも動作）
    jchange_sql = text("""
        WITH prev_jockey AS (
            SELECT DISTINCT ON (h_entry.id)
                h_entry.id AS entry_id,
                re_past.jockey_code AS prev_jockey_code_actual
            FROM race_entries h_entry
            JOIN races r_curr ON r_curr.id = h_entry.race_id
            JOIN race_entries re_past ON re_past.horse_id = h_entry.horse_id
            JOIN races r_past ON r_past.id = re_past.race_id
            WHERE h_entry.id = ANY(:ids)
              AND r_past.race_date < r_curr.race_date
              AND re_past.finish_order IS NOT NULL
              AND COALESCE(re_past.abnormal_code, 0) = 0
            ORDER BY h_entry.id, r_past.race_date DESC, r_past.race_key DESC
        )
        SELECT
            e.id AS entry_id,
            CASE WHEN pj.prev_jockey_code_actual IS NOT NULL
                      AND pj.prev_jockey_code_actual != ''
                      AND e.jockey_code IS NOT NULL
                      AND e.jockey_code != ''
                      AND pj.prev_jockey_code_actual != e.jockey_code
                 THEN 1 ELSE 0 END AS jockey_change
        FROM race_entries e
        LEFT JOIN prev_jockey pj ON pj.entry_id = e.id
        WHERE e.id = ANY(:ids)
    """)
    jchange_df = _query_in_batches(db, jchange_sql, entry_ids)

    df = _safe_merge(df, jchange_df, on="entry_id")
    if "jockey_change" not in df.columns:
        df["jockey_change"] = 0
    else:
        df["jockey_change"] = df["jockey_change"].fillna(0).astype(int)

    return df


def _add_course_aptitude(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    同距離帯・同コース種別（芝/ダート）での過去勝率を追加する。
    コース適性は予測精度に大きく寄与する。
    """
    if df.empty:
        df["same_distance_win_rate"] = 0.0
        df["same_track_win_rate"] = 0.0
        return df

    entry_ids = df["entry_id"].tolist()

    aptitude_sql = text(f"""
        WITH curr AS (
            SELECT
                re.id AS entry_id,
                re.horse_id,
                r.race_date,
                r.track_type,
                ({_distance_band_sql()}) AS distance_band
            FROM race_entries re
            JOIN races r ON r.id = re.race_id
            WHERE re.id = ANY(:ids)
        ),
        past_stats AS (
            SELECT
                c.entry_id,
                -- 同距離帯での勝率
                AVG(CASE
                    WHEN ({_distance_band_sql().replace('distance', 'r_past.distance')}) = c.distance_band
                    THEN CASE WHEN re_past.finish_order = 1 THEN 1.0 ELSE 0.0 END
                END) AS same_distance_win_rate,
                -- 同コース種別での勝率
                AVG(CASE
                    WHEN r_past.track_type = c.track_type
                    THEN CASE WHEN re_past.finish_order = 1 THEN 1.0 ELSE 0.0 END
                END) AS same_track_win_rate
            FROM curr c
            JOIN race_entries re_past ON re_past.horse_id = c.horse_id
            JOIN races r_past ON r_past.id = re_past.race_id
            WHERE r_past.race_date < c.race_date
              AND r_past.race_date >= c.race_date - INTERVAL '3 years'
              AND re_past.finish_order IS NOT NULL
              AND COALESCE(re_past.abnormal_code, 0) = 0
            GROUP BY c.entry_id
        )
        SELECT * FROM past_stats
    """)
    apt_df = _query_in_batches(db, aptitude_sql, entry_ids)

    df = _safe_merge(df, apt_df, on="entry_id")
    for col in ["same_distance_win_rate", "same_track_win_rate"]:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = df[col].fillna(0.0)

    return df


def _add_lineage_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    血統系統をカテゴリ特徴量（整数エンコード）に変換。
    LightGBMのcategorical_featureとして使用可能。
    """
    for col_src, col_dst in [
        ("father_lineage_name", "father_lineage_id"),
        ("mother_father_lineage_name", "mother_father_lineage_id"),
    ]:
        if col_src in df.columns:
            # 文字列→整数エンコード（unknownは0）
            df[col_dst] = df[col_src].astype("category").cat.codes
        else:
            df[col_dst] = 0

    return df


def _add_training_features(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    直近の調教データ（坂路/ウッドチップ）から特徴量を追加。
    - training_last_3f: 直近調教の上がり3Fタイム（0.1秒単位）
    - training_last_1f: 直近調教の最終1Fタイム
    - training_days_before: 直近調教からレースまでの日数
    """
    defaults = {
        "training_last_3f": 0.0,
        "training_last_1f": 0.0,
        "training_days_before": 14.0,
    }

    if df.empty or "horse_id" not in df.columns:
        for col, val in defaults.items():
            df[col] = val
        return df

    entry_ids = df["entry_id"].tolist()

    training_sql = text("""
        WITH latest_training AS (
            SELECT DISTINCT ON (h_entry.id)
                h_entry.id AS entry_id,
                tt.last_3f,
                tt.last_1f,
                r_curr.race_date - tt.training_date AS days_before
            FROM race_entries h_entry
            JOIN races r_curr ON r_curr.id = h_entry.race_id
            JOIN training_times tt ON tt.horse_id = h_entry.horse_id
            WHERE h_entry.id = ANY(:ids)
              AND tt.training_date < r_curr.race_date
              AND tt.training_date >= r_curr.race_date - 30
              AND tt.last_3f IS NOT NULL
              AND tt.last_3f > 0
            ORDER BY h_entry.id, tt.training_date DESC
        )
        SELECT * FROM latest_training
    """)
    tr_df = _query_in_batches(db, training_sql, entry_ids)

    if not tr_df.empty:
        tr_df = tr_df.rename(columns={
            "last_3f": "training_last_3f",
            "last_1f": "training_last_1f",
            "days_before": "training_days_before",
        })
        df = df.merge(tr_df[["entry_id", "training_last_3f", "training_last_1f", "training_days_before"]],
                       on="entry_id", how="left")

    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val
        df[col] = df[col].fillna(val)

    return df


def _add_combo_features(db: Session, df: pd.DataFrame, *, skip_heavy: bool = False) -> pd.DataFrame:
    """
    市場調査で効果確認済みの追加特徴量:
    - 騎手×馬コンビ勝率
    - 父系統×馬場状態勝率（skip_heavy=Trueの場合はスキップ：クロスジョインで非常に重い）
    - クラス変動（昇級/降級）
    - 斤量偏差（レース内平均との差）
    """
    if df.empty:
        for col in ["jockey_horse_combo_rate", "lineage_cond_rate", "class_change", "weight_carry_diff"]:
            df[col] = 0.0
        return df

    entry_ids = df["entry_id"].tolist()

    # --- 騎手×馬コンビ勝率 ---
    combo_sql = text("""
        SELECT
            h_entry.id AS entry_id,
            CASE WHEN COUNT(*) >= 2
                 THEN SUM(CASE WHEN re_past.finish_order = 1 THEN 1.0 ELSE 0.0 END) / COUNT(*)
                 ELSE 0.0
            END AS jockey_horse_combo_rate
        FROM race_entries h_entry
        JOIN races r_curr ON r_curr.id = h_entry.race_id
        JOIN race_entries re_past ON re_past.horse_id = h_entry.horse_id
                                  AND re_past.jockey_id = h_entry.jockey_id
        JOIN races r_past ON r_past.id = re_past.race_id
        WHERE h_entry.id = ANY(:ids)
          AND r_past.race_date < r_curr.race_date
          AND r_past.race_date >= r_curr.race_date - INTERVAL '2 years'
          AND re_past.finish_order IS NOT NULL
        GROUP BY h_entry.id
    """)
    combo_df = _query_in_batches(db, combo_sql, entry_ids)
    if not combo_df.empty:
        df = df.merge(combo_df, on="entry_id", how="left")
    if "jockey_horse_combo_rate" not in df.columns:
        df["jockey_horse_combo_rate"] = 0.0
    df["jockey_horse_combo_rate"] = df["jockey_horse_combo_rate"].fillna(0.0)

    # --- 父系統×馬場状態勝率（クロスジョインで非常に重い → 学習時はスキップ） ---
    if not skip_heavy:
        lineage_sql = text("""
            SELECT
                h_entry.id AS entry_id,
                CASE WHEN COUNT(*) >= 5
                     THEN SUM(CASE WHEN re_past.finish_order = 1 THEN 1.0 ELSE 0.0 END) / COUNT(*)
                     ELSE 0.0
                END AS lineage_cond_rate
            FROM race_entries h_entry
            JOIN races r_curr ON r_curr.id = h_entry.race_id
            JOIN horses h ON h.id = h_entry.horse_id
            JOIN race_entries re_past ON TRUE
            JOIN races r_past ON r_past.id = re_past.race_id
            JOIN horses h_past ON h_past.id = re_past.horse_id
            WHERE h_entry.id = ANY(:ids)
              AND h_past.father_code = h.father_code
              AND r_past.track_cond = r_curr.track_cond
              AND r_past.race_date < r_curr.race_date
              AND re_past.finish_order IS NOT NULL
            GROUP BY h_entry.id
        """)
        try:
            lin_df = _query_in_batches(db, lineage_sql, entry_ids)
            if not lin_df.empty:
                df = df.merge(lin_df, on="entry_id", how="left")
        except Exception:
            pass  # テーブル未存在時はスキップ
    if "lineage_cond_rate" not in df.columns:
        df["lineage_cond_rate"] = 0.0
    df["lineage_cond_rate"] = df["lineage_cond_rate"].fillna(0.0)

    # --- クラス変動（前走比） ---
    class_sql = text("""
        SELECT DISTINCT ON (h_entry.id)
            h_entry.id AS entry_id,
            CASE
                WHEN r_curr.grade IS NULL OR r_past.grade IS NULL THEN 0
                WHEN r_curr.grade < r_past.grade THEN 1   -- 昇級（gradeが小さいほど上位）
                WHEN r_curr.grade > r_past.grade THEN -1  -- 降級
                ELSE 0
            END AS class_change
        FROM race_entries h_entry
        JOIN races r_curr ON r_curr.id = h_entry.race_id
        JOIN race_entries re_past ON re_past.horse_id = h_entry.horse_id
        JOIN races r_past ON r_past.id = re_past.race_id
        WHERE h_entry.id = ANY(:ids)
          AND r_past.race_date < r_curr.race_date
          AND re_past.finish_order IS NOT NULL
        ORDER BY h_entry.id, r_past.race_date DESC
    """)
    cls_df = _query_in_batches(db, class_sql, entry_ids)
    if not cls_df.empty:
        df = df.merge(cls_df, on="entry_id", how="left")
    if "class_change" not in df.columns:
        df["class_change"] = 0
    df["class_change"] = df["class_change"].fillna(0).astype(int)

    # --- 斤量偏差（レース内平均との差） ---
    if "weight_carry" in df.columns and "race_key" in df.columns:
        race_avg = df.groupby("race_key")["weight_carry"].transform("mean")
        df["weight_carry_diff"] = df["weight_carry"] - race_avg
    else:
        df["weight_carry_diff"] = 0.0
    df["weight_carry_diff"] = df["weight_carry_diff"].fillna(0.0)

    return df


# =====================================================================
# v3追加特徴量（6項目）
# =====================================================================

def _add_track_bias_score(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    馬場指数: 当日レースの上位3着平均走破タイムと
    過去365日の同会場・同距離・同コース基準タイムの差分。
    負=高速馬場、正=重い馬場。
    """
    if df.empty:
        df["track_bias_score"] = 0.0
        return df

    entry_ids = df["entry_id"].tolist()

    bias_sql = text("""
        WITH curr_race AS (
            SELECT DISTINCT ON (h_entry.id)
                h_entry.id AS entry_id,
                r.race_date,
                r.venue_code,
                r.track_type,
                r.distance
            FROM race_entries h_entry
            JOIN races r ON r.id = h_entry.race_id
            WHERE h_entry.id = ANY(:ids)
        ),
        day_avg AS (
            -- 当日・同会場・同距離・同コースの上位3着平均タイム
            SELECT
                cr.entry_id,
                AVG(re2.finish_time) AS day_time
            FROM curr_race cr
            JOIN races r2 ON r2.race_date = cr.race_date
                          AND r2.venue_code = cr.venue_code
                          AND r2.track_type = cr.track_type
                          AND r2.distance = cr.distance
            JOIN race_entries re2 ON re2.race_id = r2.id
            WHERE re2.finish_order BETWEEN 1 AND 3
              AND re2.finish_time > 0
              AND COALESCE(re2.abnormal_code, 0) = 0
            GROUP BY cr.entry_id
        ),
        base_avg AS (
            -- 過去365日の同会場・同距離・同コース基準タイム
            SELECT
                cr.entry_id,
                AVG(re2.finish_time) AS base_time
            FROM curr_race cr
            JOIN races r2 ON r2.venue_code = cr.venue_code
                          AND r2.track_type = cr.track_type
                          AND r2.distance = cr.distance
                          AND r2.race_date BETWEEN (cr.race_date - 365) AND (cr.race_date - 1)
            JOIN race_entries re2 ON re2.race_id = r2.id
            WHERE re2.finish_order BETWEEN 1 AND 3
              AND re2.finish_time > 0
              AND COALESCE(re2.abnormal_code, 0) = 0
            GROUP BY cr.entry_id
            HAVING COUNT(*) >= 10
        )
        SELECT
            d.entry_id,
            ROUND((d.day_time - b.base_time)::numeric, 1) AS track_bias_score
        FROM day_avg d
        JOIN base_avg b ON b.entry_id = d.entry_id
    """)

    try:
        bias_df = _query_in_batches(db, bias_sql, entry_ids)
        if not bias_df.empty:
            df = df.merge(bias_df, on="entry_id", how="left")
    except Exception:
        pass

    if "track_bias_score" not in df.columns:
        df["track_bias_score"] = 0.0
    df["track_bias_score"] = df["track_bias_score"].fillna(0.0)

    return df


def _add_race_pace_score(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    展開予想スコア（0-100）: 出走馬の脚質分布からペースを推定。
    逃げ・先行馬が多いほどハイペース（スコア大）。
    statistics.pyのpace_predictionロジックを参考にDataFrame向けに最適化。
    """
    if df.empty:
        df["race_pace_score"] = 50.0
        return df

    # レースキーごとに集計（同じレースの全出走馬は同じスコア）
    race_keys = df["race_key"].unique().tolist()

    # 各レースの出走馬の過去3走4コーナー通過順位平均を取得
    pace_sql = text("""
        WITH target_entries AS (
            SELECT re.id AS entry_id, r.race_key, re.horse_id, r.horse_count
            FROM race_entries re
            JOIN races r ON r.id = re.race_id
            WHERE r.race_key = ANY(:rks)
        ),
        past_c4 AS (
            -- 各馬の過去3走の4コーナー平均通過順位
            SELECT
                te.entry_id,
                te.race_key,
                te.horse_id,
                COALESCE(te.horse_count, 16) AS horse_count,
                AVG(sub.corner_4) AS avg_c4
            FROM target_entries te
            LEFT JOIN LATERAL (
                SELECT re2.corner_4
                FROM race_entries re2
                JOIN races r2 ON r2.id = re2.race_id
                WHERE re2.horse_id = te.horse_id
                  AND r2.race_date < (SELECT race_date FROM races WHERE race_key = te.race_key LIMIT 1)
                  AND re2.corner_4 IS NOT NULL AND re2.corner_4 > 0
                ORDER BY r2.race_date DESC
                LIMIT 3
            ) sub ON TRUE
            GROUP BY te.entry_id, te.race_key, te.horse_id, te.horse_count
        )
        SELECT race_key, horse_count,
               -- 前残り馬の割合（4コーナー平均が頭数の1/3以内）
               COALESCE(
                   SUM(CASE WHEN avg_c4 <= horse_count * 0.33 THEN 1.0 ELSE 0.0 END) / NULLIF(COUNT(*), 0),
                   0.3
               ) AS front_ratio
        FROM past_c4
        GROUP BY race_key, horse_count
    """)

    try:
        pace_df = _query_in_batches(db, pace_sql, race_keys, "rks")
        if not pace_df.empty:
            # 前残り比率→ペーススコア（0-100）に変換
            pace_df["race_pace_score"] = (pace_df["front_ratio"] * 150).clip(0, 100).round(1)
            pace_df = pace_df[["race_key", "race_pace_score"]]
            df = df.merge(pace_df, on="race_key", how="left")
    except Exception:
        pass

    if "race_pace_score" not in df.columns:
        df["race_pace_score"] = 50.0
    df["race_pace_score"] = df["race_pace_score"].fillna(50.0)

    return df


def _add_upset_score(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    荒れ予測スコア（0-100）: レース条件から波乱度を加算式で算出。
    - ハンデ戦: +15
    - 多頭数（16頭以上）: +10
    - 重馬場以上（track_cond >= 3）: +10
    - 牝馬限定: +5
    - 条件戦（grade >= 5）: +5
    - ベース: 同条件過去レースの1番人気敗退率 × 100
    statistics.pyのupset_scoreロジックを参考。
    """
    if df.empty:
        df["upset_score"] = 50.0
        return df

    # レースキーごとの条件はbase_selectから既にDFに入っているので直接利用
    def calc_upset(row):
        score = 30.0  # ベーススコア（過去集計は重いのでデフォルト値を使用）
        if row.get("is_handicap", 0) == 1:
            score += 15
        if row.get("horse_count", 0) >= 16:
            score += 10
        if row.get("track_cond", 1) >= 3:
            score += 10
        if row.get("is_female_only", 0) == 1:
            score += 5
        if row.get("grade", 10) >= 5:
            score += 5
        return min(100, max(0, score))

    df["upset_score"] = df.apply(calc_upset, axis=1).astype(float)

    return df


def _add_training_rating_score(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    調教評価スコア（偏差値ベース）: 直近調教の上がり3Fタイムを
    母集団（同コースタイプの過去1年分調教データ）と比較してz-scoreを算出し
    偏差値（mean=50, std=10）に変換する。
    statistics.pyのtraining_ratingロジックを参考。
    """
    if df.empty:
        df["training_rating_score"] = 50.0
        return df

    entry_ids = df["entry_id"].tolist()

    rating_sql = text("""
        WITH latest_train AS (
            -- 各出走馬の直近調教タイム
            SELECT DISTINCT ON (h_entry.id)
                h_entry.id AS entry_id,
                tt.course_type,
                tt.last_3f
            FROM race_entries h_entry
            JOIN races r_curr ON r_curr.id = h_entry.race_id
            JOIN training_times tt ON tt.horse_id = h_entry.horse_id
            WHERE h_entry.id = ANY(:ids)
              AND tt.training_date < r_curr.race_date
              AND tt.training_date >= r_curr.race_date - 30
              AND tt.last_3f IS NOT NULL AND tt.last_3f > 0
            ORDER BY h_entry.id, tt.training_date DESC
        ),
        pop_stats AS (
            -- 母集団統計（コースタイプ別、過去1年）
            SELECT course_type,
                   AVG(last_3f) AS mean_3f,
                   STDDEV(last_3f) AS std_3f
            FROM training_times
            WHERE last_3f IS NOT NULL AND last_3f > 0
              AND training_date >= CURRENT_DATE - 365
            GROUP BY course_type
        )
        SELECT
            lt.entry_id,
            -- 偏差値: タイムが短い=良い → 反転（mean - actual）/ std * 10 + 50
            CASE WHEN ps.std_3f > 0
                 THEN ROUND(((ps.mean_3f - lt.last_3f) / ps.std_3f * 10 + 50)::numeric, 1)
                 ELSE 50.0
            END AS training_rating_score
        FROM latest_train lt
        LEFT JOIN pop_stats ps ON ps.course_type = lt.course_type
    """)

    try:
        rating_df = _query_in_batches(db, rating_sql, entry_ids)
        if not rating_df.empty:
            df = df.merge(rating_df, on="entry_id", how="left")
    except Exception:
        pass

    if "training_rating_score" not in df.columns:
        df["training_rating_score"] = 50.0
    df["training_rating_score"] = df["training_rating_score"].fillna(50.0)

    return df


def _add_pace_change_index(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    PCI（ペースチェンジインデックス）: race_lapsテーブルの
    前半3ハロンと後半3ハロンのペース変化率。
    PCI = 後半3F合計 / 前半3F合計 × 100
    100未満=後半加速（スロー展開）、100超=後半減速（ハイペース展開）。
    同レース出走馬全員が同じ値を持つ。
    """
    if df.empty:
        df["pace_change_index"] = 100.0
        return df

    race_keys = df["race_key"].unique().tolist()

    pci_sql = text("""
        WITH lap_data AS (
            SELECT
                r.race_key,
                rl.hallon_order,
                rl.lap_time,
                -- 総ハロン数
                MAX(rl.hallon_order) OVER (PARTITION BY r.race_key) AS max_hallon
            FROM races r
            JOIN race_laps rl ON rl.race_id = r.id
            WHERE r.race_key = ANY(:rks)
              AND rl.lap_time IS NOT NULL AND rl.lap_time > 0
        ),
        pace AS (
            SELECT
                race_key,
                -- 前半3ハロン（hallon_order 1,2,3）
                SUM(CASE WHEN hallon_order <= 3 THEN lap_time ELSE 0 END) AS first_3f,
                -- 後半3ハロン（最後の3ハロン）
                SUM(CASE WHEN hallon_order > max_hallon - 3 THEN lap_time ELSE 0 END) AS last_3f
            FROM lap_data
            GROUP BY race_key
            HAVING SUM(CASE WHEN hallon_order <= 3 THEN lap_time ELSE 0 END) > 0
        )
        SELECT
            race_key,
            ROUND((last_3f::numeric / first_3f * 100), 1) AS pace_change_index
        FROM pace
    """)

    try:
        pci_df = _query_in_batches(db, pci_sql, race_keys, "rks")
        if not pci_df.empty:
            df = df.merge(pci_df, on="race_key", how="left")
    except Exception:
        pass

    if "pace_change_index" not in df.columns:
        df["pace_change_index"] = 100.0
    df["pace_change_index"] = df["pace_change_index"].fillna(100.0)

    return df


def _add_lineage_track_aptitude(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    血統×馬場適性: 父系統（father_code経由）× 馬場状態（track_cond）の
    過去勝率を算出する。サンプル5件未満はデフォルト0.0。
    lineage_cond_rateとの違い: こちらはtrack_cond(良/稍重/重/不良)を使い、
    lineage_cond_rateはtrack_condのみだが、こちらはtrack_typeも考慮する。
    """
    if df.empty:
        df["lineage_track_aptitude"] = 0.0
        return df

    entry_ids = df["entry_id"].tolist()

    apt_sql = text("""
        SELECT
            h_entry.id AS entry_id,
            CASE WHEN COUNT(*) >= 5
                 THEN SUM(CASE WHEN re_past.finish_order = 1 THEN 1.0 ELSE 0.0 END) / COUNT(*)
                 ELSE 0.0
            END AS lineage_track_aptitude
        FROM race_entries h_entry
        JOIN races r_curr ON r_curr.id = h_entry.race_id
        JOIN horses h ON h.id = h_entry.horse_id
        JOIN race_entries re_past ON TRUE
        JOIN races r_past ON r_past.id = re_past.race_id
        JOIN horses h_past ON h_past.id = re_past.horse_id
        WHERE h_entry.id = ANY(:ids)
          AND h_past.father_code = h.father_code
          AND r_past.track_cond = r_curr.track_cond
          AND r_past.track_type = r_curr.track_type
          AND r_past.race_date < r_curr.race_date
          AND re_past.finish_order IS NOT NULL
          AND COALESCE(re_past.abnormal_code, 0) = 0
        GROUP BY h_entry.id
    """)

    try:
        apt_df = _query_in_batches(db, apt_sql, entry_ids)
        if not apt_df.empty:
            df = df.merge(apt_df, on="entry_id", how="left")
    except Exception:
        pass

    if "lineage_track_aptitude" not in df.columns:
        df["lineage_track_aptitude"] = 0.0
    df["lineage_track_aptitude"] = df["lineage_track_aptitude"].fillna(0.0)

    return df


# =====================================================================
# v5追加: 集計期間パラメータ化による精度向上施策
# =====================================================================

def _add_recent_jockey_stats(db: Session, df: pd.DataFrame, years: int = 3) -> pd.DataFrame:
    """
    騎手の直近N年の勝率でjockey_win_rateを上書きする。
    通算成績（jockeysテーブル）ではなく、race_entriesから直近N年分を集計。
    データが不十分（出走2回未満）な場合は元の通算値を維持する。
    """
    if df.empty:
        return df

    entry_ids = df["entry_id"].tolist()

    jockey_recent_sql = text(f"""
        SELECT
            h_entry.id AS entry_id,
            CASE WHEN COUNT(*) >= 2
                 THEN SUM(CASE WHEN re_past.finish_order = 1 THEN 1.0 ELSE 0.0 END) / COUNT(*)
                 ELSE NULL
            END AS jockey_win_rate_recent
        FROM race_entries h_entry
        JOIN races r_curr ON r_curr.id = h_entry.race_id
        JOIN race_entries re_past ON re_past.jockey_id = h_entry.jockey_id
        JOIN races r_past ON r_past.id = re_past.race_id
        WHERE h_entry.id = ANY(:ids)
          AND r_past.race_date < r_curr.race_date
          AND r_past.race_date >= r_curr.race_date - INTERVAL '{years} years'
          AND re_past.finish_order IS NOT NULL
          AND COALESCE(re_past.abnormal_code, 0) = 0
        GROUP BY h_entry.id
    """)
    try:
        jockey_df = _query_in_batches(db, jockey_recent_sql, entry_ids)
        if not jockey_df.empty:
            df = df.merge(jockey_df, on="entry_id", how="left")
            # 直近データがある場合のみ上書き（NULLの場合は通算値を維持）
            mask = df["jockey_win_rate_recent"].notna()
            df.loc[mask, "jockey_win_rate"] = df.loc[mask, "jockey_win_rate_recent"]
            df = df.drop(columns=["jockey_win_rate_recent"])
    except Exception:
        pass  # エラー時は通算値のまま

    return df


def _add_recent_trainer_stats(db: Session, df: pd.DataFrame, years: int = 3) -> pd.DataFrame:
    """
    調教師の直近N年の勝率でtrainer_win_rateを上書きする。
    通算成績（trainersテーブル）ではなく、race_entriesから直近N年分を集計。
    データが不十分（出走5回未満）な場合は元の通算値を維持する。
    """
    if df.empty:
        return df

    entry_ids = df["entry_id"].tolist()

    trainer_recent_sql = text(f"""
        SELECT
            h_entry.id AS entry_id,
            CASE WHEN COUNT(*) >= 5
                 THEN SUM(CASE WHEN re_past.finish_order = 1 THEN 1.0 ELSE 0.0 END) / COUNT(*)
                 ELSE NULL
            END AS trainer_win_rate_recent
        FROM race_entries h_entry
        JOIN races r_curr ON r_curr.id = h_entry.race_id
        JOIN race_entries re_past ON re_past.trainer_id = h_entry.trainer_id
        JOIN races r_past ON r_past.id = re_past.race_id
        WHERE h_entry.id = ANY(:ids)
          AND r_past.race_date < r_curr.race_date
          AND r_past.race_date >= r_curr.race_date - INTERVAL '{years} years'
          AND re_past.finish_order IS NOT NULL
          AND COALESCE(re_past.abnormal_code, 0) = 0
        GROUP BY h_entry.id
    """)
    try:
        trainer_df = _query_in_batches(db, trainer_recent_sql, entry_ids)
        if not trainer_df.empty:
            df = df.merge(trainer_df, on="entry_id", how="left")
            # 直近データがある場合のみ上書き（NULLの場合は通算値を維持）
            mask = df["trainer_win_rate_recent"].notna()
            df.loc[mask, "trainer_win_rate"] = df.loc[mask, "trainer_win_rate_recent"]
            df = df.drop(columns=["trainer_win_rate_recent"])
    except Exception:
        pass  # エラー時は通算値のまま

    return df


def _add_weighted_horse_stats(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    馬の通算成績（horse_win_rate, horse_earnings_per_race）を
    直近2年の加重平均で上書きする。
    加重方式: 直近2年 × 2.0 + 全期間 × 1.0 → 合計 / 3.0
    直近2年のデータが不十分（出走2回未満）な場合は元の通算値を維持する。
    """
    if df.empty:
        return df

    entry_ids = df["entry_id"].tolist()

    horse_recent_sql = text("""
        SELECT
            h_entry.id AS entry_id,
            CASE WHEN COUNT(*) >= 2
                 THEN SUM(CASE WHEN re_past.finish_order = 1 THEN 1.0 ELSE 0.0 END) / COUNT(*)
                 ELSE NULL
            END AS horse_win_rate_recent,
            CASE WHEN COUNT(*) >= 2
                 THEN SUM(COALESCE(re_past.prize_money, 0)::float) / COUNT(*)
                 ELSE NULL
            END AS horse_earnings_recent
        FROM race_entries h_entry
        JOIN races r_curr ON r_curr.id = h_entry.race_id
        JOIN race_entries re_past ON re_past.horse_id = h_entry.horse_id
        JOIN races r_past ON r_past.id = re_past.race_id
        WHERE h_entry.id = ANY(:ids)
          AND r_past.race_date < r_curr.race_date
          AND r_past.race_date >= r_curr.race_date - INTERVAL '2 years'
          AND re_past.finish_order IS NOT NULL
          AND COALESCE(re_past.abnormal_code, 0) = 0
        GROUP BY h_entry.id
    """)
    try:
        horse_df = _query_in_batches(db, horse_recent_sql, entry_ids)
        if not horse_df.empty:
            df = df.merge(horse_df, on="entry_id", how="left")
            # 加重平均: 直近2年 × 2.0 + 全期間 × 1.0 → / 3.0
            mask_wr = df["horse_win_rate_recent"].notna()
            df.loc[mask_wr, "horse_win_rate"] = (
                df.loc[mask_wr, "horse_win_rate_recent"] * 2.0
                + df.loc[mask_wr, "horse_win_rate"]
            ) / 3.0
            mask_er = df["horse_earnings_recent"].notna()
            df.loc[mask_er, "horse_earnings_per_race"] = (
                df.loc[mask_er, "horse_earnings_recent"] * 2.0
                + df.loc[mask_er, "horse_earnings_per_race"]
            ) / 3.0
            df = df.drop(columns=["horse_win_rate_recent", "horse_earnings_recent"], errors="ignore")
    except Exception:
        pass  # エラー時は通算値のまま

    return df


# =====================================================================
# v4追加特徴量（SEパーサー拡張由来: 4項目）
# =====================================================================

def _add_se_extended_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    SEレコード拡張フィールドからAI特徴量を生成する。
    - blinker_flag: ブリンカー使用フラグ（0/1）
    - is_apprentice: 見習騎手フラグ（0/1）
    - has_jockey_change_official: 公式騎手変更フラグ（prev_jockey_codeが空でない場合1）
    - belong_region: 東西所属（1=関東, 2=関西, 3=地方）
    """
    # ブリンカー使用フラグ（blinker_code=1 なら使用）
    if "blinker_code" in df.columns:
        df["blinker_flag"] = (df["blinker_code"] == 1).astype(int)
    else:
        df["blinker_flag"] = 0

    # 見習騎手フラグ（apprentice_code > 0 なら見習）
    if "apprentice_code" in df.columns:
        df["is_apprentice"] = (df["apprentice_code"] > 0).astype(int)
    else:
        df["is_apprentice"] = 0

    # 公式騎手変更フラグ（prev_jockey_codeが空でない場合1）
    if "prev_jockey_code" in df.columns:
        df["has_jockey_change_official"] = df["prev_jockey_code"].notna().astype(int)
    else:
        df["has_jockey_change_official"] = 0

    # 東西所属（DBの値をそのまま使用、NULLは0）
    if "belong_region" not in df.columns:
        df["belong_region"] = 0
    df["belong_region"] = df["belong_region"].fillna(0).astype(int)

    return df


# =====================================================================
# v5追加特徴量（フェーズ1拡張: +20項目）
# =====================================================================

import math  # noqa: E402（ファイル末尾での追加import）


def _add_v5_odds_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    複勝オッズ関連の特徴量を追加する。
    - odds_place_avg: 複勝オッズ中央値（市場の評価指標）
    - odds_place_range: 複勝オッズ幅（不確実性指標）
    - odds_win_place_ratio: 単勝/複勝比（穴馬検出用）
    """
    # 複勝オッズ中央値
    pmin = df.get("odds_place_min", pd.Series(dtype=float)).fillna(0.0)
    pmax = df.get("odds_place_max", pd.Series(dtype=float)).fillna(0.0)
    df["odds_place_avg"] = (pmin + pmax) / 2.0

    # 複勝オッズ幅（不確実性指標: 幅が大きいほど市場が割れている）
    df["odds_place_range"] = (pmax - pmin).clip(lower=0.0)

    # 単勝/複勝比（複勝中央値が0の場合はデフォルト3.0）
    place_avg = df["odds_place_avg"].replace(0.0, float("nan"))
    df["odds_win_place_ratio"] = (df["odds_win"] / place_avg).fillna(3.0).clip(upper=20.0)

    return df


def _add_v5_weight_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    斤量の高度な分析特徴量を追加する。
    - weight_carry_per_kg: 斤量÷馬体重（負荷率）
    - prev_weight_carry_diff: 斤量変更幅（前走比）
    """
    # 斤量÷馬体重（負荷率: 通常0.10〜0.13程度）
    hw = df["horse_weight"].replace(0, float("nan"))
    df["weight_carry_per_kg"] = (df["weight_carry"] / hw).fillna(0.115)

    # 斤量変更幅（prev_weight_carry がある場合のみ）
    if "prev_weight_carry" in df.columns:
        prev_wc = pd.to_numeric(df["prev_weight_carry"], errors="coerce")
        df["prev_weight_carry_diff"] = (df["weight_carry"] - prev_wc).fillna(0.0)
    else:
        df["prev_weight_carry_diff"] = 0.0

    return df


def _add_v5_corner_features(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    コーナー通過順位の多角的分析を追加する（過去走ベース）。
    - recent_avg_corner1: 直近3走の1コーナー通過順位平均
    - recent_corner_improvement: 直近3走の1角→4角の順位改善度平均
    - recent_corner4_std: 直近3走の4角通過順位の標準偏差（脚質安定性）
    """
    defaults = {
        "recent_avg_corner1": 8.0,
        "recent_corner_improvement": 0.0,
        "recent_corner4_std": 3.0,
    }

    if df.empty:
        for col, val in defaults.items():
            df[col] = val
        return df

    entry_ids = df["entry_id"].tolist()

    corner_sql = text("""
        WITH ranked AS (
            SELECT
                h_entry.id AS entry_id,
                re_past.corner_1,
                re_past.corner_4,
                ROW_NUMBER() OVER (
                    PARTITION BY h_entry.id
                    ORDER BY r_past.race_date DESC, r_past.race_key DESC
                ) AS rn
            FROM race_entries h_entry
            JOIN races r_curr ON r_curr.id = h_entry.race_id
            JOIN race_entries re_past ON re_past.horse_id = h_entry.horse_id
            JOIN races r_past ON r_past.id = re_past.race_id
            WHERE h_entry.id = ANY(:ids)
              AND r_past.race_date < r_curr.race_date
              AND re_past.finish_order IS NOT NULL
              AND COALESCE(re_past.abnormal_code, 0) = 0
        )
        SELECT
            entry_id,
            AVG(CASE WHEN rn <= 3 AND corner_1 > 0 THEN corner_1 END)
                AS recent_avg_corner1,
            AVG(CASE WHEN rn <= 3 AND corner_1 > 0 AND corner_4 > 0
                     THEN corner_1 - corner_4 END)
                AS recent_corner_improvement,
            STDDEV(CASE WHEN rn <= 3 AND corner_4 > 0 THEN corner_4 END)
                AS recent_corner4_std
        FROM ranked
        WHERE rn <= 3
        GROUP BY entry_id
    """)
    corner_df = _query_in_batches(db, corner_sql, entry_ids)
    df = _safe_merge(df, corner_df, on="entry_id")

    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(val)

    return df


def _add_v5_performance_features(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    パフォーマンス指標の追加特徴量。
    - recent_avg_margin: 直近3走の着差平均
    - recent_speed_index_std: 直近3走のタイム指数の標準偏差（安定性）
    - recent_best_speed_index: 直近5走のタイム指数最高値
    - recent_last_3f_best: 直近5走の上がり3F最速
    """
    defaults = {
        "recent_avg_margin": 5.0,
        "recent_speed_index_std": 5.0,
        "recent_best_speed_index": 0.0,
        "recent_last_3f_best": 0.0,
    }

    if df.empty:
        for col, val in defaults.items():
            df[col] = val
        return df

    entry_ids = df["entry_id"].tolist()

    perf_sql = text("""
        WITH ranked AS (
            SELECT
                h_entry.id AS entry_id,
                re_past.margin,
                re_past.speed_index,
                re_past.last_3f,
                ROW_NUMBER() OVER (
                    PARTITION BY h_entry.id
                    ORDER BY r_past.race_date DESC, r_past.race_key DESC
                ) AS rn
            FROM race_entries h_entry
            JOIN races r_curr ON r_curr.id = h_entry.race_id
            JOIN race_entries re_past ON re_past.horse_id = h_entry.horse_id
            JOIN races r_past ON r_past.id = re_past.race_id
            WHERE h_entry.id = ANY(:ids)
              AND r_past.race_date < r_curr.race_date
              AND re_past.finish_order IS NOT NULL
              AND COALESCE(re_past.abnormal_code, 0) = 0
        )
        SELECT
            entry_id,
            -- 直近3走の着差平均
            AVG(CASE WHEN rn <= 3 THEN COALESCE(margin, 0) END)
                AS recent_avg_margin,
            -- 直近3走のタイム指数の標準偏差（安定性指標）
            STDDEV(CASE WHEN rn <= 3 AND speed_index IS NOT NULL
                        THEN speed_index END)
                AS recent_speed_index_std,
            -- 直近5走のタイム指数最高値
            MAX(CASE WHEN rn <= 5 AND speed_index IS NOT NULL
                     THEN speed_index END)
                AS recent_best_speed_index,
            -- 直近5走の上がり3F最速
            MIN(CASE WHEN rn <= 5 AND last_3f > 0 THEN last_3f END)
                AS recent_last_3f_best
        FROM ranked
        WHERE rn <= 5
        GROUP BY entry_id
    """)
    perf_df = _query_in_batches(db, perf_sql, entry_ids)
    df = _safe_merge(df, perf_df, on="entry_id")

    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(val)

    return df


def _add_v5_jockey_trainer_efficiency(df: pd.DataFrame) -> pd.DataFrame:
    """
    騎手・調教師の効率性指標を追加する（SQLクエリ不要、SELECT句の値から計算）。
    - jockey_place_rate: 騎手の複勝率
    - jockey_experience_years: 騎手の経験年数
    - trainer_place_rate: 調教師の複勝率
    """
    # 騎手の複勝率（1着+2着+3着 / 全レース）
    jt = df.get("jockey_total_races", pd.Series(dtype=int)).fillna(0)
    j2 = df.get("jockey_total_2nd", pd.Series(dtype=int)).fillna(0)
    j3 = df.get("jockey_total_3rd", pd.Series(dtype=int)).fillna(0)
    # jockey_win_rateから1着数を逆算（win_rate = 1st / total）
    j1_est = (df["jockey_win_rate"] * jt).fillna(0)
    df["jockey_place_rate"] = ((j1_est + j2 + j3) / jt.replace(0, float("nan"))).fillna(0.0)

    # 騎手の経験年数（birth_dateからrace_dateまでの年数）
    if "jockey_birth_date" in df.columns and "race_date" in df.columns:
        jbd = pd.to_datetime(df["jockey_birth_date"], errors="coerce")
        rd = pd.to_datetime(df["race_date"], errors="coerce")
        # 経験年数 ≈ (レース日 - 誕生日) / 365.25 - 18歳でデビューと仮定
        raw_years = ((rd - jbd).dt.days / 365.25 - 18).clip(lower=0)
        df["jockey_experience_years"] = raw_years.fillna(10.0)
    else:
        df["jockey_experience_years"] = 10.0

    # 調教師の複勝率（trainersにtotal_2nd/3rdがないためwin_rateから推定）
    tt = df.get("trainer_total_races", pd.Series(dtype=int)).fillna(0)
    t1_est = (df["trainer_win_rate"] * tt).fillna(0)
    # 複勝率 ≈ 勝率 × 2.5（統計的近似）
    df["trainer_place_rate"] = (df["trainer_win_rate"] * 2.5).clip(upper=1.0).fillna(0.0)

    return df


def _add_v5_venue_cond_aptitude(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    会場別・馬場状態別の適性を追加する。
    - same_venue_win_rate: 同会場での過去3年勝率
    - track_cond_aptitude: 馬場状態別の過去勝率
    """
    defaults = {
        "same_venue_win_rate": 0.0,
        "track_cond_aptitude": 0.0,
    }

    if df.empty:
        for col, val in defaults.items():
            df[col] = val
        return df

    entry_ids = df["entry_id"].tolist()

    venue_sql = text("""
        WITH curr AS (
            SELECT
                re.id AS entry_id,
                re.horse_id,
                r.race_date,
                r.venue_code,
                COALESCE(r.track_cond, 1) AS track_cond
            FROM race_entries re
            JOIN races r ON r.id = re.race_id
            WHERE re.id = ANY(:ids)
        ),
        past_stats AS (
            SELECT
                c.entry_id,
                -- 同会場での勝率
                AVG(CASE
                    WHEN r_past.venue_code = c.venue_code
                    THEN CASE WHEN re_past.finish_order = 1 THEN 1.0 ELSE 0.0 END
                END) AS same_venue_win_rate,
                -- 同馬場状態での勝率
                AVG(CASE
                    WHEN COALESCE(r_past.track_cond, 1) = c.track_cond
                    THEN CASE WHEN re_past.finish_order = 1 THEN 1.0 ELSE 0.0 END
                END) AS track_cond_aptitude
            FROM curr c
            JOIN race_entries re_past ON re_past.horse_id = c.horse_id
            JOIN races r_past ON r_past.id = re_past.race_id
            WHERE r_past.race_date < c.race_date
              AND r_past.race_date >= c.race_date - INTERVAL '3 years'
              AND re_past.finish_order IS NOT NULL
              AND COALESCE(re_past.abnormal_code, 0) = 0
            GROUP BY c.entry_id
        )
        SELECT * FROM past_stats
    """)
    venue_df = _query_in_batches(db, venue_sql, entry_ids)
    df = _safe_merge(df, venue_df, on="entry_id")

    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(val)

    return df


def _add_v5_race_condition_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    レース条件の追加特徴量（SQLクエリ不要、SELECT句の値から計算）。
    - condition_code: 競走条件コード（クラス詳細）
    - prize_1st_log: 1着賞金の対数（レースの格指標）
    - nichi_in_kai: 開催日次（馬場の荒れ具合指標）
    """
    # 競走条件コード（DBの値をそのまま使用）
    if "condition_code" not in df.columns:
        df["condition_code"] = 0
    df["condition_code"] = df["condition_code"].fillna(0).astype(int)

    # 1着賞金の対数（0の場合はデフォルト）
    p1 = df.get("prize_1st", pd.Series(dtype=float)).fillna(0).replace(0, 1)
    df["prize_1st_log"] = p1.apply(lambda x: math.log(max(x, 1)))

    # 開催日次（nichi: 1日目〜12日目程度。後半ほど馬場が荒れる）
    if "nichi" not in df.columns:
        df["nichi_in_kai"] = 4
    else:
        df["nichi_in_kai"] = df["nichi"].fillna(4).astype(int)

    return df


# ===== v6追加: 精度向上特徴量 =====

def _add_v6_trend_features(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    直近成績のトレンド（上昇/下降）を追加。
    直近3走の着順が改善傾向なら正、悪化傾向なら負。
    """
    if df.empty:
        df["recent_win_trend"] = 0.0
        return df

    entry_ids = df["entry_id"].tolist()
    trend_sql = text("""
        WITH ranked AS (
            SELECT
                h_entry.id AS entry_id,
                re_past.finish_order,
                ROW_NUMBER() OVER (
                    PARTITION BY h_entry.id
                    ORDER BY r_past.race_date DESC, r_past.race_key DESC
                ) AS rn
            FROM race_entries h_entry
            JOIN races r_curr ON r_curr.id = h_entry.race_id
            JOIN race_entries re_past ON re_past.horse_id = h_entry.horse_id
            JOIN races r_past ON r_past.id = re_past.race_id
            WHERE h_entry.id = ANY(:ids)
              AND r_past.race_date < r_curr.race_date
              AND re_past.finish_order IS NOT NULL
              AND COALESCE(re_past.abnormal_code, 0) = 0
        )
        SELECT entry_id,
            -- トレンド: (1走前の着順 - 3走前の着順) / 2。正=改善、負=悪化
            COALESCE(
                (MAX(CASE WHEN rn = 3 THEN finish_order END)
                 - MAX(CASE WHEN rn = 1 THEN finish_order END)) / 2.0,
                0
            ) AS recent_win_trend
        FROM ranked
        WHERE rn <= 3
        GROUP BY entry_id
    """)
    trend_df = _query_in_batches(db, trend_sql, entry_ids)
    df = _safe_merge(df, trend_df, on="entry_id")
    if "recent_win_trend" not in df.columns:
        df["recent_win_trend"] = 0.0
    else:
        df["recent_win_trend"] = pd.to_numeric(df["recent_win_trend"], errors="coerce").fillna(0.0)
    return df


def _add_v6_jockey_trainer_combo(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    騎手×調教師コンビの過去勝率を追加。
    """
    if df.empty:
        df["jockey_trainer_combo_rate"] = 0.0
        return df

    entry_ids = df["entry_id"].tolist()
    combo_sql = text("""
        WITH curr AS (
            SELECT re.id AS entry_id, re.jockey_code, re.trainer_code, r.race_date
            FROM race_entries re
            JOIN races r ON r.id = re.race_id
            WHERE re.id = ANY(:ids)
        ),
        combo_stats AS (
            SELECT c.entry_id,
                AVG(CASE WHEN re_past.finish_order = 1 THEN 1.0 ELSE 0.0 END) AS combo_rate
            FROM curr c
            JOIN race_entries re_past
                ON re_past.jockey_code = c.jockey_code
                AND re_past.trainer_code = c.trainer_code
                AND c.jockey_code IS NOT NULL AND c.jockey_code != ''
                AND c.trainer_code IS NOT NULL AND c.trainer_code != ''
            JOIN races r_past ON r_past.id = re_past.race_id
            WHERE r_past.race_date < c.race_date
              AND r_past.race_date >= c.race_date - INTERVAL '3 years'
              AND re_past.finish_order IS NOT NULL
              AND COALESCE(re_past.abnormal_code, 0) = 0
            GROUP BY c.entry_id
        )
        SELECT * FROM combo_stats
    """)
    combo_df = _query_in_batches(db, combo_sql, entry_ids)
    df = _safe_merge(df, combo_df, on="entry_id")
    if "jockey_trainer_combo_rate" not in df.columns:
        df["jockey_trainer_combo_rate"] = 0.0
    else:
        df["jockey_trainer_combo_rate"] = pd.to_numeric(
            df["jockey_trainer_combo_rate"], errors="coerce"
        ).fillna(0.0).rename("jockey_trainer_combo_rate")
        # combo_rateカラム名をFEATURE_COLSに合わせる
        if "combo_rate" in df.columns and "jockey_trainer_combo_rate" not in df.columns:
            df["jockey_trainer_combo_rate"] = df["combo_rate"]
        elif "combo_rate" in df.columns:
            df["jockey_trainer_combo_rate"] = pd.to_numeric(df["combo_rate"], errors="coerce").fillna(0.0)
            df.drop(columns=["combo_rate"], inplace=True, errors="ignore")
    return df


def _add_v6_pace_style_fit(df: pd.DataFrame) -> pd.DataFrame:
    """
    脚質と展開の適合度スコア。
    先行馬×スローペース=有利(正)、差し馬×ハイペース=有利(正)。
    """
    corner4 = df.get("recent_avg_corner4", pd.Series(8.0, index=df.index)).fillna(8.0)
    pace = df.get("race_pace_score", pd.Series(50.0, index=df.index)).fillna(50.0)

    # 脚質タイプ: corner4≤3=先行(1), 4-7=中団(0), 8+=追込(-1)
    style = pd.Series(0.0, index=df.index)
    style = style.where(corner4 > 3, 1.0)    # 先行
    style = style.where(corner4 <= 7, -1.0)   # 追込

    # ペース: <40=スロー(1), 40-60=平均(0), >60=ハイ(-1)
    pace_type = pd.Series(0.0, index=df.index)
    pace_type = pace_type.where(pace >= 40, 1.0)   # スロー
    pace_type = pace_type.where(pace <= 60, -1.0)   # ハイ

    # 適合度: 先行×スロー=2, 追込×ハイ=2, 不利な組合せ=-2
    # style*pace_type: 先行(1)×スロー(1)=1(有利), 追込(-1)×ハイ(-1)=1(有利)
    df["pace_style_fit"] = (style * pace_type).fillna(0.0)

    return df
