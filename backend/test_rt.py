import sys, os, logging
sys.path.insert(0, '.')
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
from scripts.sync_jvlink import run_rt_odds
print("calling run_rt_odds for 2026042503010512...")
run_rt_odds('2026042503010512')
print("DONE")

# 確認
from app.core.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
rows = db.execute(text("SELECT horse_num, odds_win FROM race_entries re JOIN races r ON r.id=re.race_id WHERE r.race_key='2026042503010512' ORDER BY horse_num")).fetchall()
for r in rows:
    print(f"  {r[0]}番 odds={r[1]}")
db.close()
