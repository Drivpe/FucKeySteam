# -*- coding: utf-8 -*-
import ctypes, ctypes.wintypes as wt, subprocess, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
k32=ctypes.WinDLL("kernel32",use_last_error=True)
PQI=0x0400;PVR=0x0010;MC=0x1000;PG=0x100;RD={0x02,0x04,0x20,0x40,0x80}
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
o=sh("Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*KeySteam*' } | ForEach-Object { $_.ProcessId }")
pids=[int(x) for x in o.stdout.split() if x.strip().isdigit()]
print("pids:",pids)
for pid in pids:
    h=k32.OpenProcess(PQI|PVR,False,pid)
    if not h: continue
    mbi=MBI();a=0;regs=[]
    while a<0x7FFFFFFFFFFF:
        if k32.VirtualQueryEx(h,a,ctypes.byref(mbi),ctypes.sizeof(mbi))==0: break
        if mbi.State==MC and mbi.Protect in RD and not(mbi.Protect&PG) and 0<mbi.RegionSize<(256<<20):
            regs.append((mbi.BaseAddress,mbi.RegionSize))
        a=mbi.BaseAddress+mbi.RegionSize
    print(f"\n### pid {pid} regs={len(regs)}")
    for base,size in regs:
        off=0
        while off<size:
            n=min(4<<20,size-off)
            buf=ctypes.create_string_buffer(n);got=ctypes.c_size_t(0)
            if k32.ReadProcessMemory(h,base+off,buf,n,ctypes.byref(got)) and got.value:
                c=buf.raw[:got.value]
                for t in (b'ShikieikiC',b'ShikiLuaQwQ'):
                    s=0
                    while True:
                        s=c.find(t,s)
                        if s==-1: break
                        lo=max(0,s-70); hi=min(len(c),s+len(t)+70)
                        seg=c[lo:hi]
                        pr=sum(1 for x in seg if 32<=x<127 or x==0)/len(seg)
                        if pr>0.9:
                            print(f"  [{t.decode()}] {seg!r}")
                        s+=1
            off+=n
    k32.CloseHandle(h)
