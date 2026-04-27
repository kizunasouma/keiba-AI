"""
特徴量エンジニアリングのテスト
FEATURE_COLSの定義とユーティリティ関数のテスト
"""
from app.ml.features import (
    FEATURE_COLS,
    FEATURE_COLS_NO_ODDS,
    TARGET_COL,
    RANK_TARGET_COL,
)


def test_feature_cols_count():
    """特徴量数が74項目であること（v5拡張後）"""
    assert len(FEATURE_COLS) == 74


def test_feature_cols_no_odds():
    """オッズなし特徴量にodds_win/popularityが含まれないこと"""
    assert "odds_win" not in FEATURE_COLS_NO_ODDS
    assert "popularity" not in FEATURE_COLS_NO_ODDS
    assert len(FEATURE_COLS_NO_ODDS) == len(FEATURE_COLS) - 2


def test_feature_cols_no_duplicates():
    """特徴量名に重複がないこと"""
    assert len(FEATURE_COLS) == len(set(FEATURE_COLS))


def test_target_col():
    """目的変数が正しく定義されていること"""
    assert TARGET_COL == "is_win"
    assert RANK_TARGET_COL == "rank_label"


def test_v5_features_included():
    """v5追加特徴量がFEATURE_COLSに含まれていること"""
    v5_features = [
        "odds_place_avg", "odds_place_range", "odds_win_place_ratio",
        "weight_carry_per_kg", "prev_weight_carry_diff",
        "recent_avg_corner1", "recent_corner_improvement", "recent_corner4_std",
        "recent_avg_margin", "recent_speed_index_std",
        "recent_best_speed_index", "recent_last_3f_best",
        "jockey_place_rate", "jockey_experience_years", "trainer_place_rate",
        "same_venue_win_rate", "track_cond_aptitude",
        "condition_code", "prize_1st_log", "nichi_in_kai",
    ]
    for feat in v5_features:
        assert feat in FEATURE_COLS, f"{feat} がFEATURE_COLSに含まれていない"
