import sys, os, subprocess, struct, io
sys.path.insert(0, '.')
from app.core.config import settings

env = os.environ.copy()
if settings.jvlink_service_key and settings.jvlink_service_key != "UNKNOWN":
    env['JVLINK_SERVICE_KEY'] = settings.jvlink_service_key
if settings.jvlink_software_id and settings.jvlink_software_id != "UNKNOWN":
    env['JVLINK_SOFTWARE_ID'] = settings.jvlink_software_id
print(f'SID={env.get("JVLINK_SOFTWARE_ID","(none)")}')

proc = subprocess.Popen([
    'C:/code/keiba-AI/backend/bridge/JVLinkBridge/bin/Release/net8.0-windows/JVLinkBridge.exe',
    '--rt', '--dataspec', '0B31', '--rtkey', '2026042503010512'
], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)

# まずstderrを読む
stderr = proc.stderr.read().decode('cp932', 'replace')
stdout = proc.stdout.read()
proc.wait()

print(f'stderr:\n{stderr}')
print(f'stdout len: {len(stdout)}')

if len(stdout) >= 8:
    l = struct.unpack('>I', stdout[0:4])[0]
    print(f'first record len: {l}')
    if l > 0:
        data = stdout[4:4+l]
        raw = data.decode('cp932', 'replace')
        print(f'record_type={raw[0:2]}')
        print(f'race_num={raw[25:27]}')
        # 各馬のオッズ
        for i in range(16):
            pos = 35 + i * 20
            if pos + 20 > len(raw): break
            num = raw[pos:pos+2]
            odds_w = raw[pos+2:pos+8]
            print(f'  [{i+1}] num={num} odds_win_raw={odds_w} -> {int(odds_w)/10 if odds_w.isdigit() else "?"}')
