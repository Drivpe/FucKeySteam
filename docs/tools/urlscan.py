# -*- coding: utf-8 -*-
"""扫 KeySteam 进程内存，抓取 github/lua 相关 URL"""
import ctypes, ctypes.wintypes as wt, re, subprocess, sys, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
PROCESS_QUERY_INFORMATION=0x0400; PROCESS_VM_READ=0x0010
MEM_COMMIT=0x1000; PAGE_GUARD=0x100
READABLE={0x02,0x04,0x20,0x40,0x80}

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

pid=int(sys.argv[1]) if len(sys.argv)>1 else None
if pid is None:
    ps=pids()
    if not ps: print("无进程"); sys.exit(1)
    pid=ps[0]
print("扫描 pid", pid)
h=k32.OpenProcess(PROCESS_QUERY_INFORMATION|PROCESS_VM_READ, False, pid)
if not h: print("OpenProcess 失败", ctypes.get_last_error()); sys.exit(1)

mbi=MBI(); addr=0; regs=[]
while addr < 0x7FFFFFFFFFFF:
    if k32.VirtualQueryEx(h, addr, ctypes.byref(mbi), ctypes.sizeof(mbi))==0: break
    if (mbi.State==MEM_COMMIT and mbi.Protect in READABLE and not (mbi.Protect & PAGE_GUARD)
        and 0 < mbi.RegionSize < (256<<20)):
        regs.append((mbi.BaseAddress, mbi.RegionSize))
    addr = mbi.BaseAddress + mbi.RegionSize
print("可读区域", len(regs))

pats=[re.compile(rb'https?://[^\x00\s"\']{10,300}'),
      re.compile(rb'[A-Za-z0-9_\-]{40,90}\.qwq'),
      re.compile(rb'SHIKI[0-9a-f]{16}KAWAII')]
found={}
CH=4<<20
for base,size in regs:
    off=0
    while off<size:
        buf=ctypes.create_string_buffer(min(CH,size-off))
        got=ctypes.c_size_t(0)
        if k32.ReadProcessMemory(h, base+off, buf, len(buf), ctypes.byref(got)) and got.value:
            chunk=buf.raw[:got.value]
            for p in pats:
                for m in p.finditer(chunk):
                    try: s=m.group().decode('utf-8')
                    except: continue
                    found.setdefault(s, 0)
                    found[s]+=1
        off+=CH
k32.CloseHandle(h)
print("\n命中字符串:", len(found))
for s,c in sorted(found.items()):
    if any(k in s for k in ('github','qwq','jsdelivr','shiki','SHIKI','lua','steamofl')):
        print(f"  [{c}] {s}")
