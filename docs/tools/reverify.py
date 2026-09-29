# -*- coding: utf-8 -*-
"""复验：重启 r59，确认无弹窗、4 个游戏正常显示、shiki.json 未被污染。"""
import io
import json
import os
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
PS = r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
OUT = r'D:\r53'


def ps(a, t=240):
    return subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File'] + a,
                          capture_output=True, text=True, timeout=t)


def psc(c, t=60):
    return subprocess.run([PS, '-NoProfile', '-Command', c], capture_output=True, text=True, timeout=t)


def rd(p):
    try:
        return open(p, encoding='utf-8-sig', errors='replace').read()
    except Exception:
        return ''


def kill():
    psc("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*KeySteam*' } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    time.sleep(3)


def win_state():
    c = ("Get-Process | Where-Object { $_.ProcessName -like '*KeySteam*' } | "
         "ForEach-Object { \"$($_.Id)|$($_.MainWindowTitle)|$($_.Responding)\" }")
    return psc(c).stdout.strip()


def windows():
    """枚举顶层窗口标题与启用状态，检测是否残留更新弹窗。"""
    c = (r"Add-Type -AssemblyName UIAutomationClient; "
         r"$r=[System.Windows.Automation.AutomationElement]::RootElement; "
         r"$c=New-Object System.Windows.Automation.PropertyCondition("
         r"[System.Windows.Automation.AutomationElement]::ControlTypeProperty,"
         r"[System.Windows.Automation.ControlType]::Window); "
         r"$r.FindAll([System.Windows.Automation.TreeScope]::Children,$c) | "
         r"ForEach-Object { \"$($_.Current.Name)|en=$($_.Current.IsEnabled)\" }")
    return psc(c).stdout.strip()


exe, label = sys.argv[1], sys.argv[2]
CFG = '/mnt/c/Users/<user>/AppData/Roaming/Shikieiki/shiki.json'

print('--- 启动前 shiki.json ---')
try:
    j0 = json.load(open(CFG, encoding='utf-8-sig'))
    print('  window_size =', j0.get('window_size'))
except Exception as e:
    j0 = {}
    print('  读取失败', e)

kill()
subprocess.Popen([exe])
print(f'##### [{label}] 启动')
for _ in range(45):
    time.sleep(2)
    if psc("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*KeySteam*' } | "
           "ForEach-Object { $_.ProcessId }").stdout.strip():
        break
time.sleep(14)
print('  进程:', win_state())
print('  顶层窗口:', windows())

for _ in range(5):
    ps([OUT + r'\invoke.ps1', '-Name', '暂不更新', '-Out', OUT + r'\rv_inv.txt'])
    time.sleep(2)

print('--- 游戏列表 ---')
ps([OUT + r'\dump.ps1', '-Out', OUT + r'\rv_tree.txt', '-MaxDepth', '9'])
tree = rd(OUT + r'\rv_tree.txt')
for ln in tree.splitlines():
    if 'gamesSurface' in ln and 'ListItem' in ln:
        print('  ', ln.strip()[:160])
if '开始更新' in tree or '发现新版本' in tree:
    print('  !! 仍有更新相关窗口')
print('--- 关键按钮状态 ---')
for ln in tree.splitlines():
    if any(k in ln for k in ('updateLuaBtn', 'btn_process', 'primaryButton', 'dangerButton')):
        print('  ', ln.strip()[:150])

print('--- 启动后 shiki.json ---')
try:
    j1 = json.load(open(CFG, encoding='utf-8-sig'))
    print('  window_size =', j1.get('window_size'))
    print('  与启动前一致:', j0.get('window_size') == j1.get('window_size'))
except Exception as e:
    print('  读取失败', e)

print('--- 是否出现「发现新版本」弹窗（UIA 全窗口扫描）---')
w = windows()
print(' ', w[:500])

kill()
print('  已清理进程，存活:', bool(psc("Get-CimInstance Win32_Process | Where-Object "
                                   "{ $_.Name -like '*KeySteam*' }").stdout.strip()))
print('完成')
