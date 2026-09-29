# -*- coding: utf-8 -*-
"""内核部署验证：切换内核 → 保存 → 观察 Steam/dwmapi.dll 变化。
只使用 UIA，不碰屏幕坐标，不改窗口尺寸。
用法: kdeploy.py <exe> <kernel>
"""
import io
import hashlib
import os
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
PS = r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
OUT = r'D:\r53'

STEAM = r'D:\02_Games\01_Steam\Steam'
CORE = r'<USERPROFILE>\AppData\Roaming\Shikieiki\shiki\core'
CFG = r'<USERPROFILE>\AppData\Roaming\Shikieiki\shiki.json'

WATCH = ['dwmapi.dll', 'KeySteamTool.dll', 'shiki2.dll', 'shiki3.dll',
         'xinput1_4.dll', 'cloud_redirect.dll']


def psf(a, t=300):
    return subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File'] + a,
                          capture_output=True, text=True, timeout=t)


def psc(c, t=90):
    return subprocess.run([PS, '-NoProfile', '-Command', c], capture_output=True, text=True, timeout=t)


def rd(p):
    try:
        return open(p, encoding='utf-8-sig', errors='replace').read()
    except Exception:
        return ''


def pids():
    o = psc("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*KeySteam*' } | "
            "ForEach-Object { $_.ProcessId }")
    return [int(x) for x in o.stdout.split() if x.strip().isdigit()]


def kill():
    psc("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*KeySteam*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    time.sleep(3)


def invoke(name, tag):
    psf([OUT + r'\invoke.ps1', '-Name', name, '-Out', OUT + rf'\d_{tag}.txt'])
    return rd(OUT + rf'\d_{tag}.txt')


def radio(name, tag):
    psf([OUT + r'\radio.ps1', '-Name', name, '-Out', OUT + rf'\d_rad_{tag}.txt'])
    return rd(OUT + rf'\d_rad_{tag}.txt')


def dump(tag):
    p = ','.join(str(x) for x in pids())
    psf([OUT + r'\dump2.ps1', '-Out', OUT + rf'\d_tree_{tag}.txt', '-MaxDepth', '10', '-Pids', p])
    return rd(OUT + rf'\d_tree_{tag}.txt')


def snap():
    r = {}
    for d, tag in ((STEAM, 'steam'), (CORE, 'core')):
        for f in WATCH:
            p = os.path.join(d, f)
            if os.path.isfile(p):
                b = open(p, 'rb').read()
                r[f'{tag}/{f}'] = (len(b), hashlib.md5(b).hexdigest()[:10])
            else:
                r[f'{tag}/{f}'] = None
    return r


def show(tag, s):
    print(f'  --- {tag} ---')
    for k in sorted(s):
        v = s[k]
        print(f'    {k:32s} {"缺失" if v is None else f"{v[0]:>9,}B  {v[1]}"}')


kernel = sys.argv[2] if len(sys.argv) > 2 else 'KeySteamTool 内核'
exe = sys.argv[1]

print(f'##### 目标内核 = {kernel!r}')
print('=== 测试前 ===')
b = snap()
show('before', b)
try:
    cfg0 = open(CFG, encoding='utf-8-sig').read()
    print('  shiki.json steam_kernel =', __import__('json').loads(cfg0).get('steam_kernel'))
except Exception as e:
    print('  cfg 读取失败', e)

print('  Steam 是否运行:',
      bool(psc("Get-Process steam -ErrorAction SilentlyContinue").stdout.strip()))

kill()
subprocess.Popen([exe])
for _ in range(45):
    time.sleep(2)
    if pids():
        break
print('  进程:', pids())
time.sleep(14)
for _ in range(4):
    invoke('暂不更新', 'skip')
    time.sleep(2)

print('--- 打开高级设置 ---')
invoke('高级设置', 'adv')
time.sleep(3)
print('  选内核:', radio(kernel, 'set').strip()[:140])
time.sleep(2)
print('  保存:', invoke('保  存', 'save').strip()[:140])
time.sleep(4)

for tag in ('t1', 't2'):
    a = snap()
    show(f'after-save-{tag}', a)
    chg = [k for k in set(a) | set(b) if a.get(k) != b.get(k)]
    print('    变化:', chg if chg else '无')
    if chg:
        break
    time.sleep(4)

try:
    import json
    print('  shiki.json steam_kernel =',
          json.loads(open(CFG, encoding='utf-8-sig').read()).get('steam_kernel'))
except Exception as e:
    print('  cfg 读取失败', e)

kill()
print('  残留:', len(pids()))
print('完成')
