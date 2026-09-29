#!/usr/bin/env python3
"""KeySteam v2.99 exe 内嵌 payload 改造器。

Nuitka onefile (无 archive, zstd 整体压缩) 布局:
  [0, 0x235B0)            PE 引导器
  [0x235B0, 0x235B3)      b"KAY"
  [0x235B3, 0x1D4C4E2)    zstd 单帧流 (30,576,431 B 的洞)
  [0x1D4C4E2, 0x1D4C4E8)  对齐填充
  [0x1D4C4E8, 0x1D4C4F0)  u64 LE = 该字段文件偏移 - 0x235B0
  [0x1D4C4F0, 0x1D74400)  0 填充
  [0x1D74400, 0x1D74507)  footer JSON (255 B)
  [0x1D74507, 0x1D74512)  b"KEYSTEAMTR1"

约束: 新 zstd 流必须 <= 30,576,431 字节（0x1D4C4F0 之后是不可覆盖的真实 .rdata）。
      用 ZstdCompressor(level=22).compress() 一次性压缩，实测 30,571,041（余量 5,390）。
      stream_writer() 会因分块丢失上下文而超预算 6,996 字节 —— 不要用。
"""
import hashlib, json, struct, sys, zstandard as zstd

SRC  = sys.argv[1] if len(sys.argv) > 1 else '/mnt/d/03_Work/03_Develop/KeySteam v2.99/KeySteam.exe'
DST  = sys.argv[2] if len(sys.argv) > 2 else '/mnt/d/ks_debug/KeySteam_patched.exe'

PS, ZS, END = 0x235B0, 0x235B3, 0x1D4C4E2
SL   = END - ZS                 # 30,576,431  洞大小
BODY = 0x1D74400                # body 结束 = footer 开始
SHA_OFF, SHA_LEN = 0x1D74410, 64
ENTRY_HDR = 26                  # raw 中第一项 "main.dll" 名字字段长度
MAIN_SIZE = 31088128

# 8 字节桩: mov rax,[rip+disp] -> &_Py_NoneStruct ; ret   恒返回 None
NONE_VA  = 0x18143DB38          # .data 内 _Py_NoneStruct 指针槽
IMAGE_VA = 0x180000000
PATCHES = [
    (0xf94100, 'MainWindow._check_cached_verification'),   # RVA -> 去「KeySteam 验证」弹窗
    (0xf77020, 'MainWindow.show_tamper_warning'),          # RVA -> 去「倒卖可耻」篡改警告
]
EXPECT = {0xf94100: bytes.fromhex('4055535657415441'),
          0xf77020: bytes.fromhex('4053555641544155')}


def rva_to_fo(md, rva):
    e = struct.unpack_from('<I', md, 0x3c)[0]
    nsec = struct.unpack_from('<H', md, e + 6)[0]
    opt  = struct.unpack_from('<H', md, e + 20)[0]
    o = e + 24 + opt
    for _ in range(nsec):
        nm = md[o:o+8].rstrip(b'\0').decode()
        vs, va, rs, ra = struct.unpack_from('<IIII', md, o + 8)
        if va <= rva < va + max(vs, rs):
            return ra + (rva - va)
        o += 40
    raise ValueError('rva %#x not in any section' % rva)


def make_stub(rva):
    va = IMAGE_VA + rva
    disp = (NONE_VA - (va + 7)) & 0xFFFFFFFF
    return bytes([0x48, 0x8B, 0x05]) + disp.to_bytes(4, 'little') + bytes([0xC3])


def main():
    d = open(SRC, 'rb').read()
    assert d[PS:PS+3] == b'KAY', 'not a Nuitka onefile KAY payload'
    # 原帧 FHD=0x00 无 content_size，必须流式解压
    raw = zstd.ZstdDecompressor().decompressobj().decompress(d[ZS:END])
    assert len(raw) == 108502413, len(raw)

    md_off = ENTRY_HDR
    assert raw[md_off:md_off+2] == b'MZ'
    md0 = raw[md_off:md_off+MAIN_SIZE]
    base_md5 = hashlib.md5(md0).hexdigest()

    work = bytearray(raw)
    applied = []
    for rva, name in PATCHES:
        fo = rva_to_fo(bytes(md0), rva)
        cur = bytes(work[md_off+fo: md_off+fo+8])
        stub = make_stub(rva)
        if cur == stub:
            applied.append((name, hex(fo), 'already'))
            continue
        exp = EXPECT.get(rva)
        if exp and cur[:len(exp)] != exp:
            raise SystemExit('%s: unexpected bytes %s (want prefix %s)'
                             % (name, cur.hex(), exp.hex()))
        work[md_off+fo: md_off+fo+8] = stub
        applied.append((name, hex(fo), stub.hex()))
    new_raw = bytes(work)

    z = zstd.ZstdCompressor(level=22).compress(new_raw)   # 必须一次性
    if len(z) > SL:
        raise SystemExit('zstd overflow: %d > %d (slack %d)' % (len(z), SL, SL - len(z)))

    out = bytearray(d[:ZS] + z + b'\x00' * (SL - len(z)) + d[END:])
    assert len(out) == len(d), 'length drift'

    new_sha = hashlib.sha256(bytes(out[:BODY])).hexdigest()
    # 只重写 body_sha256；body_size / manifest_sig 保持原值（签名不可伪造，见报告）
    out[SHA_OFF:SHA_OFF+SHA_LEN] = new_sha.encode()
    data = bytes(out)
    open(DST, 'wb').write(data)

    # ---- 自校验：从产物重新解包 ----
    chk = zstd.ZstdDecompressor().decompressobj()
    got = chk.decompress(data[ZS:ZS+SL])
    assert chk.eof, 'patched stream did not terminate'
    got_md5 = hashlib.md5(got[md_off:md_off+MAIN_SIZE]).hexdigest()
    report = {
        'src': SRC, 'dst': DST, 'src_md5': hashlib.md5(d).hexdigest(),
        'dst_md5': hashlib.md5(data).hexdigest(), 'size': len(data),
        'stream_len': len(z), 'slack': SL - len(z),
        'body_sha256': new_sha, 'main_dll_md5_baseline': base_md5,
        'main_dll_md5_patched': got_md5, 'zstd_eof': bool(chk.eof),
        'patches': applied,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    # 产物自校验：解出的 main.dll 必须逐位等于我们写进去的内容
    assert got == new_raw, 'roundtrip mismatch'
    # 两处桩必须在位
    mdg = got[md_off:md_off+MAIN_SIZE]
    for rva, name in PATCHES:
        fo = rva_to_fo(mdg, rva)
        assert mdg[fo:fo+8] == make_stub(rva), name
    print('SELF-CHECK OK: roundtrip byte-identical, %d stub(s) verified' % len(PATCHES))


if __name__ == '__main__':
    main()
