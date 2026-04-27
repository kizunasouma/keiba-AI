import pickle, sys, numpy as np
sys.path.insert(0, '.')
from app.ml.features import FEATURE_COLS, build_prediction_features
from app.core.database import SessionLocal

# モデルをロードしてpredict
with open('../models/ensemble_v2.pkl', 'rb') as f:
    data = pickle.load(f)

lgbm = data['lgbm_classifier']
model_names = lgbm.feature_name()
print(f'Model features: {len(model_names)}')
print(f'Code features: {len(FEATURE_COLS)}')

# 特徴量の順序が一致するか
if model_names == FEATURE_COLS:
    print('Feature order: MATCH')
else:
    print('Feature order: MISMATCH!')
    for i, (m, c) in enumerate(zip(model_names, FEATURE_COLS)):
        if m != c:
            print(f'  [{i}] model={m} vs code={c}')

# 実際にデータを作ってpredict
db = SessionLocal()
df = build_prediction_features(db, '2026042503010501')
db.close()
print(f'\nDataFrame rows={len(df)}')

X = df[FEATURE_COLS].copy()
print(f'X shape: {X.shape}')
print(f'X dtypes problems:')
for c in FEATURE_COLS:
    if X[c].dtype == object:
        print(f'  {c}: object! sample={X[c].iloc[0]}')

# predict
preds = lgbm.predict(X)
print(f'Predictions: min={preds.min():.4f} max={preds.max():.4f} mean={preds.mean():.4f}')
print(f'First 5: {preds[:5]}')
