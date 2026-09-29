# -*- coding: utf-8 -*-
"""读取运行中 r40 进程的 main.dll 基址与槽值，判定 Py_True/Py_False/Py_None"""
import ctypes, ctypes.wintypes as wt, sys, io, time, subprocess, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
k32=ctypes.windll.kernel32; psapi=ctypes.windll.psapi
PS=r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
def sh(c): return subprocess.run([PS,'-NoProfile','-Command',c],capture_output=True,text=True)
def pids(pat):
    o=sh(f"Get-CimInstance Win32_Process | Where-Object {{ $_.Name -like '*{pat}*' }} | ForEach-Object {{ $_.ProcessId }}")
    return [int(x) for x in o.stdout.split() if x.strip().isdigit()]
def modules(pid):
    h=k32.OpenProcess(0x0410,False,pid)
    if not h: return None,[]
    mods=(ctypes.c_void_p*2048)(); need=ctypes.c_uint()
    if not psapi.EnumProcessModules(ctypes.c_void_p(h),mods,ctypes.sizeof(mods),ctypes.byref(need)): return h,[]
    n=need.value//ctypes.sizeof(ctypes.c_void_p); out=[]
    for i in range(n):
        buf=ctypes.create_unicode_buffer(512)
        psapi.GetModuleBaseNameW(ctypes.c_void_p(h),ctypes.c_void_p(mods[i]),buf,512)
        out.append((buf.value, mods[i]))
    return h,out
def rd(h,addr,n):
    buf=ctypes.create_string_buffer(n); got=ctypes.c_size_t()
    if not k32.ReadProcessMemory(ctypes.c_void_p(h),ctypes.c_void_p(addr),buf,n,ctypes.byref(got)): return None
    return buf.raw[:got.value]
def tname(h,obj):
    t=rd(h,obj+8,8)
    if not t: return None
    tp=struct.unpack('<Q',t)[0]
    nm=rd(h,tp+0x18,8)
    if not nm: return None
    s=rd(h,struct.unpack('<Q',nm)[0],32)
    return s.split(b'\0')[0].decode('latin1') if s else None

ps=pids('KeySteam_r40')
if not ps: print("需先启动 r40"); sys.exit(1)
h=mods=None; base=None
for pid in ps:
    hh,mm=modules(pid)
    names=[n for n,_ in mm]
    if any('main' in n.lower() for n in names):
        h,mods=hh,mm
        for nm,b in mm:
            if nm.lower()=='main.dll': base=b
        print(f"   pid={pid} 找到 main.dll base=0x{base:X}")
        break
print(f"pid={ps[0]} main.dll base=0x{base:X}" if base else "main.dll 未找到")
if base:
    for label,rva,ilen in [("slot@FE8571(对比None)",0xFE8571,7),("slot@FE8592(返回)",0xFE8592,7)]:
        va=base+rva
        ins=rd(h,va,8)
        # mov rbx/rax,[rip+disp] : 48 8B 1D / 48 8B 05
        disp=struct.unpack('<i',ins[3:7])[0]
        tgt=va+ilen+disp
        val=rd(h,tgt,8)
        obj=struct.unpack('<Q',val)[0] if val else 0
        print(f"  {label}: ins={ins.hex()} disp=0x{disp:X} tgt=0x{tgt:X} obj=0x{obj:X} type={tname(h,obj)}")
k32.CloseHandle(ctypes.c_void_p(h))
