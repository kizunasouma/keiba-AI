"""0B31の正確なフォーマットを特定"""
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

# 正解: horse5=3.9(pop1), horse9=4.1(pop2), horse6=4.7(pop3)
# ×10: 39, 41, 47
# ×10 as 4-digit string: "0039", "0041", "0047"
# ×10 as 6-digit: "000039", "000041", "000047"

# pos 27以降を1バイトずつダンプして "0039" の出現を探す
print(f'Total length: {len(raw)}')
print(f'Header (27): {repr(raw[0:27])}')

# 全体から人気1(horse5,odds=3.9)の位置を探す
target = "0039"  # horse5 odds=3.9 → ×10=39
for i in range(27, len(raw)-3):
    if raw[i:i+4] == target:
        print(f'Found "{target}" at pos {i}')
        # 周辺データを表示
        ctx = raw[max(0,i-10):i+14]
        print(f'  context: ...{repr(ctx)}...')

# "0041" (horse9 odds=4.1)
target2 = "0041"
for i in range(27, len(raw)-3):
    if raw[i:i+4] == target2:
        print(f'Found "{target2}" at pos {i}')

# "0047" (horse6 odds=4.7)
target3 = "0047"
for i in range(27, len(raw)-3):
    if raw[i:i+4] == target3:
        print(f'Found "{target3}" at pos {i}')

# 人気番号 "01" の位置（horse5が1番人気）
# もし odds(4)+pop(2) なら、"003901" がどこかにあるはず
target_full = "003901"
for i in range(27, len(raw)-5):
    if raw[i:i+6] == target_full:
        print(f'Found "003901" at pos {i} → horse5 odds=3.9 pop=1')
        # ここからの間隔を確認
        # horse6=4.7,pop3 → "004703"
        # horse9=4.1,pop2 → "004102"

# odds(6)+pop(2)=8バイトで試す
target8 = "00003901"
for i in range(27, len(raw)-7):
    if raw[i:i+8] == target8:
        print(f'Found "00003901" at pos {i}')
