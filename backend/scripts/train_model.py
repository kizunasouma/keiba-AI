"""
AIモデル学習スクリプト（v2: アンサンブル対応）
DBの過去レースデータを使ってLightGBM + CatBoostのアンサンブルモデルを訓練する

使い方:
    cd backend

    # アンサンブルモデル学習（推奨）
    python scripts/train_model.py

    # 従来のLightGBM単体モデル学習
    python scripts/train_model.py --legacy

    # 保存先を指定
    python scripts/train_model.py --output models/ensemble_v2.pkl
"""
import argparse
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.ml.features import build_training_dataset, FEATURE_COLS, FEATURE_COLS_NO_ODDS
from app.ml.model import (
    WinProbabilityModel, EnsembleModel, SpecializedModel,
    DEFAULT_MODEL_PATH, ENSEMBLE_MODEL_PATH, SPECIALIZED_MODEL_PATH,
)


def main():
    parser = argparse.ArgumentParser(description="競馬AIモデルの学習")
    parser.add_argument(
        "--output", type=Path, default=None,
        help="モデルの保存先パス",
    )
    parser.add_argument(
        "--legacy", action="store_true",
        help="従来のLightGBM単体モデルで学習する",
    )
    parser.add_argument(
        "--optuna", action="store_true",
        help="Optunaでハイパーパラメータを自動チューニングする",
    )
    parser.add_argument(
        "--n-trials", type=int, default=50,
        help="Optunaの試行回数（デフォルト: 50）",
    )
    parser.add_argument(
        "--specialized", action="store_true",
        help="条件別特化モデル（芝/ダート×距離帯）も学習する",
    )
    parser.add_argument(
        "--specialized-only", action="store_true",
        help="条件別特化モデルのみ学習する（メインモデルはスキップ）",
    )
    args = parser.parse_args()

    print("=" * 60)
    if args.specialized_only:
        print("競馬AI 条件別特化モデル 学習開始")
        print("  芝/ダート × 距離帯（7セグメント）LightGBM Classifier")
    elif args.legacy:
        print("競馬AI 勝率予測モデル 学習開始（LightGBM単体）")
    else:
        print("競馬AI アンサンブルモデル 学習開始")
        print("  LightGBM Classifier + Ranker + CatBoost + オッズなしモデル")
        if args.specialized:
            print("  + 条件別特化モデル（芝/ダート × 距離帯）")
    if args.optuna:
        print(f"  [Optuna] ハイパーパラメータ自動チューニング有効（試行数: {args.n_trials}）")
    print("=" * 60)

    db = SessionLocal()
    try:
        print("\n[1/3] 学習データ構築中...")
        df = build_training_dataset(db)
        print(f"  取得レコード数: {len(df):,} 件")
        print(f"  レース数: {df['race_key'].nunique():,} レース")
        print(f"  勝率（正解ラベル）: {df['is_win'].mean():.3f}")
        print(f"  特徴量数: {len(FEATURE_COLS)} 項目（オッズなし: {len(FEATURE_COLS_NO_ODDS)} 項目）")

        if len(df) < 100:
            print("\n  学習データが少なすぎます（100件未満）。")
            print("   JV-Linkからデータを取り込んでから再実行してください。")
            print("   python scripts/sync_jvlink.py --mode setup --dataspec RACE")
            return

        if len(df) < 5000:
            print(f"\n  注意: データが少なめ（{len(df):,}件）。精度が低い可能性があります。")
            print("  推奨: 10,000件以上のデータで学習することをお勧めします。")

        # 特徴量の欠損状況を表示
        _print_feature_stats(df)

        if args.specialized_only:
            # 特化モデルのみ学習
            _train_specialized(df, args.output or SPECIALIZED_MODEL_PATH)
        elif args.legacy:
            _train_legacy(df, args.output or DEFAULT_MODEL_PATH)
        else:
            _train_ensemble(
                df, args.output or ENSEMBLE_MODEL_PATH,
                use_optuna=args.optuna, n_trials=args.n_trials,
                train_specialized=args.specialized,
            )

        print("\n学習完了")

    finally:
        db.close()


def _train_legacy(df, output_path: Path):
    """従来のLightGBM単体モデルで学習"""
    print("\n[2/3] モデル学習中（LightGBM Classifier, GroupKFold CV）...")
    model = WinProbabilityModel()
    metrics = model.train(df)
    print(f"\n  最終評価: AUC = {metrics['mean_auc']:.4f} ± {metrics['std_auc']:.4f}")

    print("\n[3/3] モデル保存中...")
    model.save(output_path)

    _print_feature_importance(model)


def _train_ensemble(
    df, output_path: Path, *,
    use_optuna: bool = False, n_trials: int = 50,
    train_specialized: bool = False,
):
    """アンサンブルモデルで学習（Optunaオプション対応 + 条件別特化モデル）"""
    print("\n[2/3] アンサンブルモデル学習中（GroupKFold CV）...")
    model = EnsembleModel()
    metrics = model.train(df, use_optuna=use_optuna, n_trials=n_trials)

    print("\n  --- 最終評価 ---")
    print(f"  LightGBM Classifier AUC: {metrics['mean_auc']:.4f} ± {metrics['std_auc']:.4f}")
    print(f"  LightGBM No-Odds   AUC: {metrics['no_odds_auc']:.4f}")
    print(f"  CatBoost            AUC: {metrics['catboost_auc']:.4f}")

    # 条件別特化モデルの学習（--specialized フラグ指定時）
    if train_specialized:
        print("\n[2.5/3] 条件別特化モデル学習中...")
        specialized = SpecializedModel()
        spec_results = specialized.train(df)

        if specialized.is_trained:
            # EnsembleModelに特化モデルをアタッチ
            model._specialized = specialized

            print("\n  --- 特化モデル評価 ---")
            for seg_name, seg_metrics in spec_results.items():
                print(f"    {seg_name}: AUC = {seg_metrics['mean_auc']:.4f} "
                      f"± {seg_metrics['std_auc']:.4f} "
                      f"({int(seg_metrics['n_samples']):,}件)")
        else:
            print("  特化モデルの学習をスキップ（十分なデータがあるセグメントなし）")

    print("\n[3/3] モデル保存中...")
    model.save(output_path)

    _print_feature_importance(model)

    # 期待値戦略の案内
    print("\n  --- 期待値戦略について ---")
    print("  オッズなしモデルの期待値（ev_no_odds）とアンサンブル期待値の両方が")
    print("  プラスの馬は「市場が過小評価 + モデル高評価」で特に有望です。")
    if train_specialized and model._specialized is not None:
        print(f"\n  条件別特化モデル: {len(model._specialized.trained_segments)}セグメント学習済み")
        print(f"  ブレンド比率: メイン {1 - EnsembleModel.SPECIALIZED_BLEND_WEIGHT:.0%} + 特化 {EnsembleModel.SPECIALIZED_BLEND_WEIGHT:.0%}")


def _train_specialized(df, output_path: Path):
    """条件別特化モデルのみ学習する"""
    print("\n[2/3] 条件別特化モデル学習中...")
    model = SpecializedModel()
    results = model.train(df)

    if not model.is_trained:
        print("\n  特化モデルの学習に失敗（十分なデータがあるセグメントなし）")
        return

    print("\n  --- 特化モデル評価 ---")
    for seg_name, seg_metrics in results.items():
        print(f"    {seg_name}: AUC = {seg_metrics['mean_auc']:.4f} "
              f"± {seg_metrics['std_auc']:.4f} "
              f"({int(seg_metrics['n_samples']):,}件)")

    print("\n[3/3] モデル保存中...")
    model.save(output_path)
    print(f"\n  学習済みセグメント: {model.trained_segments}")
    print("  既存のアンサンブルモデルが次回ロード時に自動的にこの特化モデルをブレンドします。")


def _print_feature_stats(df):
    """特徴量の基本統計を表示"""
    print("\n  --- 特徴量サンプル統計 ---")
    cols_to_check = [
        "race_interval_days", "recent_avg_last_3f", "recent_avg_corner4",
        "same_distance_win_rate", "same_track_win_rate", "jockey_change",
    ]
    for col in cols_to_check:
        if col in df.columns:
            non_default = df[col].nunique()
            print(f"    {col}: mean={df[col].mean():.2f}, "
                  f"unique={non_default}, nulls={df[col].isna().sum()}")


def _print_feature_importance(model):
    """特徴量重要度を表示"""
    fi = model.get_feature_importance()
    if fi is not None:
        print("\n  --- 特徴量重要度 TOP 15 ---")
        print(fi.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
