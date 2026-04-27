"""マイラーズカップのリアルタイムオッズ取得テスト"""
import sys, os, subprocess, struct
sys.path.insert(0, '.')
from app.core.config import settings
from app.core.database import SessionLocal
from sqlalchemy import text as sql_text

env = os.environ.copy()
if settings.jvlink_service_key and settings.jvlink_service_key != "UNKNOWN":
    env['JVLINK_SERVICE_KEY'] = settings.jvlink_service_key

race_key = '2026042608030211'  # マイラーズカップ
print(f'Fetching odds for {race_key}...')

proc = subprocess.Popen([
    'C:/code/keiba-AI/backend/bridge/JVLinkBridge/bin/Release/net8.0-windows/JVLinkBridge.exe',
    '--rt', '--dataspec', '0B31', '--rtkey', race_key
], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

stdout_data = proc.stdout.read()
stderr_data = proc.stderr.read().decode('cp932', 'replace')
proc.wait()

print(f'stdout={len(stdout_data)}, rc={proc.returncode}')
# stderrからJVRTOpenの結果を確認
for line in stderr_data.split('\n'):
    if 'JVRTOpen' in line or 'ERROR' in line or '完了' in line:
        print(f'  {line.strip()}')

if len(stdout_data) < 8:
    print('No data returned')
    exit()

l = struct.unpack('>I', stdout_data[0:4])[0]
if l == 0:
    print('EOF marker (no records)')
    exit()

data = stdout_data[4:4+l]
raw = data.decode('cp932', 'replace')
print(f'Record: type={raw[0:2]}, len={l}')

# パース
entries = []
for i in range(18):
    p = 43 + i * 8
    if p + 8 > len(raw): break
    c = raw[p:p+8]
    try:
        n = int(c[0:2])
        o = int(c[2:6]) / 10.0
        pp = int(c[6:8])
        if n > 0 and o > 0:
            entries.append({"horse_num": n, "odds_win": o, "popularity": pp})
            print(f'  {n:>2}番 {o:>7.1f}倍 {pp}番人気')
    except:
        pass

if entries:
    db = SessionLocal()
    for e in entries:
        db.execute(sql_text("""
            UPDATE race_entries re SET odds_win = :odds, popularity = :pop
            FROM races r
            WHERE r.id = re.race_id AND r.race_key = :rk AND re.horse_num = :hn
        """), {"odds": e["odds_win"], "pop": e["popularity"], "rk": race_key, "hn": e["horse_num"]})
    db.commit()
    db.close()
    print(f'\nDB更新完了: {len(entries)}頭')
else:
    print('No entries parsed')
