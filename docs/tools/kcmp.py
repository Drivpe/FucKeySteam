# -*- coding: utf-8 -*-
"""内核 A/B 严格对照：同一 exe、同一游戏(3934270)、同一动作(更新选中Lua)，
切换内核 → 点更新 → 等 40s → 比对文件 mtime/md5 与日志。
把 3934270.ks 先改成一个可识别的「哨兵」内容，谁改动它谁就赢了。
"""
import hashlib, io, os, subprocess, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
PS = r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
OUT = r'D:\r53'
SP = '/mnt/d/02_Games/01_Steam/Steam/config/stplug-in'
TARGET = '3934270.ks'
SENTINEL = b'-- SENTINEL untouched\n'

def psf(a, t=300):
    return subprocess.run([PS,'-NoProfile','-ExecutionPolicy','Bypass','-File']+a,
                          capture_output=True,text=True,timeout=t)
def psc(c, t=90):
    return subprocess.run([PS,'-NoProfile','-Command',c],capture_output=True,text=True,timeout=t)
def rd(p):
    try: return open(p,encoding='utf-8-sig',errors='replace').read()
    except Exception: return ''
def pids():
    o=psc("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*KeySteam*' } | ForEach-Object { $_.ProcessId }")
    return [int(x) for x in o.stdout.split() if x.strip().isdigit()]
def kill():
    psc("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*KeySteam*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    time.sleep(3)
def invoke(name, tag):
    psf([OUT+r'\invoke.ps1','-Name',name,'-Out',OUT+rf'\c_{tag}.txt'])
    return rd(OUT+rf'\c_{tag}.txt')
def radio(name, tag):
    psf([OUT+r'\radio.ps1','-Name',name,'-Out',OUT+rf'\c_rad_{tag}.txt'])
    return rd(OUT+rf'\c_rad_{tag}.txt')
def logtext():
    psf([OUT+r'\uia_edit.ps1','-Out',OUT+r'\c_log.txt'])
    for l in rd(OUT+r'\c_log.txt').splitlines():
        if 'logsSurface' in l and 'val=' in l:
            return l[l.find('val=')+4:]
    return ''
def state():
    p=os.path.join(SP,TARGET)
    if not os.path.exists(p): return ('缺失',None,None)
    b=open(p,'rb').read()
    return (len(b), hashlib.md5(b).hexdigest()[:12], os.path.getmtime(p))

exe, kernel = sys.argv[1], sys.argv[2]
# 打哨兵
open(os.path.join(SP,TARGET),'wb').write(SENTINEL)
print(f'##### kernel={kernel!r}  哨兵已打: {state()}')

kill()
subprocess.Popen([exe])
for _ in range(45):
    time.sleep(2)
    if pids(): break
time.sleep(13)
for _ in range(4):
    invoke('暂不更新','skip'); time.sleep(2)

invoke('高级设置','adv'); time.sleep(3)
print('  选内核:', radio(kernel,'set').strip()[:100])
time.sleep(2)
print('  保存:', invoke('保  存','save').strip()[:100])
time.sleep(3)
for b in ('取  消','关  闭','确定'):
    if 'INVOKED' in invoke(b,'cls'): break
time.sleep(2)

print('  选游戏:', end=' ')
psf([OUT+r'\selone.ps1','-AppID','3934270','-Out',OUT+r'\c_sel.txt'])
print([l[:60] for l in rd(OUT+r'\c_sel.txt').splitlines() if l.startswith('PICKED')])
print('  T0 日志:', logtext()[-200:])
print('  点更新:', invoke('更新选中Lua','go').strip()[:90])

for i in range(1,8):
    time.sleep(6)
    st=state()
    print(f'  T{i}(+{i*6}s) 文件={st[0]}B md5={st[1]} 日志={logtext()[-260:]!r}')
    if st[1] and st[1]!=hashlib.md5(SENTINEL).hexdigest()[:12]:
        print(f'  >>> 文件已被改写！{kernel} 生效')
        break
print('  最终:', state())
kill()
print('  残留:', len(pids()))
