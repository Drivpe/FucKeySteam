# -*- coding: utf-8 -*-
"""端到端验收第 2 步：清洁启动 → 关弹窗 → 全选 4 项 → 点「更新选中Lua」→ 读日志。
全程 UIA（InvokePattern / SelectionItemPattern），不使用屏幕坐标，不修改窗口尺寸。"""
import io
import os
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PS = r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
OUT = r'D:\r53'
LOG = r'D:\03_Work\03_Develop\KeySteam v2.99\_re\_e2e.log'


def ps(args, timeout=240):
    return subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File'] + args,
                          capture_output=True, text=True, timeout=timeout)


def psc(c, timeout=60):
    return subprocess.run([PS, '-NoProfile', '-Command', c],
                          capture_output=True, text=True, timeout=timeout)


def rd(p):
    try:
        return open(p, encoding='utf-8-sig', errors='replace').read()
    except Exception:
        return ''


def kill_all():
    psc("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*KeySteam*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    time.sleep(3)


def pids():
    o = psc("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*KeySteam*' } | "
            "ForEach-Object { $_.ProcessId }")
    return [int(x) for x in o.stdout.split() if x.strip().isdigit()]


def invoke_named(name):
    ps([OUT + r'\invoke.ps1', '-Name', name, '-Out', OUT + r'\s2_inv.txt'])
    return rd(OUT + r'\s2_inv.txt')


def go_btn(aid):
    ps([OUT + r'\gobtn.ps1', '-AidSub', aid, '-Out', OUT + r'\s2_go.txt'])
    return rd(OUT + r'\s2_go.txt')


def read_logs(tag):
    ps([OUT + r'\uia_edit.ps1', '-Out', OUT + rf'\s2_edit_{tag}.txt'])
    txt = rd(OUT + rf'\s2_edit_{tag}.txt')
    out = []
    for ln in txt.splitlines():
        if ln.startswith('EDIT|'):
            out.append(ln)
    return out


def select_all():
    ps([OUT + r'\sel2.ps1', '-Out', OUT + r'\s2_sel.txt'])
    return rd(OUT + r'\s2_sel.txt')


exe, label = sys.argv[1], sys.argv[2]
kill_all()
print(f'##### [{label}] 清洁启动')
subprocess.Popen([exe])
for _ in range(45):
    time.sleep(2)
    if pids():
        break
print('  进程:', pids())
time.sleep(13)
for _ in range(5):
    r = invoke_named('暂不更新')
    if 'INVOKED' in r:
        print('  关闭更新弹窗')
    time.sleep(2)

os.makedirs(os.path.dirname(LOG), exist_ok=True)
with open(LOG, 'w', encoding='utf-8') as fh:
    fh.write('')

print('--- 全选 4 项 ---')
sel = select_all()
print(sel)
print('--- 记录 T0 日志 ---')
for l in read_logs('T0'):
    print('  ', l[:300])

print('--- 点击「更新选中Lua」 ---')
print(go_btn('updateLuaBtn'))

for i in range(1, 13):
    time.sleep(5)
    print(f'--- T{i} (+{i*5}s) ---')
    for l in read_logs(f'T{i}'):
        if 'logsSurface' in l:
            print('  ', l[:700])
    print('  存活:', bool(pids()))

kill_all()
print('完成')
