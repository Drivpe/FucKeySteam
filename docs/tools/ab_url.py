# -*- coding: utf-8 -*-
"""A/B 对照：启动指定 exe，扫内存抓取所有 github/lua URL，不点击任何按钮。"""
import ctypes, ctypes.wintypes as wt, re, subprocess, sys, time, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PQI=0x0400; PVR=0x0010; MEM_COMMIT=0x1000; PAGE_GUARD=0x100
READ={0x02,0x04,0x20,0x40,0x80}
class MBI(ctypes.Structure):
    _fields_=[("BaseAddress",ctypes.c_ulonglong),("AllocationBase",ctypes.c_ulonglong),
              ("AllocationProtect",wt.DWORD),("__a1",wt.DWORD),("RegionSize",ctypes.c_ulonglong),
              ("State",wt.DWORD),("Protect",wt.DWORD),("Type",wt.DWORD),("__a2",wt.DWORD)]
k32.OpenProcess.restype=wt.HANDLE
k32.OpenProcess.argtypes=[wt.DWORD,wt.BOOL,wt.DWORD]
k32.VirtualQueryEx.argtypes=[wt.HANDLE,ctypes.c_ulonglong,ctypes.POINTER(MBI),ctypes.c_size_t]
k32.ReadProcessMemory.argtypes=[wt.HANDLE,ctypes.c_ulonglong,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]

PS=r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
def sh(c): return subprocess.run([PS,'-NoProfile','-Command',c],capture_output=True,text=True)
def kill():
    sh("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*KeySteam*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    time.sleep(2.5)
def pids():
    o=sh("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*KeySteam*' } | ForEach-Object { $_.ProcessId }")
    return [int(x) for x in o.stdout.split() if x.strip().isdigit()]

PATS=[re.compile(rb'https?://[^\x00\s"\']{20,400}'),
      re.compile(rb'ShikieikiC'), re.compile(rb'ShikiLuaQwQ'),
      re.compile(rb'Cec1c'), re.compile(rb'oureveryday'),
      re.compile(rb'[A-Za-z0-9_\-]{50,70}\.qwq')]

def scan(pid):
    h=k32.OpenProcess(PQI|PVR,False,pid)
    if not h: return {}
    mbi=MBI(); addr=0; regs=[]
    while addr<0x7FFFFFFFFFFF:
        if k32.VirtualQueryEx(h,addr,ctypes.byref(mbi),ctypes.sizeof(mbi))==0: break
        if (mbi.State==MEM_COMMIT and mbi.Protect in READ
            and not (mbi.Protect&PAGE_GUARD) and 0<mbi.RegionSize<(256<<20)):
            regs.append((mbi.BaseAddress,mbi.RegionSize))
        addr=mbi.BaseAddress+mbi.RegionSize
    found={}
    CH=4<<20
    for base,size in regs:
        off=0
        while off<size:
            n=min(CH,size-off)
            buf=ctypes.create_string_buffer(n); got=ctypes.c_size_t(0)
            if k32.ReadProcessMemory(h,base+off,buf,n,ctypes.byref(got)) and got.value:
                c=buf.raw[:got.value]
                for p in PATS:
                    for m in p.finditer(c):
                        try: s=m.group().decode('utf-8')
                        except: continue
                        found[s]=found.get(s,0)+1
            off+=n
    k32.CloseHandle(h)
    return found

def run(exe, label, wait=38):
    kill()
    print(f"\n{'='*78}\n##### [{label}] {exe}")
    subprocess.Popen([exe])
    time.sleep(wait)
    ps=pids()
    print(f"  进程: {ps}")
    agg={}
    for pid in ps:
        try:
            f=scan(pid)
            for k,v in f.items(): agg[k]=agg.get(k,0)+v
        except Exception as e:
            print(f"   scan {pid} ERR {e}")
    keep=[s for s in agg if ('github' in s or '.qwq' in s or 'Shikie' in s
                             or 'Cec1c' in s or 'oureveryday' in s)]
    for s in sorted(keep):
        print(f"    [{agg[s]:3d}] {s[:230]}")
    if not keep: print("    （无 github/库相关字符串）")
    return agg

if __name__=='__main__':
    targets=[(r'D:\03_Work\03_Develop\KeySteam v2.99\KeySteam.exe','ORIG'),
             (r'D:\03_Work\03_Develop\KeySteam v2.99\KeySteam_r58_可用.exe','R58')]
    if len(sys.argv)>2:
        targets=[(sys.argv[1], sys.argv[2])]
    for exe,label in targets:
        run(exe,label)
    kill()
    print("\n完成")
