"""
AIモデルラッパー（v2: アンサンブル対応）
勝利確率の予測と期待値の算出を担当する

【モデル構成】
1. LightGBM Classifier（二値分類: 勝ち/負け）— ベースライン
2. LightGBM Ranker（LambdaRank: レース内順位予測）— ランキング学習
3. CatBoost Classifier（カテゴリ特徴量に強い）— アンサンブル用
4. オッズなしモデル（市場バイアスを排除して期待値戦略に使う）

【期待値算出】
- オッズありモデル: 高精度な勝率予測
- オッズなしモデル: 市場の過小評価馬を発見（EV = P_no_odds × odds - 1）
- 最終推奨: 両モデルの期待値が正の馬を推奨
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any

import lightgbm as lgb

logger = logging.getLogger(__name__)
import numpy as np
import pandas as pd
try:
    from catboost import CatBoostClassifier
except ImportError:
    CatBoostClassifier = None  # type: ignore
try:
    import optuna
    from optuna.integration import LightGBMPruningCallback
    from optuna.integration.lightgbm import LightGBMTunerCV
    try:
        from optuna.integration import CatBoostPruningCallback
    except ImportError:
        CatBoostPruningCallback = None  # type: ignore
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    LightGBMPruningCallback = None  # type: ignore
    LightGBMTunerCV = None  # type: ignore
    CatBoostPruningCallback = None  # type: ignore
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from app.ml.features import (
    FEATURE_COLS, FEATURE_COLS_NO_ODDS,
    TARGET_COL, RANK_TARGET_COL,
)

# モデルファイルの保存パス
MODEL_DIR = Path(__file__).parent.parent.parent.parent / "models"
DEFAULT_MODEL_PATH = MODEL_DIR / "lgbm_win.pkl"
ENSEMBLE_MODEL_PATH = MODEL_DIR / "ensemble_v2.pkl"
SPECIALIZED_MODEL_PATH = MODEL_DIR / "specialized_v1.pkl"

# LightGBM Classifier ハイパーパラメータ
LGBM_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "metric": "auc",
    "boosting_type": "gbdt",
    "num_leaves": 63,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "min_child_samples": 20,
    "lambda_l1": 0.1,
    "lambda_l2": 0.1,
    "verbose": -1,
    "n_jobs": -1,
    "seed": 42,
}

# LightGBM Ranker ハイパーパラメータ（LambdaRank）
LGBM_RANKER_PARAMS: dict[str, Any] = {
    "objective": "lambdarank",
    "metric": "ndcg",
    "boosting_type": "gbdt",
    "num_leaves": 63,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "min_child_samples": 20,
    "lambda_l1": 0.1,
    "lambda_l2": 0.1,
    "verbose": -1,
    "n_jobs": -1,
    "seed": 42,
    "label_gain": list(range(18, -1, -1)),  # 18頭立てまで対応
}

# CatBoost ハイパーパラメータ
CATBOOST_PARAMS: dict[str, Any] = {
    "iterations": 500,
    "learning_rate": 0.05,
    "depth": 8,
    "l2_leaf_reg": 3.0,
    "random_seed": 42,
    "verbose": 0,
    "eval_metric": "AUC",
    "auto_class_weights": "Balanced",
}

NUM_BOOST_ROUND = 500
EARLY_STOPPING_ROUNDS = 50


class WinProbabilityModel:
    """
    単勝勝率予測モデル（後方互換: 従来のClassifierのみ版）
    学習・保存・ロード・予測・期待値算出を提供する
    """

    def __init__(self) -> None:
        self._model: lgb.Booster | None = None
        self._feature_importance: pd.DataFrame | None = None

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def train(self, df: pd.DataFrame) -> dict[str, float]:
        """
        学習データを受け取ってモデルを訓練する。
        GroupKFold（レースIDでグループ化）でデータリークを防ぐ。
        """
        X = df[FEATURE_COLS].copy()
        y = df[TARGET_COL].copy()
        groups = pd.factorize(df["race_key"])[0]

        kf = GroupKFold(n_splits=5)
        auc_scores: list[float] = []
        best_model: lgb.Booster | None = None
        best_auc = 0.0

        for fold, (train_idx, val_idx) in enumerate(kf.split(X, y, groups)):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

            dtrain = lgb.Dataset(X_train, label=y_train, feature_name=FEATURE_COLS)
            dval = lgb.Dataset(X_val, label=y_val, feature_name=FEATURE_COLS, reference=dtrain)

            callbacks = [
                lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False),
                lgb.log_evaluation(period=-1),
            ]

            model = lgb.train(
                LGBM_PARAMS, dtrain,
                num_boost_round=NUM_BOOST_ROUND,
                valid_sets=[dval],
                callbacks=callbacks,
            )

            val_pred = model.predict(X_val)
            auc = roc_auc_score(y_val, val_pred)
            auc_scores.append(auc)
            print(f"  Fold {fold + 1}: AUC = {auc:.4f} (best_iter={model.best_iteration})")

            if auc > best_auc:
                best_auc = auc
                best_model = model

        self._model = best_model

        if best_model is not None:
            self._feature_importance = pd.DataFrame({
                "feature": FEATURE_COLS,
                "importance": best_model.feature_importance(importance_type="gain"),
            }).sort_values("importance", ascending=False)

        result = {
            "mean_auc": float(np.mean(auc_scores)),
            "std_auc": float(np.std(auc_scores)),
        }
        print(f"\n  CV AUC: {result['mean_auc']:.4f} ± {result['std_auc']:.4f}")
        return result

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("モデルが学習されていません。train() を先に実行してください。")
        X = df[FEATURE_COLS].copy()
        return self._model.predict(X)

    def predict_with_ev(self, df: pd.DataFrame) -> pd.DataFrame:
        """予測確率と期待値を計算して返す。"""
        proba = self.predict_proba(df)

        result = df[["entry_id", "horse_num", "horse_name", "jockey_name", "odds_win_raw"]].copy()
        result["win_prob"] = proba
        odds = df["odds_win_raw"].fillna(50.0)
        result["expected_value"] = proba * odds - 1.0
        result["recommendation"] = result["expected_value"].apply(_ev_label)

        return result.sort_values("win_prob", ascending=False).reset_index(drop=True)

    def get_feature_importance(self) -> pd.DataFrame | None:
        return self._feature_importance

    def save(self, path: Path | str = DEFAULT_MODEL_PATH) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self._model, f)
        print(f"モデルを保存しました: {path}")

    def load(self, path: Path | str = DEFAULT_MODEL_PATH) -> None:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"モデルファイルが見つかりません: {path}")
        with open(path, "rb") as f:
            self._model = pickle.load(f)


# --- 条件別特化LightGBMパラメータ（軽量版）---
LGBM_SPECIALIZED_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "metric": "auc",
    "boosting_type": "gbdt",
    "num_leaves": 31,          # メインより少なめ（過学習防止）
    "learning_rate": 0.05,
    "feature_fraction": 0.75,
    "bagging_fraction": 0.75,
    "bagging_freq": 5,
    "min_child_samples": 30,   # セグメントはデータ少なめなので正則化強め
    "lambda_l1": 0.3,
    "lambda_l2": 0.3,
    "verbose": -1,
    "n_jobs": -1,
    "seed": 42,
}

# 特化モデルの学習ラウンド数（軽量）
SPECIALIZED_NUM_BOOST_ROUND = 300
SPECIALIZED_EARLY_STOPPING = 30


class SpecializedModel:
    """
    条件別特化モデル（芝/ダート × 距離帯）

    会場別特化で回収率285%の事例を参考に、コース種別×距離帯でセグメント分割し、
    各セグメントごとにLightGBM Classifierを学習する。
    メインのEnsembleModelと加重平均してアンサンブル予測に利用する。

    【セグメント構成】 7分割
    - 芝スプリント (〜1400m) / 芝マイル (1401-1800m) / 芝中距離 (1801-2200m) / 芝長距離 (2201m〜)
    - ダートスプリント (〜1400m) / ダートマイル (1401-1800m) / ダートロング (1801m〜)
    """

    # セグメント定義: track_type=1(芝), 2(ダート)
    # v5拡張: 芝/ダート × 距離帯（7セグメント）+ 主要会場別（10セグメント）= 17セグメント
    SEGMENTS: dict[str, dict] = {
        # 基本セグメント（芝/ダート × 距離帯）
        "turf_sprint":  {"track_type": 1, "distance_min": 0,    "distance_max": 1400},
        "turf_mile":    {"track_type": 1, "distance_min": 1401, "distance_max": 1800},
        "turf_middle":  {"track_type": 1, "distance_min": 1801, "distance_max": 2200},
        "turf_long":    {"track_type": 1, "distance_min": 2201, "distance_max": 9999},
        "dirt_sprint":  {"track_type": 2, "distance_min": 0,    "distance_max": 1400},
        "dirt_mile":    {"track_type": 2, "distance_min": 1401, "distance_max": 1800},
        "dirt_long":    {"track_type": 2, "distance_min": 1801, "distance_max": 9999},
        # v5追加: 主要会場別セグメント（会場特有の傾向をキャプチャ）
        "venue_tokyo":    {"venue_code": 5,  "distance_min": 0, "distance_max": 9999},
        "venue_nakayama": {"venue_code": 6,  "distance_min": 0, "distance_max": 9999},
        "venue_hanshin":  {"venue_code": 9,  "distance_min": 0, "distance_max": 9999},
        "venue_kyoto":    {"venue_code": 8,  "distance_min": 0, "distance_max": 9999},
        "venue_chukyo":   {"venue_code": 7,  "distance_min": 0, "distance_max": 9999},
        "venue_kokura":   {"venue_code": 10, "distance_min": 0, "distance_max": 9999},
        "venue_niigata":  {"venue_code": 4,  "distance_min": 0, "distance_max": 9999},
        "venue_fukushima": {"venue_code": 3, "distance_min": 0, "distance_max": 9999},
        "venue_sapporo":  {"venue_code": 1,  "distance_min": 0, "distance_max": 9999},
        "venue_hakodate":  {"venue_code": 2, "distance_min": 0, "distance_max": 9999},
    }

    # セグメントごとの最低学習データ数（これ未満はスキップ）
    MIN_SAMPLES = 1000

    def __init__(self) -> None:
        # セグメント名 → 学習済みLightGBM Booster
        self._models: dict[str, lgb.Booster] = {}
        # セグメント名 → CV AUC（効果検証用）
        self._segment_aucs: dict[str, float] = {}
        # 使用する特徴量列（FEATURE_COLSと同じ）
        self._feature_cols: list[str] = FEATURE_COLS

    @property
    def is_trained(self) -> bool:
        return len(self._models) > 0

    @property
    def trained_segments(self) -> list[str]:
        """学習済みセグメント名リスト"""
        return list(self._models.keys())

    def _get_segment_name(self, track_type: int, distance: int, venue_code: int | None = None) -> str | None:
        """track_typeとdistanceから該当セグメント名を返す。該当なしはNone。
        会場別セグメントがあればそちらを優先する。"""
        # まず会場別セグメントをチェック（より特化した予測が可能）
        if venue_code is not None:
            for seg_name, cond in self.SEGMENTS.items():
                if ("venue_code" in cond
                        and venue_code == cond["venue_code"]
                        and seg_name in self._models):
                    return seg_name
        # 次に芝/ダート×距離帯セグメント
        for seg_name, cond in self.SEGMENTS.items():
            if ("track_type" in cond
                    and track_type == cond["track_type"]
                    and cond["distance_min"] <= distance <= cond["distance_max"]):
                return seg_name
        return None

    def _filter_segment(self, df: pd.DataFrame, cond: dict) -> pd.DataFrame:
        """DataFrameからセグメント条件に合致する行を抽出"""
        mask = (
            (df["distance"] >= cond["distance_min"])
            & (df["distance"] <= cond["distance_max"])
        )
        # track_type条件（芝/ダート別セグメント用）
        if "track_type" in cond:
            mask = mask & (df["track_type"] == cond["track_type"])
        # venue_code条件（会場別セグメント用）
        if "venue_code" in cond:
            mask = mask & (df["venue_code"] == cond["venue_code"])
        return df[mask]

    def train(self, df: pd.DataFrame) -> dict[str, dict[str, float]]:
        """
        各セグメントごとにLightGBM Classifierを学習する。
        GroupKFold（5分割）でデータリーク防止。

        Returns:
            セグメント名 → {"mean_auc": float, "std_auc": float, "n_samples": int}
        """
        results: dict[str, dict[str, float]] = {}

        print("\n  === 条件別特化モデル学習開始 ===")
        print(f"  セグメント数: {len(self.SEGMENTS)}")
        print(f"  最低データ数: {self.MIN_SAMPLES:,}")

        for seg_name, cond in self.SEGMENTS.items():
            seg_df = self._filter_segment(df, cond)
            n_samples = len(seg_df)

            if n_samples < self.MIN_SAMPLES:
                print(f"\n  [{seg_name}] スキップ（データ数: {n_samples:,} < {self.MIN_SAMPLES:,}）")
                continue

            print(f"\n  [{seg_name}] 学習開始（データ数: {n_samples:,}、"
                  f"勝率: {seg_df[TARGET_COL].mean():.3f}）")

            # GroupKFold CV
            X = seg_df[self._feature_cols].copy()
            y = seg_df[TARGET_COL].copy()
            groups = pd.factorize(seg_df["race_key"])[0]

            # グループ数が5未満の場合はsplit数を調整
            n_groups = len(set(groups))
            n_splits = min(5, n_groups)
            if n_splits < 2:
                print(f"    スキップ（グループ数: {n_groups} < 2）")
                continue

            kf = GroupKFold(n_splits=n_splits)
            auc_scores: list[float] = []
            best_model: lgb.Booster | None = None
            best_auc = 0.0

            for fold, (train_idx, val_idx) in enumerate(kf.split(X, y, groups)):
                X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
                y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

                dtrain = lgb.Dataset(
                    X_train, label=y_train, feature_name=self._feature_cols,
                )
                dval = lgb.Dataset(
                    X_val, label=y_val, feature_name=self._feature_cols,
                    reference=dtrain,
                )

                model = lgb.train(
                    LGBM_SPECIALIZED_PARAMS, dtrain,
                    num_boost_round=SPECIALIZED_NUM_BOOST_ROUND,
                    valid_sets=[dval],
                    callbacks=[
                        lgb.early_stopping(SPECIALIZED_EARLY_STOPPING, verbose=False),
                        lgb.log_evaluation(period=-1),
                    ],
                )

                val_pred = model.predict(X_val)
                auc = roc_auc_score(y_val, val_pred)
                auc_scores.append(auc)
                print(f"    Fold {fold + 1}: AUC = {auc:.4f}")

                if auc > best_auc:
                    best_auc = auc
                    best_model = model

            if best_model is not None:
                self._models[seg_name] = best_model
                mean_auc = float(np.mean(auc_scores))
                std_auc = float(np.std(auc_scores))
                self._segment_aucs[seg_name] = mean_auc
                results[seg_name] = {
                    "mean_auc": mean_auc,
                    "std_auc": std_auc,
                    "n_samples": float(n_samples),
                }
                print(f"    CV AUC: {mean_auc:.4f} ± {std_auc:.4f}")

        print(f"\n  === 特化モデル学習完了: {len(self._models)}/{len(self.SEGMENTS)} セグメント ===")
        return results

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray | None:
        """
        該当セグメントの特化モデルで予測する。

        DataFrameの各行について、track_typeとdistanceから該当セグメントを特定し、
        そのセグメントの特化モデルで予測する。
        特化モデルが存在しない行はNaNとする。

        Returns:
            予測確率の配列。全行が対象外の場合はNone。
            NaN値は「特化モデルが該当しない行」を意味する。
        """
        if not self._models:
            return None

        n = len(df)
        preds = np.full(n, np.nan)

        # 各セグメントでまとめて予測（行ごとではなくバッチ処理で高速化）
        for seg_name, model in self._models.items():
            cond = self.SEGMENTS[seg_name]
            # 会場別セグメント vs 芝/ダート×距離帯セグメント
            if "venue_code" in cond:
                seg_mask = (
                    (df["venue_code"] == cond["venue_code"])
                    & (df["distance"] >= cond["distance_min"])
                    & (df["distance"] <= cond["distance_max"])
                )
            else:
                seg_mask = (
                    (df["track_type"] == cond["track_type"])
                    & (df["distance"] >= cond["distance_min"])
                    & (df["distance"] <= cond["distance_max"])
                )
            seg_indices = df.index[seg_mask]

            if len(seg_indices) == 0:
                continue

            X_seg = df.loc[seg_indices, self._feature_cols].copy()
            preds[seg_mask.values] = model.predict(X_seg)

        # 全部NaNなら該当なし
        if np.all(np.isnan(preds)):
            return None

        return preds

    def get_segment_aucs(self) -> dict[str, float]:
        """各セグメントのCV AUCを返す"""
        return self._segment_aucs.copy()

    def save(self, path: Path | str = SPECIALIZED_MODEL_PATH) -> None:
        """全セグメントモデルをまとめてpickleで保存"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "models": self._models,
            "segment_aucs": self._segment_aucs,
            "feature_cols": self._feature_cols,
            "segments": self.SEGMENTS,
        }
        with open(path, "wb") as f:
            pickle.dump(data, f)
        print(f"特化モデルを保存しました: {path}")

    def load(self, path: Path | str = SPECIALIZED_MODEL_PATH) -> None:
        """保存済み特化モデルをロードする"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"特化モデルファイルが見つかりません: {path}")
        with open(path, "rb") as f:
            data = pickle.load(f)
        self._models = data["models"]
        self._segment_aucs = data.get("segment_aucs", {})
        self._feature_cols = data.get("feature_cols", FEATURE_COLS)
        logger.info(f"特化モデルをロード: {list(self._models.keys())}")


class EnsembleModel:
    """
    アンサンブル予測モデル（v2 → v3 Stacking構成）

    4つのサブモデルを統合:
    1. LightGBM Classifier（オッズあり）— 市場情報込みの高精度予測
    2. LightGBM Classifier（オッズなし）— 市場バイアス排除、期待値戦略用
    3. LightGBM Ranker（LambdaRank）— レース内順位予測
    4. CatBoost Classifier（オッズあり）— カテゴリ特徴量に強い

    統合方式: Stacking（メタラーナー: LogisticRegression）
    - OOF予測値（N×4行列）でメタラーナーを学習
    - メタラーナーが存在しない場合は従来の加重平均にフォールバック
    - 最終出力にIsotonic Regressionキャリブレーションを適用
    """

    # 特化モデルの予測をメインモデルとブレンドする際の重み
    # main_pred * (1 - SPECIALIZED_BLEND_WEIGHT) + spec_pred * SPECIALIZED_BLEND_WEIGHT
    SPECIALIZED_BLEND_WEIGHT = 0.3

    def __init__(self) -> None:
        self._lgbm_classifier: lgb.Booster | None = None
        self._lgbm_no_odds: lgb.Booster | None = None
        self._lgbm_ranker: lgb.Booster | None = None
        self._catboost: CatBoostClassifier | None = None
        self._feature_importance: pd.DataFrame | None = None
        # Isotonic Regressionによる確率キャリブレーター（予測確率を実勝率に補正）
        self._calibrator: IsotonicRegression | None = None
        # Stackingメタラーナー（LogisticRegression: OOF予測値→最終予測）
        self._meta_learner: LogisticRegression | None = None
        # 条件別特化モデル（芝/ダート×距離帯、存在する場合のみブレンドに使用）
        self._specialized: SpecializedModel | None = None

        # アンサンブル重み（学習後にCV結果で調整、メタラーナー不在時のフォールバック用）
        self._weights = {
            "lgbm_classifier": 0.35,
            "lgbm_no_odds": 0.20,
            "lgbm_ranker": 0.20,
            "catboost": 0.25,
        }

    @property
    def is_trained(self) -> bool:
        return self._lgbm_classifier is not None

    def train(
        self, df: pd.DataFrame, *,
        use_optuna: bool = False, n_trials: int = 50,
    ) -> dict[str, float]:
        """
        4つのモデルを順番に学習し、Stackingメタラーナーを構築する。
        GroupKFold（5分割）でデータリークを防ぐ。

        【Stacking構成】
        1. 各サブモデルをGroupKFoldで学習（best modelを保存）
        2. 全サブモデルのOOF予測値（N×4行列）を収集
        3. LogisticRegressionメタラーナーをOOF予測行列 vs 実ラベルでフィッティング
        4. Stacking出力に対してIsotonic Regressionキャリブレーションを適用

        Args:
            use_optuna: TrueならOptuna LightGBMTunerCVでハイパーパラメータ自動チューニング
            n_trials: Optunaの試行回数（デフォルト50）
        """
        # Optunaフラグの検証
        if use_optuna and not OPTUNA_AVAILABLE:
            logger.warning("Optunaが未インストールです。固定パラメータで学習します。")
            use_optuna = False
        if use_optuna:
            print("\n  [Optuna] ハイパーパラメータ自動チューニング有効（試行数: %d）" % n_trials)
        groups = pd.factorize(df["race_key"])[0]
        kf = GroupKFold(n_splits=5)
        n_samples = len(df)

        # --- 時間重み付け: 直近データを重視する sample_weight を計算 ---
        sample_weights = self._compute_time_weights(df)
        print(f"\n  時間重み: 直近3年(2.0)={int((sample_weights == 2.0).sum()):,}件, "
              f"3-5年(1.0)={int((sample_weights == 1.0).sum()):,}件, "
              f"5年超(0.5)={int((sample_weights == 0.5).sum()):,}件")

        # OOF予測値を格納する配列（各モデルのOOF予測を列として格納）
        oof_lgbm = np.zeros(n_samples)
        oof_no_odds = np.zeros(n_samples)
        oof_ranker = np.zeros(n_samples)
        oof_catboost = np.zeros(n_samples)

        # --- 1. LightGBM Classifier（オッズあり）+ OOF予測収集 ---
        print("\n  --- LightGBM Classifier（オッズあり）---")
        self._lgbm_classifier, lgbm_aucs, oof_lgbm = self._train_lgbm_classifier_with_oof(
            df, FEATURE_COLS, kf, groups,
            sample_weights=sample_weights,
            use_optuna=use_optuna, n_trials=n_trials,
        )
        lgbm_mean_auc = float(np.mean(lgbm_aucs))
        print(f"  CV AUC: {lgbm_mean_auc:.4f} ± {np.std(lgbm_aucs):.4f}")

        # --- 2. LightGBM Classifier（オッズなし）+ OOF予測収集 ---
        print("\n  --- LightGBM Classifier（オッズなし）---")
        self._lgbm_no_odds, no_odds_aucs, oof_no_odds = self._train_lgbm_classifier_with_oof(
            df, FEATURE_COLS_NO_ODDS, kf, groups,
            sample_weights=sample_weights,
            use_optuna=use_optuna, n_trials=n_trials,
        )
        no_odds_mean_auc = float(np.mean(no_odds_aucs))
        print(f"  CV AUC: {no_odds_mean_auc:.4f} ± {np.std(no_odds_aucs):.4f}")

        # --- 3. LightGBM Ranker（LambdaRank）+ OOF予測収集 ---
        print("\n  --- LightGBM Ranker（LambdaRank）---")
        self._lgbm_ranker, oof_ranker = self._train_lgbm_ranker_with_oof(
            df, kf, groups,
            sample_weights=sample_weights,
            use_optuna=use_optuna, n_trials=n_trials,
        )

        # --- 4. CatBoost Classifier + OOF予測収集 ---
        print("\n  --- CatBoost Classifier ---")
        self._catboost, cat_aucs, oof_catboost = self._train_catboost_with_oof(
            df, kf, groups,
            sample_weights=sample_weights,
            use_optuna=use_optuna, n_trials=n_trials,
        )
        if cat_aucs:
            cat_mean_auc = float(np.mean(cat_aucs))
            print(f"  CV AUC: {cat_mean_auc:.4f} ± {np.std(cat_aucs):.4f}")
        else:
            cat_mean_auc = 0.0
            print("  スキップ（CatBoost未インストール）")

        # 特徴量重要度（LightGBM Classifierのもの）
        if self._lgbm_classifier is not None:
            self._feature_importance = pd.DataFrame({
                "feature": FEATURE_COLS,
                "importance": self._lgbm_classifier.feature_importance(importance_type="gain"),
            }).sort_values("importance", ascending=False)

        # アンサンブル重みをAUCベースで動的調整（フォールバック用）
        total = lgbm_mean_auc + no_odds_mean_auc + cat_mean_auc
        if total > 0:
            self._weights["lgbm_classifier"] = lgbm_mean_auc / total * 0.8
            self._weights["lgbm_no_odds"] = no_odds_mean_auc / total * 0.8
            self._weights["catboost"] = cat_mean_auc / total * 0.8
            self._weights["lgbm_ranker"] = 0.20  # Rankerは固定重み
            # 正規化
            w_sum = sum(self._weights.values())
            self._weights = {k: v / w_sum for k, v in self._weights.items()}

        print(f"\n  アンサンブル重み（フォールバック用）: {self._weights}")

        # --- 5. Stackingメタラーナーの学習 ---
        # OOF予測値をN×4の行列にスタックし、LogisticRegressionでフィッティング
        print("\n  --- Stackingメタラーナー（LogisticRegression）---")
        self._meta_learner = self._train_meta_learner(
            df, oof_lgbm, oof_no_odds, oof_ranker, oof_catboost
        )
        if self._meta_learner is not None:
            print(f"    メタラーナー係数: {dict(zip(['lgbm', 'no_odds', 'ranker', 'catboost'], self._meta_learner.coef_[0]))}")
            print("  メタラーナー学習完了")
        else:
            print("  メタラーナー学習スキップ → 加重平均にフォールバック")

        # --- 6. Isotonic Regressionによる確率キャリブレーション ---
        # Stacking出力（またはフォールバック加重平均）のOOF予測に対して学習
        print("\n  --- 確率キャリブレーション（Isotonic Regression）---")
        self._calibrator = self._train_calibrator(
            df, kf, groups, oof_lgbm, oof_no_odds, oof_ranker, oof_catboost
        )
        if self._calibrator is not None:
            print("  キャリブレーター学習完了")
        else:
            print("  キャリブレーター学習スキップ（OOF予測値の収集に失敗）")

        return {
            "mean_auc": lgbm_mean_auc,
            "std_auc": float(np.std(lgbm_aucs)),
            "no_odds_auc": no_odds_mean_auc,
            "catboost_auc": cat_mean_auc,
        }

    def _train_lgbm_classifier_with_oof(
        self, df: pd.DataFrame, feature_cols: list[str],
        kf: GroupKFold, groups: np.ndarray, *,
        sample_weights: np.ndarray | None = None,
        use_optuna: bool = False, n_trials: int = 50,
    ) -> tuple[lgb.Booster | None, list[float], np.ndarray]:
        """
        LightGBM Classifierの学習 + OOF予測値の収集。
        各FoldのバリデーションデータへのOOF予測値を返す（Stacking用）。
        sample_weights: 時間重み付けの配列（直近データを重視）
        use_optuna=True の場合、LightGBMTunerCVでハイパーパラメータを自動チューニングしてから学習する。
        """
        X = df[feature_cols].copy()
        y = df[TARGET_COL].copy()
        n_samples = len(df)
        auc_scores: list[float] = []
        best_model: lgb.Booster | None = None
        best_auc = 0.0
        oof_preds = np.zeros(n_samples)

        # Optunaでハイパーパラメータをチューニング（有効時のみ）
        params = LGBM_PARAMS.copy()
        if use_optuna:
            params = self._tune_lgbm_params_with_optuna(
                X, y, groups, feature_cols, params, n_trials=n_trials,
                objective="binary",
            )

        for fold, (train_idx, val_idx) in enumerate(kf.split(X, y, groups)):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

            # 時間重み付け（sample_weightsが指定されている場合）
            w_train = sample_weights[train_idx] if sample_weights is not None else None
            dtrain = lgb.Dataset(X_train, label=y_train, weight=w_train, feature_name=feature_cols)
            dval = lgb.Dataset(X_val, label=y_val, feature_name=feature_cols, reference=dtrain)

            model = lgb.train(
                params, dtrain,
                num_boost_round=NUM_BOOST_ROUND,
                valid_sets=[dval],
                callbacks=[
                    lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False),
                    lgb.log_evaluation(period=-1),
                ],
            )

            val_pred = model.predict(X_val)
            # OOF予測値を格納（各Foldのバリデーション分）
            oof_preds[val_idx] = val_pred
            auc = roc_auc_score(y_val, val_pred)
            auc_scores.append(auc)
            print(f"    Fold {fold + 1}: AUC = {auc:.4f}")

            if auc > best_auc:
                best_auc = auc
                best_model = model

        return best_model, auc_scores, oof_preds

    def _train_lgbm_ranker_with_oof(
        self, df: pd.DataFrame, kf: GroupKFold, groups: np.ndarray, *,
        sample_weights: np.ndarray | None = None,
        use_optuna: bool = False, n_trials: int = 50,
    ) -> tuple[lgb.Booster | None, np.ndarray]:
        """
        LightGBM Ranker（LambdaRank）の学習 + OOF予測値の収集。
        Rankerの生スコアをレース内softmax正規化して0-1に変換する。
        sample_weights: 時間重み付けの配列（直近データを重視）
        use_optuna=True の場合、Optunaで主要パラメータをチューニングしてから学習する。
        """
        X = df[FEATURE_COLS].copy()
        y = df[RANK_TARGET_COL].copy()
        # ランキングラベルを0-18にクリップ（大頭数レースでラベル>18が発生しCVでエラーになるため）
        # int変換も必須（float状態だとLightGBMが内部で丸め処理を行いラベル範囲外エラーになる場合がある）
        y = y.clip(upper=18).astype(int)
        n_samples = len(df)
        oof_preds = np.zeros(n_samples)

        # レースごとの出走頭数（groupパラメータ用）
        race_keys_ordered = df["race_key"].values

        # Optunaでハイパーパラメータをチューニング（有効時のみ）
        params = LGBM_RANKER_PARAMS.copy()
        if use_optuna:
            params = self._tune_lgbm_ranker_params_with_optuna(
                df, X, y, groups, race_keys_ordered, kf, params, n_trials=n_trials,
            )

        best_model: lgb.Booster | None = None
        best_ndcg = 0.0

        for fold, (train_idx, val_idx) in enumerate(kf.split(X, y, groups)):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

            # group = 各レースの出走頭数のリスト
            train_groups = _compute_group_sizes(race_keys_ordered[train_idx])
            val_groups = _compute_group_sizes(race_keys_ordered[val_idx])

            # 時間重み付け（sample_weightsが指定されている場合）
            w_train = sample_weights[train_idx] if sample_weights is not None else None
            dtrain = lgb.Dataset(X_train, label=y_train, weight=w_train, group=train_groups, feature_name=FEATURE_COLS)
            dval = lgb.Dataset(X_val, label=y_val, group=val_groups, feature_name=FEATURE_COLS, reference=dtrain)

            model = lgb.train(
                params, dtrain,
                num_boost_round=NUM_BOOST_ROUND,
                valid_sets=[dval],
                callbacks=[
                    lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False),
                    lgb.log_evaluation(period=-1),
                ],
            )

            # OOF予測値を格納（Rankerのスコアをsoftmax正規化）
            ranker_scores = model.predict(X_val)
            oof_preds[val_idx] = _softmax_normalize(ranker_scores)

            # NDCGは内部で計算されるため、best_iterationで判断
            ndcg_score = model.best_score.get("valid_0", {}).get("ndcg@5", 0.0)
            print(f"    Fold {fold + 1}: NDCG@5 = {ndcg_score:.4f}")

            if ndcg_score > best_ndcg:
                best_ndcg = ndcg_score
                best_model = model

        return best_model, oof_preds

    def _train_catboost_with_oof(
        self, df: pd.DataFrame, kf: GroupKFold, groups: np.ndarray, *,
        sample_weights: np.ndarray | None = None,
        use_optuna: bool = False, n_trials: int = 50,
    ) -> tuple[CatBoostClassifier | None, list[float], np.ndarray]:
        """
        CatBoost Classifierの学習 + OOF予測値の収集（未インストール時はスキップ）。
        sample_weights: 時間重み付けの配列（直近データを重視）
        use_optuna=True の場合、CatBoostPruningCallbackで不要な試行を早期打ち切りする。
        """
        n_samples = len(df)
        oof_preds = np.zeros(n_samples)

        if CatBoostClassifier is None:
            logger.warning("CatBoost未インストール。CatBoostモデルをスキップします。")
            return None, [], oof_preds

        X = df[FEATURE_COLS].copy()
        y = df[TARGET_COL].copy()

        # Optunaでハイパーパラメータをチューニング（有効時のみ）
        cat_params = CATBOOST_PARAMS.copy()
        if use_optuna:
            cat_params = self._tune_catboost_params_with_optuna(
                X, y, groups, kf, cat_params, n_trials=n_trials,
            )

        auc_scores: list[float] = []
        best_model: CatBoostClassifier | None = None
        best_auc = 0.0

        for fold, (train_idx, val_idx) in enumerate(kf.split(X, y, groups)):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

            model = CatBoostClassifier(**cat_params)
            # 時間重み付け（sample_weightsが指定されている場合）
            w_train = sample_weights[train_idx] if sample_weights is not None else None
            model.fit(
                X_train, y_train,
                sample_weight=w_train,
                eval_set=(X_val, y_val),
                early_stopping_rounds=EARLY_STOPPING_ROUNDS,
            )

            val_pred = model.predict_proba(X_val)[:, 1]
            # OOF予測値を格納
            oof_preds[val_idx] = val_pred
            auc = roc_auc_score(y_val, val_pred)
            auc_scores.append(auc)
            print(f"    Fold {fold + 1}: AUC = {auc:.4f}")

            if auc > best_auc:
                best_auc = auc
                best_model = model

        return best_model, auc_scores, oof_preds

    # --- Optunaハイパーパラメータチューニング用メソッド ---

    def _tune_lgbm_params_with_optuna(
        self, X: pd.DataFrame, y: pd.Series, groups: np.ndarray,
        feature_cols: list[str], base_params: dict[str, Any], *,
        n_trials: int = 50, objective: str = "binary",
    ) -> dict[str, Any]:
        """
        Optuna LightGBMTunerCVを使ってLightGBM Classifierのハイパーパラメータを自動チューニング。
        LightGBMTunerCVはnum_leaves, feature_fraction, bagging_fraction, lambda_l1, lambda_l2等を
        ステップワイズにチューニングする。
        """
        print("    [Optuna] LightGBM Classifier チューニング開始...")

        # TunerCV用のパラメータ（verboseをオフにする）
        tuner_params = base_params.copy()
        tuner_params["verbose"] = -1

        # 全データでDatasetを作成
        dtrain = lgb.Dataset(X, label=y, feature_name=feature_cols)

        # GroupKFoldの分割インデックスを生成（TunerCVのfolds引数用）
        kf = GroupKFold(n_splits=5)
        folds = list(kf.split(X, y, groups))

        # Optunaのログレベルを抑制（TunerCVの内部ログが冗長になるため）
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        tuner = LightGBMTunerCV(
            tuner_params,
            dtrain,
            folds=folds,
            num_boost_round=NUM_BOOST_ROUND,
            callbacks=[
                lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False),
                lgb.log_evaluation(period=-1),
            ],
            optuna_seed=42,
            show_progress_bar=False,
        )

        # チューニング実行
        tuner.run()

        # ベストパラメータを取得
        best_params = tuner.best_params
        best_score = tuner.best_score
        print(f"    [Optuna] ベストスコア（AUC）: {best_score:.4f}")
        print(f"    [Optuna] ベストパラメータ: {best_params}")

        # ベストパラメータをベースパラメータにマージ
        merged = base_params.copy()
        merged.update(best_params)
        return merged

    def _tune_lgbm_ranker_params_with_optuna(
        self, df: pd.DataFrame, X: pd.DataFrame, y: pd.Series,
        groups: np.ndarray, race_keys_ordered: np.ndarray,
        kf: GroupKFold, base_params: dict[str, Any], *,
        n_trials: int = 50,
    ) -> dict[str, Any]:
        """
        OptunaでLightGBM Rankerのハイパーパラメータをチューニングする。
        LightGBMTunerCVはRankerに対応していないため、通常のOptuna Studyで探索する。
        PruningCallbackで不要な試行を早期打ち切りする。
        """
        print("    [Optuna] LightGBM Ranker チューニング開始...")
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        def objective(trial: optuna.Trial) -> float:
            """Optunaの目的関数: NDCG@5を最大化する"""
            params = base_params.copy()
            params["num_leaves"] = trial.suggest_int("num_leaves", 15, 127)
            params["learning_rate"] = trial.suggest_float("learning_rate", 0.01, 0.3, log=True)
            params["feature_fraction"] = trial.suggest_float("feature_fraction", 0.4, 1.0)
            params["bagging_fraction"] = trial.suggest_float("bagging_fraction", 0.4, 1.0)
            params["min_child_samples"] = trial.suggest_int("min_child_samples", 5, 100)
            params["lambda_l1"] = trial.suggest_float("lambda_l1", 1e-8, 10.0, log=True)
            params["lambda_l2"] = trial.suggest_float("lambda_l2", 1e-8, 10.0, log=True)
            params["verbose"] = -1

            # 1つ目のFoldだけで評価（高速化のため）
            ndcg_scores = []
            for fold, (train_idx, val_idx) in enumerate(kf.split(X, y, groups)):
                X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
                y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

                train_groups = _compute_group_sizes(race_keys_ordered[train_idx])
                val_groups = _compute_group_sizes(race_keys_ordered[val_idx])

                dtrain = lgb.Dataset(X_train, label=y_train, group=train_groups, feature_name=FEATURE_COLS)
                dval = lgb.Dataset(X_val, label=y_val, group=val_groups, feature_name=FEATURE_COLS, reference=dtrain)

                # PruningCallbackで不要な試行を早期打ち切り
                pruning_callback = LightGBMPruningCallback(trial, "ndcg@5")

                model = lgb.train(
                    params, dtrain,
                    num_boost_round=NUM_BOOST_ROUND,
                    valid_sets=[dval],
                    callbacks=[
                        lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False),
                        lgb.log_evaluation(period=-1),
                        pruning_callback,
                    ],
                )

                ndcg = model.best_score.get("valid_0", {}).get("ndcg@5", 0.0)
                ndcg_scores.append(ndcg)

                # 最初の2Foldだけで判断（高速化）
                if fold >= 1:
                    break

            return float(np.mean(ndcg_scores))

        study = optuna.create_study(
            direction="maximize",
            pruner=optuna.pruners.MedianPruner(n_startup_trials=5),
        )
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

        best_params = study.best_params
        best_score = study.best_value
        print(f"    [Optuna] ベストスコア（NDCG@5）: {best_score:.4f}")
        print(f"    [Optuna] ベストパラメータ: {best_params}")

        # ベストパラメータをベースにマージ
        merged = base_params.copy()
        merged.update(best_params)
        return merged

    def _tune_catboost_params_with_optuna(
        self, X: pd.DataFrame, y: pd.Series,
        groups: np.ndarray, kf: GroupKFold,
        base_params: dict[str, Any], *,
        n_trials: int = 50,
    ) -> dict[str, Any]:
        """
        OptunaでCatBoostのハイパーパラメータをチューニングする。
        CatBoostPruningCallback（利用可能な場合）で不要な試行を早期打ち切り。
        """
        print("    [Optuna] CatBoost チューニング開始...")
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        def objective(trial: optuna.Trial) -> float:
            """Optunaの目的関数: AUCを最大化する"""
            params = {
                "iterations": base_params.get("iterations", 500),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "depth": trial.suggest_int("depth", 4, 10),
                "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1e-3, 10.0, log=True),
                "random_seed": 42,
                "verbose": 0,
                "eval_metric": "AUC",
                "auto_class_weights": "Balanced",
                "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            }

            # 最初の2Foldだけで評価（高速化）
            auc_scores = []
            for fold, (train_idx, val_idx) in enumerate(kf.split(X, y, groups)):
                X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
                y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

                model = CatBoostClassifier(**params)

                # CatBoostPruningCallbackが利用可能な場合は適用
                callbacks_list = []
                if CatBoostPruningCallback is not None:
                    callbacks_list.append(CatBoostPruningCallback(trial, "AUC"))

                model.fit(
                    X_train, y_train,
                    eval_set=(X_val, y_val),
                    early_stopping_rounds=EARLY_STOPPING_ROUNDS,
                    callbacks=callbacks_list if callbacks_list else None,
                )

                val_pred = model.predict_proba(X_val)[:, 1]
                auc = roc_auc_score(y_val, val_pred)
                auc_scores.append(auc)

                # 最初の2Foldだけで判断（高速化）
                if fold >= 1:
                    break

            return float(np.mean(auc_scores))

        study = optuna.create_study(
            direction="maximize",
            pruner=optuna.pruners.MedianPruner(n_startup_trials=5),
        )
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

        best_params = study.best_params
        best_score = study.best_value
        print(f"    [Optuna] ベストスコア（AUC）: {best_score:.4f}")
        print(f"    [Optuna] ベストパラメータ: {best_params}")

        # ベストパラメータをベースにマージ
        merged = base_params.copy()
        merged.update(best_params)
        return merged

    def _train_meta_learner(
        self, df: pd.DataFrame,
        oof_lgbm: np.ndarray, oof_no_odds: np.ndarray,
        oof_ranker: np.ndarray, oof_catboost: np.ndarray,
    ) -> LogisticRegression | None:
        """
        Stackingメタラーナーを学習する。

        4モデルのOOF予測値（N×4の行列）を特徴量とし、
        LogisticRegression(C=1.0)で実ラベルに対してフィッティングする。
        これにより、各モデルの予測を最適な重みで統合できる。
        """
        try:
            y = df[TARGET_COL].values

            # N×4のOOF予測行列を構築
            oof_matrix = np.column_stack([oof_lgbm, oof_no_odds, oof_ranker, oof_catboost])

            # OOF予測値がすべてゼロの列がないかチェック（未学習モデルの検出）
            col_sums = np.abs(oof_matrix).sum(axis=0)
            if np.any(col_sums == 0):
                logger.warning("一部のモデルのOOF予測値がすべてゼロ。メタラーナー学習をスキップします。")
                return None

            # LogisticRegressionでメタラーナーを学習
            meta_learner = LogisticRegression(C=1.0, max_iter=1000, random_state=42)
            meta_learner.fit(oof_matrix, y)

            # メタラーナーのOOF AUCを表示
            meta_pred = meta_learner.predict_proba(oof_matrix)[:, 1]
            meta_auc = roc_auc_score(y, meta_pred)
            print(f"    Stacking OOF AUC: {meta_auc:.4f}")

            return meta_learner
        except Exception as e:
            logger.warning(f"メタラーナー学習中にエラー: {e}")
            return None

    def _train_calibrator(
        self, df: pd.DataFrame, kf: GroupKFold, groups: np.ndarray,
        oof_lgbm: np.ndarray, oof_no_odds: np.ndarray,
        oof_ranker: np.ndarray, oof_catboost: np.ndarray,
    ) -> IsotonicRegression | None:
        """
        Stacking出力のOOF予測値に対してIsotonic Regressionキャリブレーターを学習する。

        メタラーナーが存在する場合: OOF予測行列→メタラーナー→Stacking出力をキャリブレーション
        メタラーナーが存在しない場合: 加重平均のOOF予測をキャリブレーション（フォールバック）
        """
        try:
            y = df[TARGET_COL].values

            if self._meta_learner is not None:
                # Stacking出力のOOF予測値を使用
                oof_matrix = np.column_stack([oof_lgbm, oof_no_odds, oof_ranker, oof_catboost])
                oof_preds = self._meta_learner.predict_proba(oof_matrix)[:, 1]
            else:
                # フォールバック: 加重平均のOOF予測値を使用
                oof_preds = (
                    oof_lgbm * self._weights["lgbm_classifier"]
                    + oof_no_odds * self._weights["lgbm_no_odds"]
                    + oof_ranker * self._weights["lgbm_ranker"]
                    + oof_catboost * self._weights["catboost"]
                )

            # Isotonic Regressionで予測確率→実勝率の補正関数を学習
            calibrator = IsotonicRegression(
                y_min=0.0, y_max=1.0, out_of_bounds="clip"
            )
            calibrator.fit(oof_preds, y)

            # キャリブレーション前後のAUCを比較表示
            calibrated = calibrator.predict(oof_preds)
            auc_before = roc_auc_score(y, oof_preds)
            auc_after = roc_auc_score(y, calibrated)
            print(f"    OOF AUC（補正前）: {auc_before:.4f}")
            print(f"    OOF AUC（補正後）: {auc_after:.4f}")

            return calibrator
        except Exception as e:
            logger.warning(f"キャリブレーター学習中にエラー: {e}")
            return None

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        """
        アンサンブル予測（Stacking → Calibration）。

        メタラーナーが存在する場合: 4モデル予測→メタラーナー→キャリブレーション
        メタラーナーが存在しない場合: 加重平均→キャリブレーション（フォールバック）
        """
        if self._lgbm_classifier is None:
            raise RuntimeError("モデルが学習されていません。")

        # モデルが学習した特徴量を使用（コードとモデルの不一致に対応）
        model_features = self._lgbm_classifier.feature_name()
        for col in model_features:
            if col not in df.columns:
                df[col] = 0.0  # 不足カラムはデフォルト値
        X_full = df[model_features].copy()

        no_odds_features = [c for c in model_features if c not in ("odds_win", "popularity", "odds_place_avg", "odds_place_range", "odds_win_place_ratio")]
        X_no_odds = df[no_odds_features].copy() if self._lgbm_no_odds is not None else X_full.copy()

        # 各モデルの個別予測を収集
        pred_lgbm = self._lgbm_classifier.predict(X_full)

        if self._lgbm_no_odds is not None:
            pred_no_odds = self._lgbm_no_odds.predict(X_no_odds)
        else:
            pred_no_odds = pred_lgbm.copy()

        if self._lgbm_ranker is not None:
            ranker_scores = self._lgbm_ranker.predict(X_full)
            pred_ranker = _softmax_normalize(ranker_scores)
        else:
            pred_ranker = pred_lgbm.copy()

        if self._catboost is not None:
            pred_cat = self._catboost.predict_proba(X_full)[:, 1]
        else:
            pred_cat = pred_lgbm.copy()

        # Stacking統合: メタラーナーが存在する場合はStackingで統合
        if self._meta_learner is not None:
            # 4モデルの予測を行列にスタック → メタラーナーで最終予測
            pred_matrix = np.column_stack([pred_lgbm, pred_no_odds, pred_ranker, pred_cat])
            preds = self._meta_learner.predict_proba(pred_matrix)[:, 1]
        else:
            # フォールバック: 従来の加重平均方式
            preds = (
                pred_lgbm * self._weights["lgbm_classifier"]
                + pred_no_odds * self._weights["lgbm_no_odds"]
                + pred_ranker * self._weights["lgbm_ranker"]
                + pred_cat * self._weights["catboost"]
            )

        # Isotonic Regressionによる確率キャリブレーション補正
        if self._calibrator is not None:
            try:
                preds = self._calibrator.predict(preds)
            except Exception as e:
                logger.warning(f"キャリブレーション補正に失敗、補正なしで返します: {e}")

        # 条件別特化モデルとのブレンド（存在する場合のみ）
        if self._specialized is not None and self._specialized.is_trained:
            spec_preds = self._specialized.predict_proba(df)
            if spec_preds is not None:
                # NaNでない行（特化モデルが該当する行）のみブレンド
                valid_mask = ~np.isnan(spec_preds)
                if np.any(valid_mask):
                    w = self.SPECIALIZED_BLEND_WEIGHT
                    preds[valid_mask] = (
                        (1.0 - w) * preds[valid_mask]
                        + w * spec_preds[valid_mask]
                    )

        return preds

    def predict_proba_no_odds(self, df: pd.DataFrame) -> np.ndarray:
        """オッズなしモデルのみで予測（期待値戦略の核）"""
        if self._lgbm_no_odds is None:
            raise RuntimeError("オッズなしモデルが学習されていません。")
        X_no_odds = df[FEATURE_COLS_NO_ODDS].copy()
        return self._lgbm_no_odds.predict(X_no_odds)

    def predict_with_ev(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        アンサンブル予測 + 期待値を計算して返す。
        オッズなしモデルの期待値も併記。
        """
        proba_ensemble = self.predict_proba(df)

        # 全馬の予測が極端に小さい場合（未勝利戦等）、レース内で正規化して相対確率にする
        if proba_ensemble.max() < 0.01 and len(proba_ensemble) > 1:
            # softmaxで正規化（合計=1にならないが相対的な差を出す）
            total = proba_ensemble.sum()
            if total > 0:
                proba_ensemble = proba_ensemble / total
            else:
                # 完全に0の場合は均等確率
                proba_ensemble = np.full(len(proba_ensemble), 1.0 / len(proba_ensemble))

        result = df[["entry_id", "horse_num", "horse_name", "jockey_name", "odds_win_raw"]].copy()
        result["win_prob"] = proba_ensemble
        odds = df["odds_win_raw"]
        has_odds = odds.notna() & (odds > 0)

        # 生のEV計算
        raw_ev = np.where(has_odds, proba_ensemble * odds.fillna(1) - 1.0, np.nan)

        # ロングショットバイアス補正（高オッズ馬のEVを緩やかに割り引く）
        odds_vals = odds.fillna(10)
        longshot_discount = np.where(odds_vals > 200, 0.3,
                            np.where(odds_vals > 100, 0.5,
                            np.where(odds_vals > 50, 0.7,
                            np.where(odds_vals > 30, 0.85,
                            np.where(odds_vals > 15, 0.95, 1.0)))))
        result["expected_value"] = np.where(has_odds, raw_ev * longshot_discount, np.nan)

        # オッズなしモデルの期待値（市場の過小評価を発見）
        if self._lgbm_no_odds is not None:
            proba_no_odds = self.predict_proba_no_odds(df)
            result["win_prob_no_odds"] = proba_no_odds
            raw_ev_no_odds = np.where(has_odds, proba_no_odds * odds.fillna(1) - 1.0, np.nan)

            # ロングショットバイアス補正:
            # noOddsモデルの精度が低い（AUC~0.65）ため、高オッズ馬に過剰なEVを与えてしまう
            # 対策1: オッズに応じた割引率（高オッズほどEVを割り引く）
            odds_discount = np.where(odds > 200, 0.1,
                            np.where(odds > 100, 0.2,
                            np.where(odds > 50, 0.4,
                            np.where(odds > 30, 0.6,
                            np.where(odds > 15, 0.8, 1.0)))))
            # 対策2: noOdds勝率とアンサンブル勝率の乖離が大きい場合ペナルティ
            prob_ratio = np.where(proba_ensemble > 0.01, proba_no_odds / proba_ensemble, 1.0)
            divergence_penalty = np.where(prob_ratio > 3.0, 0.3,
                                 np.where(prob_ratio > 2.0, 0.5, 1.0))
            # 補正後のEV
            result["ev_no_odds"] = raw_ev_no_odds * odds_discount * divergence_penalty
        else:
            result["win_prob_no_odds"] = proba_ensemble
            result["ev_no_odds"] = result["expected_value"]

        # EV上限キャップ（非現実的な値を抑制）
        result["expected_value"] = result["expected_value"].clip(upper=5.0)
        result["ev_no_odds"] = result["ev_no_odds"].clip(upper=5.0)

        # 推奨ラベル（アンサンブルEV + オッズなしEVの両方を考慮）
        result["recommendation"] = result.apply(
            lambda r: _ev_label_ensemble(r["expected_value"], r["ev_no_odds"]),
            axis=1,
        )

        return result.sort_values("win_prob", ascending=False).reset_index(drop=True)

    @staticmethod
    def _compute_time_weights(df: pd.DataFrame) -> np.ndarray:
        """
        学習データの日付から時間重みを計算する。
        直近3年=2.0, 3-5年=1.0, 5年以上=0.5
        最新のレースデータを基準にして経過日数を算出。
        """
        race_dates = pd.to_datetime(df["race_date"])
        latest = race_dates.max()
        days_ago = (latest - race_dates).dt.days
        # 直近3年(1095日)=2.0, 3-5年(1825日)=1.0, それ以前=0.5
        weights = np.where(
            days_ago <= 1095, 2.0,
            np.where(days_ago <= 1825, 1.0, 0.5)
        )
        return weights

    def get_feature_importance(self) -> pd.DataFrame | None:
        return self._feature_importance

    def save(self, path: Path | str = ENSEMBLE_MODEL_PATH) -> None:
        """全サブモデルをまとめてpickleで保存する"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "lgbm_classifier": self._lgbm_classifier,
            "lgbm_no_odds": self._lgbm_no_odds,
            "lgbm_ranker": self._lgbm_ranker,
            "catboost": self._catboost,
            "weights": self._weights,
            "feature_importance": self._feature_importance,
            "calibrator": self._calibrator,  # 確率キャリブレーター
            "meta_learner": self._meta_learner,  # Stackingメタラーナー
            "has_specialized": self._specialized is not None and self._specialized.is_trained,
        }
        with open(path, "wb") as f:
            pickle.dump(data, f)
        print(f"アンサンブルモデルを保存しました: {path}")

        # 特化モデルは別ファイルに保存（サイズ分離 + 独立更新可能にするため）
        if self._specialized is not None and self._specialized.is_trained:
            self._specialized.save(SPECIALIZED_MODEL_PATH)

    def load(self, path: Path | str = ENSEMBLE_MODEL_PATH) -> None:
        """保存済みアンサンブルモデルをロードする"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"モデルファイルが見つかりません: {path}")
        with open(path, "rb") as f:
            data = pickle.load(f)
        self._lgbm_classifier = data["lgbm_classifier"]
        self._lgbm_no_odds = data["lgbm_no_odds"]
        self._lgbm_ranker = data["lgbm_ranker"]
        self._catboost = data["catboost"]
        self._weights = data["weights"]
        self._feature_importance = data.get("feature_importance")
        # キャリブレーターは後から追加されたため、存在しない場合はNone（後方互換）
        self._calibrator = data.get("calibrator")
        # メタラーナーはStacking構成で追加、存在しない場合は加重平均にフォールバック（後方互換）
        self._meta_learner = data.get("meta_learner")

        # 特化モデルの自動ロード（ファイルが存在する場合のみ）
        has_specialized = data.get("has_specialized", False)
        if has_specialized and SPECIALIZED_MODEL_PATH.exists():
            try:
                self._specialized = SpecializedModel()
                self._specialized.load(SPECIALIZED_MODEL_PATH)
                logger.info(f"特化モデルをロード: {self._specialized.trained_segments}")
            except Exception as e:
                logger.warning(f"特化モデルのロードに失敗（メインモデルのみで予測します）: {e}")
                self._specialized = None
        elif SPECIALIZED_MODEL_PATH.exists():
            # has_specializedフラグがなくても特化モデルファイルが存在すればロード試行（後方互換）
            try:
                self._specialized = SpecializedModel()
                self._specialized.load(SPECIALIZED_MODEL_PATH)
                logger.info(f"特化モデルをロード（自動検出）: {self._specialized.trained_segments}")
            except Exception as e:
                logger.warning(f"特化モデルのロードに失敗: {e}")
                self._specialized = None


# --- ユーティリティ関数 ---

def _ev_label(ev: float) -> str:
    """期待値から推奨ラベルを返す（後方互換）"""
    if ev >= 0.2:
        return "◎ 強推奨"
    elif ev >= 0.0:
        return "○ 推奨"
    elif ev >= -0.1:
        return "△ 検討"
    else:
        return "✕ 非推奨"


def _ev_label_ensemble(ev_ensemble, ev_no_odds) -> str:
    """
    アンサンブルEV + オッズなしEVの両方を考慮した推奨ラベル。
    オッズ未確定（NaN）の場合は勝率ベースで判定。
    """
    import math
    e_nan = (isinstance(ev_ensemble, float) and math.isnan(ev_ensemble))
    n_nan = (isinstance(ev_no_odds, float) and math.isnan(ev_no_odds))

    # オッズ未確定の場合 — 勝率ベースの判定（EVは計算不可）
    if e_nan:
        return "- オッズ未確定"

    if ev_ensemble >= 0.2 and (n_nan or ev_no_odds >= 0.0):
        return "◎ 強推奨"
    elif ev_ensemble >= 0.0 and (n_nan or ev_no_odds >= 0.0):
        return "◎ 推奨（期待値◎）"
    elif ev_ensemble >= 0.2:
        return "○ 推奨"
    elif ev_ensemble >= 0.0:
        return "○ 検討"
    elif ev_ensemble >= -0.1:
        return "△ 様子見"
    else:
        return "✕ 非推奨"


def _softmax_normalize(scores: np.ndarray) -> np.ndarray:
    """Rankerの生スコアを0-1の確率に正規化する"""
    exp_scores = np.exp(scores - np.max(scores))
    return exp_scores / exp_scores.sum()


def _compute_group_sizes(race_keys: np.ndarray) -> list[int]:
    """レースキーの連続をカウントしてgroupサイズリストを作る"""
    groups = []
    if len(race_keys) == 0:
        return groups
    current_key = race_keys[0]
    count = 1
    for key in race_keys[1:]:
        if key == current_key:
            count += 1
        else:
            groups.append(count)
            current_key = key
            count = 1
    groups.append(count)
    return groups


# --- グローバルモデルインスタンス（FastAPIで使い回す）---
_global_model: EnsembleModel | None = None
_global_legacy_model: WinProbabilityModel | None = None


def get_model() -> EnsembleModel | WinProbabilityModel:
    """
    グローバルモデルを返す。
    アンサンブルモデルがあればそちらを優先。なければ旧Classifierモデルにフォールバック。
    """
    global _global_model, _global_legacy_model

    # アンサンブルモデルを優先
    if _global_model is None and ENSEMBLE_MODEL_PATH.exists():
        _global_model = EnsembleModel()
        _global_model.load()
    if _global_model is not None and _global_model.is_trained:
        return _global_model

    # レガシーモデルにフォールバック
    if _global_legacy_model is None:
        _global_legacy_model = WinProbabilityModel()
        if DEFAULT_MODEL_PATH.exists():
            _global_legacy_model.load()
    return _global_legacy_model
