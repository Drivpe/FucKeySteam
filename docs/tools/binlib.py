"""binlib.py —— main.dll 二进制元数据的唯一来源（共享模块）。

存在理由（#15 审查发现）：此前节表解析、.pdata 解析、RIP 相对扫描、
三组路径常量在 17 个工具里各抄一遍 —— 改一个偏移要动 17+ 处（Shotgun Surgery）。

本模块集中这四件事，并**实时从 DLL 解析**，不依赖 /tmp 节转储（/tmp 重启即丢）。

用法：
    from binlib import Bin
    b = Bin()                     # 默认取仓库内 payload/main.dll
    b = Bin(r'D:\\path\\main.dll')
    print(b.sections)             # {name: (vaddr, rawptr, rawsize, vsize)}
    for s, e in b.funcs: ...      # .pdata 函数边界（静态 VA）
    for ins in b.disasm_text(): ...   # 分段反汇编（按 .pdata 边界）
"""
import struct
import capstone

# ── 路径常量（审查发现三组路径总是结伴出现却无集中定义）────────────────
# 可用环境变量覆盖，便于换机 / 换样本
import os
DEFAULT_DLL = os.environ.get(
    "KS_MAIN_DLL",
    r"/mnt/d/03_Work/03_Develop/KeySteam v2.99/_re/work/payload/main.dll")
DEFAULT_WRAPPER = os.environ.get("KS_WRAPPER", r"D:\ks_debug\kshost.exe")
DEFAULT_HEADLESS = os.environ.get(
    "KS_HEADLESS",
    r"D:\03_Work\03_Develop\snapshot_2026-05-27_12-11\release\x64\headless.exe")

# 调试器脚本侧使用的 Windows 形态路径（与上面的 Linux 侧默认值同源不同表示）。
# disc.py / bp3.py 等脚本按原样传给 CreateProcessW，**不要**改成 Linux 路径。
WIN_DLL = os.environ.get(
    "KS_WIN_MAIN_DLL",
    r"D:\03_Work\03_Develop\KeySteam v2.99\_re\work\payload\main.dll")
WIN_WRAPPER = DEFAULT_WRAPPER
WIN_CWD = os.environ.get("KS_WIN_CWD", r"D:\ks_debug")
WIN_LOG_DIR = os.environ.get(
    "KS_WIN_LOG_DIR",
    r"D:\03_Work\03_Develop\KeySteam v2.99\_re\ghidra")

IB = 0x180000000          # 本样本 ImageBase
PD_RAW, PD_SZ = 0x1d5a800, 214528   # .pdata 文件偏移与大小
                                  # 改这一个偏移即可，17 个工具的 .pdata 解析全部随之更新

# ── 节表四元组曾经在 ksdis/modconsts/rvarefs/candidateA/fullscan2 五份副本 ──
# 现在由 Bin.sections 实时解析（见 _parse_sections）。下列 RAW 常量仅供
# 需要文件偏移而非 VA 的脚本（如按 raw 切 .text/.rdata）使用，仍是唯一来源。
TX_RAW = 0x400            # .text 文件偏移
RD_RAW = 0x143b800        # .rdata 文件偏移
RD_SZ = 0x910000          # .rdata 大小（9504256 = 0x910000）
DA_RAW = 0x1d4be00        # .data 文件偏移
DA_SZ = 59904             # .data rawsize（文件内可见部分；vsize 647296 含 .bss 式未初始化区）
DA_VSZ = 647296           # .data 虚拟大小
DA_RVA = 0x1d4e000        # .data RVA

# .data 的「未初始化区」即 BSS 式区间 —— mod_consts 结构体所在。
BSS_LO = IB + DA_RVA + DA_SZ
BSS_HI = IB + DA_RVA + DA_VSZ

# 模块描述符表与初始化器（Nuitka 常量池装配链的两个固定锚点）
DESC_TBL_RVA = 0x1d52cf0   # 模块描述符表（.data），每项 0x20
ENTRY_SZ = 0x20
INIT_FN = IB + 0x1433f90   # 模块初始化器：lea rdx,[rip+mod_consts] ; call 它

TEXT_VA_END = IB + 0x143c2d8   # .text 有效代码上界（5 个脚本里各写一遍）
TEXT_LO = IB + 0x1000


class Bin:
    """main.dll 的节表 / .pdata / 反汇编 访问器。"""

    def __init__(self, path=DEFAULT_DLL):
        self.path = path
        self.data = open(path, "rb").read()
        self.sections = self._parse_sections()
        self.funcs = self._parse_functions()

    # ── 节表 ────────────────────────────────────────────────────────
    def _parse_sections(self):
        d = self.data
        e = struct.unpack_from("<I", d, 0x3C)[0]
        nsec = struct.unpack_from("<H", d, e + 6)[0]
        opt = e + 24
        sizeopt = struct.unpack_from("<H", d, e + 20)[0]
        secs = opt + sizeopt
        out = {}
        for i in range(nsec):
            o = secs + i * 40
            name = d[o:o + 8].rstrip(b"\0").decode("ascii", "replace")
            vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", d, o + 8)
            out[name] = (vaddr, rawptr, rawsize, vsize)
        return out

    # ── .pdata 函数边界 ─────────────────────────────────────────────
    def _parse_functions(self):
        pd = self.data[PD_RAW:PD_RAW + PD_SZ]
        out = []
        for i in range(len(pd) // 12):
            s, e, _u = struct.unpack_from("<III", pd, i * 12)
            if s == 0:
                break
            out.append((IB + s, IB + e))
        return out

    # ── 地址换算 ────────────────────────────────────────────────────
    def rva2off(self, rva):
        for _n, (v, r, sz, _vs) in self.sections.items():
            if v <= rva < v + sz:
                return r + (rva - v)
        return None

    def off2rva(self, off):
        for _n, (v, r, sz, _vs) in self.sections.items():
            if r <= off < r + sz:
                return v + (off - r)
        return None

    def va2off(self, va):
        return self.rva2off(va - IB)

    def sec_of_rva(self, rva):
        for n, (v, _r, sz, _vs) in self.sections.items():
            if v <= rva < v + sz:
                return n
        return None

    # ── 反汇编 ──────────────────────────────────────────────────────
    def text_range(self):
        v, _r, sz, _vs = self.sections[".text"]
        return IB + v, sz

    def disasm_text(self):
        """按 .pdata 函数边界**分段**反汇编全 .text。

        为何分段：capstone 线性扫描从 .text 开头只覆盖 7.5%
        （在 0x18018458b 处遇数据区停止）。按函数边界逐段扫才完整。
        产出 (insn)。调用方自行过滤。
        """
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        md.detail = True
        tx_va, tx_sz = self.text_range()
        d = self.data
        for s, e in self.funcs:
            if not (tx_va <= s < tx_va + tx_sz):
                continue
            off = self.rva2off(s - IB)
            ln = min(e - s, tx_sz - (s - tx_va))
            try:
                for ins in md.disasm(d[off:off + ln], s):
                    yield ins
            except Exception:
                continue

    def disasm(self, va, count=40):
        """单点反汇编，返回指令列表。"""
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        md.detail = True
        off = self.va2off(va)
        if off is None:
            return []
        out = []
        for ins in md.disasm(self.data[off:off + count * 16], va):
            out.append(ins)
            if len(out) >= count:
                break
        return out

    # ── capstone 实例 ───────────────────────────────────────────────
    @staticmethod
    def _md():
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        md.detail = True
        return md

    # ── RIP 相对目标 ────────────────────────────────────────────────
    @staticmethod
    def rip_target(ins):
        """若该指令有 RIP 相对内存操作数，返回目标 VA；否则 None。

        这是全目录唯一的 RIP 相对判定实现。此前
        `op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP` 在 15 个文件里逐字重复。
        """
        for op in ins.operands:
            if (op.type == capstone.x86.X86_OP_MEM
                    and op.mem.base == capstone.x86.X86_REG_RIP):
                return ins.address + ins.size + op.mem.disp
        return None

    # ── 按 .pdata 函数边界逐段反汇编（带指令索引）────────────────────
    def iter_funcs(self, va_lo=None, va_hi=None):
        """产出 (func_start, func_end, [(idx, insn), ...])。

        收口了 8 个脚本里逐字重复的「函数边界过滤 + 偏移换算 + try/except
        反汇编」三连。调用方在本函数内做二次过滤（lea / call / mov）。
        va_lo/va_hi 默认取 .text 有效区间。
        """
        if va_lo is None:
            va_lo = TEXT_LO
        if va_hi is None:
            va_hi = TEXT_VA_END
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
        md.detail = True
        d = self.data
        for s, e in self.funcs:
            if not (va_lo <= s < va_hi):
                continue
            off = self.rva2off(s - IB)
            if off is None:
                continue
            ln = min(e - s, 0x2000000)
            try:
                insns = list(md.disasm(d[off:off + ln], s))
            except Exception:
                continue
            yield s, e, list(enumerate(insns))

    def rip_refs(self, va_lo=None, va_hi=None, mnemonics=None):
        """产出 (insn_addr, target_va, mnemonic, op_str, func_start)。

        全目录唯一的「分段扫 RIP 相对引用」实现。mnemonics 为 None 时不过滤。
        """
        for s, _e, insns in self.iter_funcs(va_lo, va_hi):
            for _i, ins in insns:
                if mnemonics and ins.mnemonic not in mnemonics:
                    continue
                t = Bin.rip_target(ins)
                if t is not None:
                    yield ins.address, t, ins.mnemonic, ins.op_str, s

    def calls_to(self, target_va, va_lo=None, va_hi=None):
        """产出 (func_start, [指令索引]) —— 函数内调用 target_va 的位置。

        收口 find_consumers/locate_mw_mc/locate_mw2/candidateA 里同一段
        `calls={i for i,ins in ...}` 集合推导。
        """
        for s, _e, insns in self.iter_funcs(va_lo, va_hi):
            idxs = [i for i, ins in insns
                    if ins.mnemonic == "call" and ins.operands
                    and ins.operands[0].type == capstone.x86.X86_OP_IMM
                    and ins.operands[0].imm == target_va]
            if idxs:
                yield s, idxs

    # ── 字符串读取 ──────────────────────────────────────────────────
    def cstr(self, va, maxlen=96):
        off = self.va2off(va)
        if off is None:
            return None
        chunk = self.data[off:off + maxlen]
        return chunk.split(b"\0")[0]

    def readable(self, b, minlen=3):
        """粗略判断字节串是否像可读文本（含 UTF-8 中文）。"""
        if not b or len(b) < minlen:
            return False
        return all(32 <= c < 127 or c >= 0x80 for c in b[:min(24, len(b))])

    # ── 常量池 blob 顺序解析 ────────────────────────────────────────
    # find_mw.py / map_slots.py 各抄一份 tag 规则，现收口于此。
    # 依子代理 constants_blob_spec.h: tag 紧跟内容；字符串以 \0 结尾。
    # 已知样本 tag: 0x61('a' 标识符) 0x75('u' 文本) 0x54('T' 类型) 0x45('E' 异常)
    POOL_STR_TAGS = (0x61, 0x75, 0x45)
    POOL_T_BODY = (0x01, 0x02, 0x03)
    POOL_FIXED_TAGS = (0x73, 0x6c, 0x69, 0x66, 0x64, 0x4c, 0x50,
                       0x44, 0x43, 0x77, 0xe7)

    def parse_pool(self, pool_off, size, entries):
        """顺序解析常量池 blob，返回 [(序号 n, 池内偏移, tag, 内容字节)]。

        pool_off 是 .rdata 内偏移（rdata_off），不是 VA。
        条目序号 n 即槽号：槽地址 = mod_consts + 8*n。
        """
        rd = self.data[RD_RAW:RD_RAW + RD_SZ]
        p = pool_off
        end = pool_off + size
        out = []
        n = 0
        while p < end and n < entries:
            tag = rd[p]
            p += 1
            if tag in self.POOL_STR_TAGS:
                z = rd.find(b"\0", p, end)
                if z < 0:
                    break
                s = rd[p:z]
                p = z + 1
                out.append((n, p - len(s) - 2, tag, s))
            elif tag == 0x54:
                sub = rd[p]
                p += 1
                if sub in self.POOL_T_BODY:
                    z = rd.find(b"\0", p, end)
                    if z < 0:
                        break
                    s = rd[p:z]
                    p = z + 1
                    out.append((n, p - len(s) - 3, tag, s))
                else:
                    out.append((n, p - 1, tag, b"<%02x>" % sub))
            else:
                out.append((n, p, tag, b"<%02x>" % tag))
            n += 1
        return out
