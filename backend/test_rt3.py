"""0B31のレコード構造を解析して正しいオッズ位置を特定する"""
import sys, os, subprocess, struct, io
sys.path.insert(0, '.')
from app.core.config import settings

env = os.environ.copy()
if settings.jvlink_service_key and settings.jvlink_service_key != "UNKNOWN":
    env['JVLINK_SERVICE_KEY'] = settings.jvlink_service_key
if settings.jvlink_software_id and settings.jvlink_software_id != "UNKNOWN":
    env['JVLINK_SOFTWARE_ID'] = settings.jvlink_software_id

# 確定済みレース（オッズが分かっている）のO1を取得して照合
# 福島1R: 1番人気=2番(odds=4.8), 2番人気=9番(odds=5.0)
race_key = '2026042503010501'

proc = subprocess.Popen([
    'C:/code/keiba-AI/backend/bridge/JVLinkBridge/bin/Release/net8.0-windows/JVLinkBridge.exe',
    '--rt', '--dataspec', '0B31', '--rtkey', race_key
], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

stderr = proc.stderr.read().decode('cp932', 'replace')
stdout = proc.stdout.read()
proc.wait()

if len(stdout) < 8:
    print(f'No data. stderr:\n{stderr}')
    exit()

l = struct.unpack('>I', stdout[0:4])[0]
data = stdout[4:4+l]
raw = data.decode('cp932', 'replace')

print(f'Record length: {l} bytes')
print(f'Type: {raw[0:2]}')

# 共通ヘッダー: 27バイト
# race_num at pos 25-26
print(f'Race num: {raw[25:27]}')

# DBから正解オッズを取得
from app.core.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
rows = db.execute(text("""
    SELECT re.horse_num, re.odds_win, re.popularity
    FROM race_entries re JOIN races r ON r.id=re.race_id
    WHERE r.race_key = :rk AND re.odds_win > 0
    ORDER BY re.horse_num
"""), {"rk": race_key}).fetchall()
db.close()

print(f'\n--- DB confirmed odds ---')
for r in rows:
    print(f'  Horse {r[0]:>2}: odds={r[1]:>6.1f}  pop={r[2]}')

# 生データからオッズ位置を探す
# 1番馬のオッズ=9.4, ×10=94, 文字列"00094" or "000094" or "0094"
target_odds = {r[0]: int(r[1] * 10) for r in rows}
print(f'\n--- Searching for odds patterns in raw data ---')

# 各馬のオッズ値をraw内から検索
for horse_num, odds_x10 in list(target_odds.items())[:5]:
    pattern = f'{odds_x10:06d}'
    pos = raw.find(pattern, 27)
    pattern4 = f'{odds_x10:04d}'
    pos4 = raw.find(pattern4, 27)
    print(f'  Horse {horse_num}: odds×10={odds_x10}, '
          f'6dig "{pattern}" at pos={pos}, '
          f'4dig "{pattern4}" at pos={pos4}')

# ヘッダー後のデータをダンプ（位置特定用）
print(f'\n--- Raw data dump (pos 27-130) ---')
for i in range(27, min(130, len(raw)), 6):
    chunk = raw[i:i+6]
    print(f'  pos {i:>3}: "{chunk}"')
