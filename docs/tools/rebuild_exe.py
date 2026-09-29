#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rebuild_exe.py -- KeySteam v2.99 (Nuitka onefile + 单帧 zstd) 内嵌 payload 通用重打包器。

对 exe 内嵌 payload 打任意 FO 补丁，产出与原 exe 等长、可重新解析的副本。

外层布局（全部动态推导，无硬编码偏移）::

    [0, PS)                     PE 引导器
    [PS, PS+3)                  b"KAY"          Nuitka onefile 头（'Y' = zstd）
    [ZS, SE)                    zstd 单帧流      ZS = PS + 3
    [SE, BODY_END)              .rdata 尾部真实数据 / 对齐填充 / u64 尾指针
    [BODY_END, U64_OFF)         footer JSON      长度 = u64 字段值
    [U64_OFF, U64_OFF+8)        u64 LE = len(footer JSON)
    [U64_OFF+8, EOF)            b"KEYSTEAMTR1"

内层解压结果 raw（117 条目扁平表，entry 0 即 main.dll）::

    [0, 16)     utf-16le "main.dll"
    [16, 18)    u16 0 空名终止符
    [18, 26)    u64 LE = 31,088,128
    [26, ...)   main.dll 原始字节

    => raw 内偏移 = 26 + <main.dll 文件偏移 FO>      （ENTRY_HDR = 26）

硬约束
------
1. 原帧 `28 b5 2f fd 00 88`：FHD=0x00 => 无 checksum / 无 content_size，
   因此**必须**用 `decompressobj()` 流式解压；直接 `.decompress()` 会报
   "could not determine content size"。
2. 新 zstd 流长度必须 <= 原流长度。流后紧跟的是**真实 .rdata 数据**
   （IAT / import 名表 / load config），不是可覆盖填充。
3. 重压**必须**用一次性 `ZstdCompressor(level=22).compress()`。
   `stream_writer()` 分块刷块会丢失跨块长距离匹配，实测超出预算 6,996 B —— 已知死路。
4. 改 body 后只需重算 footer 的 `body_sha256`；Ed25519 `manifest_sig` 校验实测不阻断启动。

用法
----
    python3 rebuild_exe.py --src KeySteam.exe --out out.exe --patch 0xF93500:40:48
    python3 rebuild_exe.py --src KeySteam.exe --out out.exe \\
        --patch 0xF93500:4055535657415441:488B05319A4A00C3 \\
        --patch 0xF76420:4053555641544155:488B05116B4C00C3
    python3 rebuild_exe.py --src KeySteam.exe --patch 0xF93500:40:48 --dry-run

`--patch FO:ORIGHEX:NEWHEX`
    FO        main.dll 内文件偏移（支持 0x 前缀或十进制）
    ORIGHEX   期望在原处的字节（长度须与 NEWHEX 相等；`??` 表示该字节通配不校验）
    NEWHEX    写入的字节
补丁应用前**强制**逐字节校验原字节，不一致立即中止（exit 3），防止打错位置。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import sys
import time
from dataclasses import dataclass, field

try:
    import zstandard as zstd
except ImportError:  # pragma: no cover - 环境缺失时的明确提示
    sys.stderr.write("fatal: 缺少 zstandard 模块（pip install zstandard）\n")
    raise SystemExit(127)

MAGIC = b"KEYSTEAMTR1"
KAY = b"KAY"
ZSTD_MAGIC = bytes((0x28, 0xB5, 0x2F, 0xFD))
KAY_ZSTD = KAY + ZSTD_MAGIC
ENTRY_HDR = 26            # raw 内 main.dll 数据起点
COMPRESS_LEVEL = 22       # 一次性 compress 的固定级别
MAX_JSON_LEN = 1 << 20    # footer JSON 合理性上限
DIFF_CHUNK = 1 << 20

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_LAYOUT = 2
EXIT_PATCH_MISMATCH = 3
EXIT_OVERFLOW = 4
EXIT_VERIFY = 5
EXIT_JSON = 6


class Fail(Exception):
    def __init__(self, msg: str, code: int = EXIT_LAYOUT):
        super().__init__(msg)
        self.code = code


# --------------------------------------------------------------------------- 工具


def md5_hex(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def human(n: int) -> str:
    return f"{n:,}"


def diff_offsets(a: bytes, b: bytes, limit: int = 4096) -> tuple[list[int], int]:
    """返回 (不同的绝对偏移列表, 差别总数)。分块加速，避免 108MB 级别纯 Python 逐字节循环。"""
    if len(a) != len(b):
        raise Fail(f"长度不一致: {len(a)} vs {len(b)}")
    outs: list[int] = []
    total = 0
    for base in range(0, len(a), DIFF_CHUNK):
        end = min(base + DIFF_CHUNK, len(a))
        ca, cb = a[base:end], b[base:end]
        if ca == cb:
            continue
        for i in range(end - base):
            if ca[i] != cb[i]:
                total += 1
                if len(outs) < limit:
                    outs.append(base + i)
    return outs, total


def fmt_ranges(offsets: list[int]) -> list[str]:
    """把离散偏移压成区间字符串列表。"""
    spans: list[list[int]] = []
    for o in offsets:
        if spans and o == spans[-1][1] + 1:
            spans[-1][1] = o
        else:
            spans.append([o, o])
    return [f"{a:#x}" if a == b else f"{a:#x}-{b:#x}" for a, b in spans]


# --------------------------------------------------------------------------- 布局


@dataclass
class Layout:
    total: int
    ps: int                  # "KAY" 偏移
    zs: int                  # zstd 流起点
    se: int                  # zstd 流终点（动态推导）
    body_end: int            # footer JSON 起点 == 被 sha256 覆盖的 body 长度
    u64_off: int             # footer 长度字段偏移
    magic_off: int
    json_off: int
    json_len: int
    tail_u64_off: int        # 流尾 u64 指针字段（值 == 自身偏移 - ps）
    tail_u64_val: int
    json_obj: dict
    json_raw: bytes
    raw: bytes
    raw_sha_len: str
    e0_name: str
    e0_size: int
    e0_data: int

    @property
    def hole_len(self) -> int:
        """原 zstd 流长度（仅诊断用，不是预算）。"""
        return self.se - self.zs

    @property
    def gap_len(self) -> int:
        """流终点 → u64 尾指针之间的填充字节数。"""
        return self.tail_u64_off - self.se

    @property
    def budget(self) -> int:
        """新 zstd 流的真实可用预算 = [zs, tail_u64_off)。

        原文件本身在该区间尾部就留有成片零填充（实测 5420 B），解压器只认
        zstd 帧尾，帧后零字节被忽略；u64 尾指针标记的是**含填充**的 payload
        末界，因此只要新流不越过它，布局与原文件同构。
        """
        return self.tail_u64_off - self.zs

    def summary(self) -> dict:
        return {
            "total": self.total,
            "pe_loader": [0, self.ps],
            "kay": [self.ps, self.zs],
            "zstd_stream": [self.zs, self.se],
            "stream_len": self.hole_len,
            "post_stream_gap": self.tail_u64_off - self.se,
            "tail_u64": {"off": self.tail_u64_off, "value": self.tail_u64_val},
            "body": [0, self.body_end],
            "footer_json": [self.json_off, self.u64_off],
            "footer_u64_len": self.json_len,
            "magic_off": self.magic_off,
            "raw_len": len(self.raw),
            "entry0": {"name": self.e0_name, "size": self.e0_size, "data_off": self.e0_data},
            "footer": self.json_obj,
        }


def parse_footer(blob: bytes) -> tuple[int, int, int, int, dict, bytes]:
    if not blob.endswith(MAGIC):
        raise Fail(f"尾部缺少 {MAGIC!r} 魔数（该文件不是 KeySteam footer 格式）")
    magic_off = len(blob) - len(MAGIC)
    u64_off = magic_off - 8
    json_len = struct.unpack_from("<Q", blob, u64_off)[0]
    if not 0 < json_len <= MAX_JSON_LEN:
        raise Fail(f"footer 长度字段异常: {json_len}")
    json_off = u64_off - json_len
    if json_off <= 0:
        raise Fail("footer JSON 起点越界")
    raw_json = blob[json_off:u64_off]
    try:
        obj = json.loads(raw_json.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise Fail(f"footer JSON 解析失败: {exc}") from exc
    if not isinstance(obj, dict):
        raise Fail("footer JSON 顶层不是对象")
    return magic_off, u64_off, json_off, json_len, obj, raw_json


def locate_kay(blob: bytes) -> int:
    hits = []
    start = 0x100  # 跳过 DOS/PE 头，避免误命中
    while True:
        i = blob.find(KAY_ZSTD, start)
        if i < 0:
            break
        hits.append(i)
        start = i + 1
    if not hits:
        raise Fail('未找到 b"KAY" + zstd 魔数：该 exe 不是 zstd 压缩的 Nuitka onefile')
    if len(hits) > 1:
        raise Fail(f'b"KAY"+zstd 魔数命中 {len(hits)} 处（{ [hex(h) for h in hits] }），无法唯一确定 payload')
    return hits[0]


def decompress_payload(blob: bytes, zs: int, body_end: int) -> tuple[bytes, int]:
    """流式解压（原帧无 content_size），返回 (raw, 流真实终点)。"""
    dctx = zstd.ZstdDecompressor()
    chk = dctx.decompressobj()
    try:
        raw = chk.decompress(blob[zs:body_end])
    except zstd.ZstdError as exc:
        raise Fail(f"zstd 解压失败: {exc}") from exc
    if not chk.eof:
        raise Fail("zstd 流未正常结束（eof=False）：payload 被截断或布局推导有误")
    se = body_end - len(chk.unused_data)
    return raw, se


def find_tail_u64(blob: bytes, ps: int, se: int, body_end: int) -> tuple[int, int]:
    """定位流尾的 u64 指针字段。

    字段语义（Nuitka onefile）：值 == 自身偏移 - "KAY" 偏移，即标记 payload 区
    （含末尾对齐填充）的结束位置。它是**位置关系**，与压缩流实际字节数无关，
    因此在重压后流变短时该字段既不移位也不改值，只需保证其前方填充为零。

    搜索范围取 [se, body_end-8)：约束「8 字节对齐基准于 ps」且「值精确等于偏移差」
    同时成立，误命中概率 2^-64/位置，实测原文件唯一命中。
    """
    hits = []
    off = se
    while off + 8 <= body_end and off < body_end:
        if (off - ps) % 8 == 0:
            v = struct.unpack_from("<Q", blob, off)[0]
            if v == off - ps:
                hits.append((off, v))
        off += 1
    if not hits:
        raise Fail(f"未在 [{se:#x}, {body_end:#x}) 内找到 u64 尾指针（值 == 自身偏移 - KAY 偏移）")
    if len(hits) > 1:
        raise Fail(f"u64 尾指针命中 {len(hits)} 处，无法唯一确定: {[hex(h) for h, _ in hits]}")
    return hits[0]


def parse_entry0(raw: bytes) -> tuple[str, int, int]:
    i = 0
    while True:
        if i + 2 > len(raw):
            raise Fail("raw 头部未找到 utf-16le 空名终止符")
        if raw[i:i + 2] == b"\x00\x00":
            break
        i += 2
    name = raw[:i].decode("utf-16-le", "replace")
    size = struct.unpack_from("<Q", raw, i + 2)[0]
    data_off = i + 10
    return name, size, data_off


def locate(blob: bytes, label: str = "src") -> Layout:
    magic_off, u64_off, json_off, json_len, obj, raw_json = parse_footer(blob)
    body_end = json_off
    ps = locate_kay(blob)
    zs = ps + 3
    raw, se = decompress_payload(blob, zs, body_end)
    tail_off, tail_val = find_tail_u64(blob, ps, se, body_end)
    name, size, data_off = parse_entry0(raw)
    if data_off != ENTRY_HDR:
        raise Fail(f"entry 0 数据起点 {data_off:#x} != 期望 {ENTRY_HDR:#x}")
    if raw[data_off:data_off + 2] != b"MZ":
        raise Fail(f"raw[{data_off:#x}] 不是 MZ，条目表解析有误")
    lay = Layout(
        total=len(blob), ps=ps, zs=zs, se=se, body_end=body_end,
        u64_off=u64_off, magic_off=magic_off, json_off=json_off, json_len=json_len,
        tail_u64_off=tail_off, tail_u64_val=tail_val, json_obj=obj, json_raw=raw_json,
        raw=raw, raw_sha_len=sha256_hex(blob[:body_end]),
        e0_name=name, e0_size=size, e0_data=data_off,
    )
    selftest(lay, blob, label)
    return lay


def selftest(lay: Layout, blob: bytes, label: str) -> None:
    obj = lay.json_obj
    if "body_sha256" in obj and obj["body_sha256"] != lay.raw_sha_len:
        raise Fail(f"[{label}] footer body_sha256 与实际 body 不符 "
                   f"(footer={obj['body_sha256']} actual={lay.raw_sha_len})")
    if "body_size" in obj and int(obj["body_size"]) != lay.body_end:
        raise Fail(f"[{label}] footer body_size={obj['body_size']} != body_end={lay.body_end}")
    if lay.zs + lay.hole_len > lay.body_end:
        raise Fail(f"[{label}] 流终点越过 body 末尾")


# --------------------------------------------------------------------------- 补丁


@dataclass
class Patch:
    fo: int
    orig: bytes
    new: bytes
    mask: list[bool] = field(default_factory=list)
    raw_off: int = 0
    spec: str = ""

    @property
    def n(self) -> int:
        return len(self.new)


def parse_hexbytes(s: str) -> tuple[bytes, list[bool]]:
    t = re.sub(r"0x|[\s,_:.\-]", "", s)
    if not t:
        raise Fail("空字节串", EXIT_USAGE)
    if len(t) % 2:
        raise Fail(f"十六进制字节串长度必须为偶数: {s!r}", EXIT_USAGE)
    if not re.fullmatch(r"[0-9a-fA-F?]+", t):
        raise Fail(f"非法十六进制字节串: {s!r}", EXIT_USAGE)
    mask = [c == "?" for c in t[0::2]]
    return bytes.fromhex(t.replace("?", "0")), mask


def parse_patch_spec(spec: str) -> Patch:
    parts = spec.split(":")
    if len(parts) != 3:
        raise Fail(f"--patch 需要 FO:ORIGHEX:NEWHEX 三段，收到 {spec!r}", EXIT_USAGE)
    try:
        fo = int(parts[0], 0)
    except ValueError as exc:
        raise Fail(f"FO 解析失败: {parts[0]!r}", EXIT_USAGE) from exc
    if fo < 0:
        raise Fail(f"FO 不能为负: {fo}", EXIT_USAGE)
    orig, _ = parse_hexbytes(parts[1])
    new, _ = parse_hexbytes(parts[2])
    if len(orig) != len(new):
        raise Fail(f"原字节长度 {len(orig)} != 新字节长度 {len(new)}（{spec!r}）", EXIT_USAGE)
    mask = [c == "?" for c in re.sub(r"0x|[\s,_:.\-]", "", parts[1])[0::2]]
    return Patch(fo=fo, orig=orig, new=new, mask=mask, spec=spec)


def apply_patches(lay: Layout, patches: list[Patch]) -> tuple[bytes, list[dict]]:
    base = lay.e0_data
    limit = base + lay.e0_size
    ordered = sorted(patches, key=lambda p: p.fo)

    for p in ordered:
        p.raw_off = base + p.fo
        if p.raw_off + p.n > limit:
            raise Fail(
                f"补丁越界: FO {p.fo:#x} + {p.n} B 超过 {lay.e0_name} 末尾 "
                f"(FO 上限 {lay.e0_size - p.n:#x})", EXIT_PATCH_MISMATCH)

    for a, b in zip(ordered, ordered[1:]):
        if a.raw_off + a.n > b.raw_off:
            raise Fail(f"补丁区间重叠: {a.spec!r} 与 {b.spec!r}", EXIT_USAGE)

    work = bytearray(lay.raw)
    report = []
    for p in ordered:
        cur = bytes(work[p.raw_off:p.raw_off + p.n])
        bad = [i for i in range(p.n)
               if not p.mask[i] and cur[i] != p.orig[i]]
        if bad:
            detail = ", ".join(f"+{i:#04x}: 实际 {cur[i]:#04x} != 期望 {p.orig[i]:#04x}" for i in bad[:8])
            more = f"（共 {len(bad)} 字节不符）" if len(bad) > 8 else ""
            raise Fail(
                f"补丁原字节校验失败 @ FO {p.fo:#x}（raw {p.raw_off:#x}）: {detail}{more}\n"
                f"  实际: {cur.hex()}\n  期望: {p.orig.hex()}"
                + (f"\n  通配: {''.join('?' if m else '.' for m in p.mask)}" if any(p.mask) else ""),
                EXIT_PATCH_MISMATCH)
        if cur == p.new:
            state = "already-applied"
        else:
            work[p.raw_off:p.raw_off + p.n] = p.new
            state = "applied"
        report.append({
            "spec": p.spec, "fo": f"{p.fo:#x}", "raw_off": f"{p.raw_off:#x}",
            "len": p.n, "before": cur.hex(), "after": p.new.hex(), "state": state,
            "wildcard": any(p.mask),
        })
    return bytes(work), report


def build_expected(orig_raw: bytes, patches: list[Patch]) -> bytes:
    """把补丁施加到原始 raw 上，用于「除补丁区间外逐字节一致」的强校验。"""
    exp = bytearray(orig_raw)
    for p in patches:
        exp[p.raw_off:p.raw_off + p.n] = p.new
    return bytes(exp)


# --------------------------------------------------------------------------- footer


def rebuild_footer(lay: Layout, new_body_sha: str) -> tuple[bytes, dict]:
    obj = dict(lay.json_obj)
    before = dict(obj)
    changes = {}
    if "body_sha256" in obj:
        obj["body_sha256"] = new_body_sha
    if "body_size" in obj:
        obj["body_size"] = lay.body_end
    for k in ("body_sha256", "body_size"):
        if k in obj and obj[k] != before.get(k):
            changes[k] = {"from": before.get(k), "to": obj[k]}
    blob = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(blob) > lay.json_len:
        raise Fail(
            f"footer JSON 变长 {len(blob)} > 原 {lay.json_len}，无法原地容纳。"
            f"（多出的 {len(blob) - lay.json_len} B 需要重排 body 布局）", EXIT_JSON)
    padded = len(blob) != lay.json_len
    if padded:
        # 尾随空白对 JSON 合法，且 u64 长度字段会同步记录填充后的长度
        blob = blob + b" " * (lay.json_len - len(blob))
    json.loads(blob.decode("utf-8"))  # 自证可解析
    return blob, {"changed": changes, "padded": padded, "len": len(blob),
                  "before": before, "after": obj}


# --------------------------------------------------------------------------- 主流程


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="rebuild_exe.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="KeySteam v2.99 Nuitka onefile/zstd payload 重打包器（原 exe -> 等长可用副本）",
        epilog="示例:\n"
               "  rebuild_exe.py --src KeySteam.exe --out patched.exe --patch 0xF93500:40:48\n"
               "  rebuild_exe.py --src KeySteam.exe --patch 0xF93500:40:48 --dry-run\n",
    )
    ap.add_argument("--src", required=True, help="原始 exe 路径（只读）")
    ap.add_argument("--out", help="输出 exe 路径（--dry-run 时可省略）")
    ap.add_argument("--patch", action="append", default=[], metavar="FO:ORIGHEX:NEWHEX",
                    help="raw 偏移 = 26 + FO 处写入 NEWHEX；应用前校验原字节 == ORIGHEX（可重复）")
    ap.add_argument("--dry-run", action="store_true", help="只解析 + 字节校验 + 压缩预算，不写任何文件")
    ap.add_argument("--level", type=int, default=COMPRESS_LEVEL, help=f"zstd 级别（默认 {COMPRESS_LEVEL}）")
    ap.add_argument("--dump-raw", metavar="PATH", help="把改动前的解压 raw 写出（调试用）")
    ap.add_argument("--report-json", metavar="PATH", help="把完整报告同时写入 JSON 文件")
    args = ap.parse_args(argv)

    t0 = time.time()
    log = lambda *a: print(*a, flush=True)  # noqa: E731

    if not args.out and not args.dry_run:
        ap.error("未指定 --out（或加 --dry-run）")
    if args.dry_run and args.dump_raw:
        ap.error("--dry-run 与 --dump-raw 互斥（dry-run 不写任何文件）")

    blob = open(args.src, "rb").read()
    log(f"[1/7] 读入 {args.src}")
    log(f"      大小 {human(len(blob))} B · md5 {md5_hex(blob)}")

    lay = locate(blob, "src")
    log(f"[2/7] 布局解析 OK（全部动态推导）")
    log(f"      KAY          {lay.ps:#010x} → {lay.zs:#010x}")
    log(f"      zstd 流      {lay.zs:#010x} → {lay.se:#010x}  {human(lay.hole_len)} B")
    log(f"      尾部 u64 指针 {lay.tail_u64_off:#010x} = {lay.tail_u64_val} (= 自身偏移 - KAY 偏移)")
    log(f"      可写预算     [{lay.zs:#x}, {lay.tail_u64_off:#x}) = {human(lay.budget)} B"
        f"  (含原文件自带零填充 {human(lay.gap_len)} B)")
    log(f"      body         [0, {lay.body_end:#010x})  sha256 自校验 OK")
    log(f"      footer JSON  [{lay.json_off:#010x}, {lay.u64_off:#010x})  {lay.json_len} B")
    log(f"      魔数         {lay.magic_off:#010x} {MAGIC.decode()}")
    log(f"      解压 raw     {human(len(lay.raw))} B · entry0 {lay.e0_name!r} "
        f"size {human(lay.e0_size)} · 数据起点 {lay.e0_data:#x} (MZ ✔)")
    log(f"      footer 字段  {json.dumps(lay.json_obj, ensure_ascii=False)}")

    patches = [parse_patch_spec(s) for s in args.patch]
    log(f"[3/7] 补丁 {len(patches)} 条")
    new_raw, patch_report = apply_patches(lay, patches)
    for r in patch_report:
        log(f"      FO {r['fo']:>10} (raw {r['raw_off']:>10}) {r['len']}B "
            f"{r['before']} -> {r['after']}  [{r['state']}]")
    if not patches:
        log("      （无补丁，纯 round-trip）")
    if args.dump_raw:
        open(args.dump_raw, "wb").write(new_raw)
        log(f"      --dump-raw 已写出补丁后 raw → {args.dump_raw}")

    expected = build_expected(lay.raw, patches)
    if new_raw != expected:
        raise Fail("内部错误：补丁结果与期望不一致", EXIT_VERIFY)

    log(f"[4/7] 重压（一次性 compress, level={args.level}）...")
    t_c = time.time()
    comp = zstd.ZstdCompressor(level=args.level).compress(new_raw)
    dt = time.time() - t_c
    slack = lay.budget - len(comp)
    log(f"      新流 {human(len(comp))} B · 预算 {human(lay.budget)} B · "
        f"余量 {human(slack)} B ({slack / lay.budget * 100:+.2f}%) · 耗时 {dt:.1f}s")
    if len(comp) > lay.budget:
        raise Fail(
            f"zstd 超预算：新流 {len(comp)} B > 预算 {lay.budget} B，"
            f"超出 {len(comp) - lay.budget} B。\n"
            f"  预算终点是 u64 尾指针（标记含填充的 payload 末界），不得越过。\n"
            f"  可选项：① 改用更少的补丁字节；② 调 --level；"
            f"③ 对齐原始打包器所用 zstd 版本；④ 末位手段才是重排 .rdata 布局。",
            EXIT_OVERFLOW)

    if args.dry_run:
        log("[5/7] --dry-run：跳过写盘")
        log("[6/7] 跳过产物解析校验")
        log("[7/7] 跳过逐字节比对")
        log(f"      DRY-RUN OK（补丁落位、压缩预算均在范围内）· {time.time() - t0:.1f}s")
        return EXIT_OK

    log("[5/7] 重组 + 重算 footer（内存内完成，校验通过后才落盘）...")
    out = bytearray(blob)
    out[lay.zs:lay.tail_u64_off] = comp + b"\x00" * slack
    assert len(out) == len(blob), "长度漂移"
    out = bytes(out)
    new_body_sha = sha256_hex(out[:lay.body_end])
    json_blob, json_info = rebuild_footer(lay, new_body_sha)
    out = out[:lay.json_off] + json_blob + out[lay.u64_off:]
    assert len(out) == len(blob), "footer 变长导致长度漂移"
    log(f"      body_sha256 {lay.raw_sha_len[:16]}… → {new_body_sha[:16]}…")
    log(f"      footer 变更 {json.dumps(json_info['changed'], ensure_ascii=False) or '{}'}"
        + ("（JSON 尾部补空格对齐）" if json_info["padded"] else ""))

    log("[6/7] 从产物内存副本重新解析结构 ...")
    lay2 = locate(out, "out")
    structural = [
        ("总长", lay.total == lay2.total, f"{lay.total} vs {lay2.total}"),
        ("KAY 偏移", lay.ps == lay2.ps, f"{lay.ps:#x} vs {lay2.ps:#x}"),
        ("body 末尾", lay.body_end == lay2.body_end, f"{lay.body_end:#x} vs {lay2.body_end:#x}"),
        ("footer JSON 长度", lay.json_len == lay2.json_len, f"{lay.json_len} vs {lay2.json_len}"),
        ("raw 长度", len(lay.raw) == len(lay2.raw), f"{len(lay.raw)} vs {len(lay2.raw)}"),
        ("entry0 名称", lay.e0_name == lay2.e0_name, f"{lay.e0_name!r} vs {lay2.e0_name!r}"),
        ("entry0 大小", lay.e0_size == lay2.e0_size, f"{lay.e0_size} vs {lay2.e0_size}"),
        ("entry0 数据起点", lay.e0_data == lay2.e0_data, f"{lay.e0_data:#x} vs {lay2.e0_data:#x}"),
        ("尾部 u64 指针", lay.tail_u64_off == lay2.tail_u64_off and lay.tail_u64_val == lay2.tail_u64_val,
         f"{lay.tail_u64_val} vs {lay2.tail_u64_val}"),
        ("footer build_id/version", lay2.json_obj.get("build_id") == lay.json_obj.get("build_id")
         and lay2.json_obj.get("version") == lay.json_obj.get("version"),
         f"{lay2.json_obj.get('build_id')} / {lay2.json_obj.get('version')}"),
        ("footer manifest_sig 原样保留", lay2.json_obj.get("manifest_sig") == lay.json_obj.get("manifest_sig"),
         "unchanged" if lay2.json_obj.get("manifest_sig") == lay.json_obj.get("manifest_sig") else "CHANGED"),
    ]
    for k, ok, v in structural:
        log(f"      {'OK  ' if ok else 'FAIL'} {k}: {v}")
    if not all(ok for _, ok, _ in structural):
        raise Fail("产物结构复检失败（未写盘）", EXIT_VERIFY)

    log("[7/7] 逐字节比对 ...")
    d_new, n_new = diff_offsets(lay2.raw, new_raw)
    log(f"      产物 raw vs 期望 raw（原始 raw + 补丁）: 差异 {n_new} 字节"
        + (f" @ {', '.join(fmt_ranges(d_new)[:8])}" if n_new else "  ← 完全一致 ✔"))
    if n_new:
        raise Fail(f"产物 raw 与期望不符，差异 {n_new} 字节", EXIT_VERIFY)

    d_orig, n_orig = diff_offsets(lay2.raw, lay.raw)
    allowed: list[tuple[int, int]] = []
    for p in patches:
        allowed.append((p.raw_off, p.raw_off + p.n))
    outside = [o for o in _all_offsets(lay2.raw, lay.raw, allowed)]
    for p in patches:
        got = lay2.raw[p.raw_off:p.raw_off + p.n]
        log(f"      补丁落位 FO {p.fo:#x} (raw {p.raw_off:#x}) = {got.hex()} "
            f"{'✔' if got == p.new else '✘ (期望 ' + p.new.hex() + ')'}")
    log(f"      产物 raw vs 原始 raw: 差异 {n_orig} 字节，全部位于补丁区间内: "
        f"{'✔ 是' if not outside else '✘ 否 -> ' + str(outside[:8])}")
    if outside:
        raise Fail(f"存在补丁区间外的字节漂移: {outside[:16]}", EXIT_VERIFY)

    peak = max(p.raw_off + p.n for p in patches) if patches else 0
    first = min(p.raw_off for p in patches) if patches else 0

    # 全部校验通过，原子落盘
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    tmp = args.out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(out)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, args.out)
    log(f"      写出 {args.out} · {human(len(out))} B · md5 {md5_hex(out)}")

    report = {
        "ok": True,
        "dry_run": False,
        "src": {"path": args.src, "size": lay.total, "md5": md5_hex(blob)},
        "out": {"path": args.out, "size": len(out), "md5": md5_hex(out)},
        "sizes_equal": lay.total == len(out),
        "layout": lay.summary(),
        "zstd": {
            "level": args.level,
            "orig_stream_len": lay.hole_len,
            "new_stream_len": len(comp),
            "slack": slack,
            "slack_pct": round(slack / lay.hole_len * 100, 4),
            "compress_seconds": round(dt, 1),
            "one_shot_compress": True,
        },
        "patches": patch_report,
        "patch_span": {"first_raw_off": first, "last_raw_off_end": peak} if patches else None,
        "footer": json_info,
        "footer_after": lay2.json_obj,
        "raw_sha_before": lay.raw_sha_len,
        "raw_sha_after": lay2.raw_sha_len,
        "verify": {
            "reparsed": True,
            "raw_matches_expected": True,
            "diff_outside_patches": 0,
            "diff_total_vs_orig": n_orig,
        },
        "elapsed_seconds": round(time.time() - t0, 1),
    }
    log("")
    log(json.dumps(report, indent=2, ensure_ascii=False))
    if args.report_json:
        with open(args.report_json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
    log(f"ALL CHECKS PASSED · {time.time() - t0:.1f}s")
    return EXIT_OK


def _all_offsets(a: bytes, b: bytes, allowed: list[tuple[int, int]]):
    """产出所有差异偏移，过滤掉落在补丁区间内的（用于「区间外零漂移」断言）。"""
    offs, _ = diff_offsets(a, b, limit=len(b))
    for o in offs:
        if not any(lo <= o < hi for lo, hi in allowed):
            yield o


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Fail as e:
        sys.stderr.write(f"\nfatal: {e}\n")
        raise SystemExit(e.code)
    except KeyboardInterrupt:
        sys.stderr.write("\ninterrupted\n")
        raise SystemExit(130)
