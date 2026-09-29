#!/usr/bin/env python3
"""Nuitka constants blob 权威解码器 —— 依 HelpersConstantsBlob.c 的 _unpackVariableLength (LEB128)。
关键修正：所有 count/size 都是 **变长整数 (LEB128)**，不是 u8/u16/u32 定宽。
"""
import sys,struct,json
sys.path.insert(0,'/mnt/d/03_Work/03_Develop/KeySteam v2.99/_re/ghidra/tools')
from binlib import Bin
DLL=r'/mnt/d/ks_debug/main.dll'
b=Bin(DLL); d=b.data

def vlen(buf,p):
    """LEB128 变长整数（低位在前，7 bit/byte，<0x80 结束）"""
    r=0; f=1
    while True:
        c=buf[p]; p+=1
        r += (c & 127)*f
        if c < 128: break
        f <<= 7
    return r,p

class Dec:
    def __init__(s,buf): s.buf=buf
    def zs(s,p):
        z=s.buf.index(b'\0',p); return s.buf[p:z],z+1
    def read(s,p,dep=0):
        if dep>400: raise ValueError('deep')
        buf=s.buf
        if p>=len(buf): raise ValueError('eof')
        tag=buf[p]; p0=p; p+=1
        if tag in (0x61,0x75,0x45,0x4f,0x4d,0x51):
            v,p=s.zs(p); return (chr(tag),v),p
        if tag==0x73: return ('s',b''),p
        if tag==0x77: return ('w',buf[p:p+1]),p+1
        if tag==0x76:
            L,p=vlen(buf,p); return ('v',buf[p:p+L]),p+L
        if tag==0x62:
            L,p=vlen(buf,p); return ('b',buf[p:p+L]),p+L
        if tag==0x63: v,p=s.zs(p); return ('c',v),p
        if tag==0x64: return ('d',buf[p:p+1]),p+1
        if tag in (0x69,0x49):
            v,p=vlen(buf,p)
            return ('i' if tag==0x69 else 'I', v if tag==0x69 else -v),p
        if tag in (0x6c,0x71):
            v,p=vlen(buf,p)
            return ('l' if tag==0x6c else 'q', v if tag==0x6c else -v),p
        if tag in (0x67,0x47):
            L,p=vlen(buf,p); return ('g',buf[p:p+L]),p+L
        if tag==0x66: return ('f',struct.unpack_from('<d',buf,p)[0]),p+8
        if tag==0x5a: return ('Z',buf[p]),p+1
        if tag==0x4a: return ('J',buf[p]),p+1
        if tag==0x6a: return ('j',struct.unpack_from('<dd',buf,p)),p+16
        if tag==0x6e: return ('n',None),p
        if tag==0x74: return ('t',True),p
        if tag==0x46: return ('F',False),p
        if tag==0x70: return ('p',None),p
        if tag==0x2e: return ('.',None),p
        if tag in (0x54,0x4c,0x53,0x50,0x44):
            cnt,p=vlen(buf,p)
            it=[]
            for _ in range(cnt):
                if tag==0x44:
                    k,p=s.read(p,dep+1); v,p=s.read(p,dep+1); it.append((k,v))
                else:
                    x,p=s.read(p,dep+1); it.append(x)
            return ({0x54:'T',0x4c:'L',0x53:'S',0x50:'P',0x44:'D'}[tag],cnt,it),p
        if tag==0x3a:
            a,p=s.read(p,dep+1); b2,p=s.read(p,dep+1); c2,p=s.read(p,dep+1)
            return (':',a,b2,c2),p
        if tag==0x3b:
            a,p=s.read(p,dep+1); b2,p=s.read(p,dep+1); c2,p=s.read(p,dep+1)
            return (';',a,b2,c2),p
        if tag==0x58:
            L,p=vlen(buf,p); return ('X',buf[p:p+L]),p+L
        if tag==0x41:
            a,p=s.read(p,dep+1); b2,p=s.read(p,dep+1); return ('A',a,b2),p
        if tag==0x48:
            cnt,p=vlen(buf,p); it=[]
            for _ in range(cnt): x,p=s.read(p,dep+1); it.append(x)
            return ('H',it),p
        if tag==0x42:
            L,p=vlen(buf,p); return ('B',buf[p:p+L]),p+L
        if tag==0x43:   # CODE_OBJECT
            fl,p=vlen(buf,p)
            nm,p=s.zs(p)
            fsz,p=vlen(buf,p)
            return ('C',nm,fl,fsz),p+fsz
        raise ValueError('tag 0x%02x @%d'%(tag,p0))

def parse(body,size,cnt):
    buf=d[body:body+size-2]
    dec=Dec(buf); pos=0; out=[]
    for _ in range(cnt):
        try:
            v,pos=dec.read(pos)
        except Exception as ex:
            return out,('FAIL',len(out),pos,str(ex))
        out.append(v)
    return out,('OK',pos,len(buf))

if __name__=='__main__':
    import json
    res={}
    for name,body,size,cnt in [('src.security',0x1cce0af,223,11),
                               ('src.gui.main_window_controller',0x1cb1a44,49866,1513)]:
        o,st=parse(body,size,cnt)
        print('%-36s 解析 %4d/%-5d  status=%s'%(name,len(o),cnt,st))
        res[name]=o
    o=res['src.gui.main_window_controller']
    print()
    for i,v in enumerate(o):
        s=str(v)
        if '_verification_gate_allows' in s or '_emit_integrity_lock' in s or 'is_resource_initializing' in s:
            print('  [%4d] %s'%(i,s[:120]))
    json.dump({k:[str(x) for x in v] for k,v in res.items()},open('/tmp/nk/pools_decoded.json','w'),indent=1)
