# -*- coding: utf-8 -*-
"""扫描内存中 ShikieikiC / ShikiLuaQwQ 的原始字节上下文"""
import ctypes, ctypes.wintypes as wt, re, subprocess, sys, time, io
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
def pids():
    o=sh("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*KeySteam*' } | ForEach-Object { $_.ProcessId }")
    return [int(x) for x in o.stdout.split() if x.strip().isdigit()]

TARGET=[b'ShikieikiC', b'ShikiLuaQwQ', b'ShikiLuaQwQ_old', b'oureveryday']
for pid in pids():
    h=k32.OpenProcess(PQI|PVR,False,pid)
    if not h: continue
    mbi=MBI(); addr=0; regs=[]
    while addr<0x7FFFFFFFFFFF:
        if k32.VirtualQueryEx(h,addr,ctypes.byref(mbi),ctypes.sizeof(mbi))==0: break
        if (mbi.State==MEM_COMMIT and mbi.Protect in READ
            and not (mbi.Protect&PAGE_GUARD) and 0<mbi.RegionSize<(256<<20)):
            regs.append((mbi.BaseAddress,mbi.RegionSize))
        addr=mbi.BaseAddress+mbi.RegionSize
    print(f"\n===== pid {pid}  可读区 {len(regs)}")
    hits=0
    for base,size in regs:
        off=0
        while off<size:
            n=min(4<<20,size-off)
            buf=ctypes.create_string_buffer(n); got=ctypes.c_size_t(0)
            if k32.ReadProcessMemory(h,base+off,buf,n,ctypes.byref(got)) and got.value:
                c=buf.raw[:got.value]
                for t in TARGET:
                    s=0
                    while True:
                        s=c.find(t,s)
                        if s==-1: break
                        a=max(0,s-80); b2=min(len(c),s+len(t)+80)
                        ctx=c[a:b2]
                        # 只打印看起来像文本的上下文
                        pr=sum(1 for x in ctx if 32<=x<127 or x==0)/len(ctx)
                        if pr>0.85:
                            try: print(f"  [{t.decode()}] @{base+off+s:#x}  {ctx!r}")
                            except: pass
                        hits+=1
                        s+=1
                        if hits>60: break
            off+=n
    k32.CloseHandle(h)
    if hits==0: print("  （无命中）")
