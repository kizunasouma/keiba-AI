"""0B31フォーマット特定 - 8バイトずつパース"""
import sys, os, subprocess, struct
sys.path.insert(0, '.')
from app.core.config import settings
env = os.environ.copy()
if settings.jvlink_service_key and settings.jvlink_service_key != "UNKNOWN":
    env['JVLINK_SERVICE_KEY'] = settings.jvlink_service_key
proc = subprocess.Popen([
    'C:/code/keiba-AI/backend/bridge/JVLinkBridge/bin/Release/net8.0-windows/JVLinkBridge.exe',
    '--rt', '--dataspec', '0B31', '--rtkey', '2026042503010501'
], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
stderr = proc.stderr.read()
stdout = proc.stdout.read()
proc.wait()
l = struct.unpack('>I', stdout[0:4])[0]
raw = stdout[4:4+l].decode('cp932', 'replace')

# "003901"がpos77にある。馬番5。直前が"05"ならpos75="05"=馬番5
# 各馬のデータ: num(2)+odds(4)+pop(2)=8バイト
# 開始位置を探す: pos75-8=67, 67-8=59, ...

# "003901"の直前2バイトが馬番なら→ pos75="05", データ開始はpos75
# 馬番5のデータはpos75-77-82=75: "05003901" → num=05, odds=0039(3.9), pop=01 ✓!

# 逆算: 馬番1はpos 75 - (5-1)*8 = 75-32 = 43
# 馬番1のデータ: pos 43-50

start = 75 - (5-1) * 8  # = 43
print(f'Estimated start: pos {start}')
print(f'Header extended: pos 27-{start-1} = "{raw[27:start]}"')
print()

for i in range(18):
    p = start + i * 8
    if p + 8 > len(raw): break
    chunk = raw[p:p+8]
    num_s = chunk[0:2]
    odds_s = chunk[2:6]
    pop_s = chunk[6:8]
    try:
        num = int(num_s)
        odds = int(odds_s) / 10
        pop = int(pop_s)
        print(f'  pos {p}: num={num:>2} odds={odds:>7.1f} pop={pop:>2}')
    except:
        print(f'  pos {p}: raw="{chunk}" (parse error)')
