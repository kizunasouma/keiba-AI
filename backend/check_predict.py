import sys
sys.path.insert(0, '.')
from app.core.database import SessionLocal
from app.ml.features import build_prediction_features, FEATURE_COLS
import pickle

db = SessionLocal()
df = build_prediction_features(db, '2026042503010501')
db.close()

print(f'rows={len(df)}')
if len(df) > 0:
    print(f'odds_win unique: {sorted(df["odds_win"].unique())}')
    print(f'popularity unique: {sorted(df["popularity"].unique())}')
    for _, row in df.head(5).iterrows():
        print(f'  {int(row["horse_num"])}番 odds={row["odds_win"]:.1f} pop={int(row["popularity"])} '
              f'jockey_wr={row.get("jockey_win_rate",0):.3f} trainer_wr={row.get("trainer_win_rate",0):.3f} '
              f'horse_wr={row.get("horse_win_rate",0):.3f}')

    with open('../models/ensemble_v2.pkl', 'rb') as f:
        data = pickle.load(f)
    lgbm = data['lgbm_classifier']
    X = df[FEATURE_COLS].copy()
    preds = lgbm.predict(X)
    for i, (_, row) in enumerate(df.head(8).iterrows()):
        print(f'  {int(row["horse_num"])}番 pred={preds[i]*100:.2f}%')
