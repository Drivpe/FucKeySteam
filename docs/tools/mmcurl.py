# -*- coding: utf-8 -*-
"""在指定内核下抓取程序构造的真实 URL（启动时 + 点更新后各一次）。
用法: mmcurl.py <exe> <label> <kernel: keep|KeySteamTool 内核|TanuShiki 内核>
"""
import ctypes
import ctypes.wintypes as wt
import io
import os
import re
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PQI = 0x0400
PVR = 0x0010
MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
READ = {0x02, 0x04, 0x20, 0x40, 0x80, 0x10}


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong), ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", wt.DWORD), ("__a1", wt.DWORD), ("RegionSize", ctypes.c_ulonglong),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD), ("__a2", wt.DWORD)]


k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_ulonglong, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_ulonglong, ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.POINTER(ctypes.c_size_t)]

PS = r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
OUT = r'D:\r53'

PATS = [re.compile(rb'https?://[^\x00\s"\']{20,400}'),
        re.compile(rb'Cec1c'), re.compile(rb'ShikieikiC'),
        re.compile(rb'ShikiLuaQwQ'), re.compile(rb'[A-Za-z0-9_\-]{50,70}\.qwq')]


def sh(c):
    return subprocess.run([PS, '-NoProfile', '-Command', c], capture_output=True, text=True)


def kill():
    sh("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*KeySteam*' } | "
       "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    time.sleep(3)


def pids():
    o = sh("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*KeySteam*' } | "
           "ForEach-Object { $_.ProcessId }")
    return [int(x) for x in o.stdout.split() if x.strip().isdigit()]


def scan(pid):
    h = k32.OpenProcess(PQI | PVR, False, pid)
    if not h:
        return {}
    mbi = MBI()
    addr = 0
    regs = []
    while addr < 0x7FFFFFFFFFFF:
        if k32.VirtualQueryEx(h, addr, ctypes.byref(mbi), ctypes.sizeof(mbi)) == 0:
            break
        if (mbi.State == MEM_COMMIT and mbi.Protect in READ and not (mbi.Protect & PAGE_GUARD)
                and 0 < mbi.RegionSize < (256 << 20)):
            regs.append((mbi.BaseAddress, mbi.RegionSize))
        addr = mbi.BaseAddress + mbi.RegionSize
    found = {}
    CH = 4 << 20
    for base, size in regs:
        off = 0
        while off < size:
            n = min(CH, size - off)
            buf = ctypes.create_string_buffer(n)
            got = ctypes.c_size_t(0)
            if k32.ReadProcessMemory(h, base + off, buf, n, ctypes.byref(got)) and got.value:
                c = buf.raw[:got.value]
                for p in PATS:
                    for m in p.finditer(c):
                        try:
                            s = m.group().decode('utf-8')
                        except Exception:
                            continue
                        found[s] = found.get(s, 0) + 1
            off += n
    k32.CloseHandle(h)
    return found


def grab(tag):
    agg = {}
    for pid in pids():
        try:
            for k, v in scan(pid).items():
                agg[k] = agg.get(k, 0) + v
        except Exception as e:
            print(f'   scan {pid} ERR {e}')
    keep = [s for s in agg if 'Cec1c' in s or 'Shikie' in s or 'ShikiLuaQwQ' in s or '.qwq' in s]
    print(f'  --- [{tag}] 库相关命中 {len(keep)} ---')
    for s in sorted(keep):
        print(f'    [{agg[s]:3d}] {s[:250]}')
    if not keep:
        print('    (无)')
    return agg


def ps_file(a, t=300):
    return subprocess.run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File'] + a,
                          capture_output=True, text=True, timeout=t)


def invoke(name, tag):
    ps_file([OUT + r'\invoke.ps1', '-Name', name, '-Out', OUT + rf'\m_{tag}.txt'])
    try:
        return open(OUT + rf'\m_{tag}.txt', encoding='utf-8-sig', errors='replace').read()
    except Exception:
        return ''


def radio(name, tag):
    ps_file([OUT + r'\radio.ps1', '-Name', name, '-Out', OUT + rf'\m_rad_{tag}.txt'])
    try:
        return open(OUT + rf'\m_rad_{tag}.txt', encoding='utf-8-sig', errors='replace').read()
    except Exception:
        return ''


exe, label = sys.argv[1], sys.argv[2]
kernel = sys.argv[3] if len(sys.argv) > 3 else 'keep'

print(f'##### [{label}] kernel={kernel!r}')
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

if kernel != 'keep':
    invoke('高级设置', 'adv')
    time.sleep(3)
    print('  选内核:', radio(kernel, 'set').strip()[:120])
    time.sleep(2)
    print('  保存:', invoke('保  存', 'save').strip()[:120])
    time.sleep(3)
    for b in ('取  消', '关  闭', '确定'):
        if 'INVOKED' in invoke(b, 'cls'):
            break
    time.sleep(2)

print('=== 抓取 A：启动后 ===')
grab('A-启动后')

print('=== 选中 3934270 并点更新 ===')
ps_file([OUT + r'\selone.ps1', '-AppID', '3934270', '-Out', OUT + r'\m_sel.txt'])
print('  ', invoke('更新选中Lua', 'go').strip()[:120])
time.sleep(8)
print('=== 抓取 B：点击后 ===')
grab('B-点击后')
time.sleep(8)
print('=== 抓取 C：+16s ===')
grab('C-再8s')

kill()
print('  已清理，残留:', len(pids()))
print('完成')
