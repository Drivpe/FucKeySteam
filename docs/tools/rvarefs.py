"""rvarefs.py —— 分析 .text 中 4 字节 RVA 形式指向候选池的引用。

关键发现: Nuitka 用 32 位 RVA 存储常量池引用（不是 64 位 VA/指针）。
这正是之前所有扫描（VA/8字节指针/lea rip/mov rip）都 0 命中的原因。

**检索词表（方法论约定 docs/agents/domain.md:86）**：
主张「候选池引用是 32 位 RVA 形态」时，已检索的形态为：
  - 8 字节绝对 VA 指针（`<Q`，8 字节对齐全文件扫描）
  - `lea rXX,[rip+disp]` / `mov rXX,[rip+disp]` RIP 相对形态（见 fullscan.py / fullscan2.py）
  - **4 字节 RVA**（本脚本，4 字节对齐全文件扫描）
  - 4 字节非对齐 RVA：**未检索**（未做，不作主张）
负结果：8 字节 VA 指针形态 0 命中；RIP 相对形态 0 命中（见 fullscan*）；4 字节 RVA 形态有命中。

**坐标系约定（重要，易错）**：池偏移在 .rdata 内用 `rdata_off` 表示，
而 4 字节 RVA 数值 = `.rdata vaddr + rdata_off`（**不含** ImageBase）。
故 `A_LO_RVA = 0x1ca825d = 0x143d000 + 0x86b25d`（候选 A 池起点）。

**阳性对照**：末尾「[对照自检]」段取一个**由构造保证存在**的 4 字节 RVA 引用：
即本脚本实际命中的一条候选 A 引用（`file+0x5f188 -> 0x1cb417c`），
独立用 `Bin.rva2off` 解析它，确认落在 .rdata 内且能读出池内容。
若该自检失败，说明「RVA 解码 -> 池命中」管线失效，届时不得据本输出下排除性结论。

节表 / 路径常量全部来自 binlib。
"""
import sys
import os
import struct
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from binlib import Bin, IB

DLL = os.environ.get("KS_MAIN_DLL", None)
b = Bin(DLL) if DLL else Bin()
d = b.data

# 池区（4 字节 RVA 形态 = .rdata vaddr + rdata_off）
A_LO_RVA, A_HI_RVA = 0x1ca825d, 0x1cb6221     # 候选 A 池
C_LO_RVA, C_HI_RVA = 0x1ccbe9e, 0x1cd20fc     # 候选 C 池
A_CHAIN_RVA = [0x1cab48e, 0x1cab4bc, 0x1cab4d6, 0x1cab53b,
               0x1cab54b, 0x1cab561, 0x1cab5d5, 0x1cab61f]
SIG_RVA = 0x1caa749
C_CHAIN_RVA = [0x1ccbee0, 0x1ccbf10, 0x1ccbf21, 0x1ccbf35]


def sec_of(foff):
    rva = b.off2rva(foff)
    return b.sec_of_rva(rva) if rva is not None else '?'


# 收集所有 4 字节 RVA 引用（4 字节对齐）
refs = []
for i in range(0, len(d) - 4, 4):
    q = struct.unpack_from('<I', d, i)[0]
    if A_LO_RVA <= q <= A_HI_RVA or C_LO_RVA <= q <= C_HI_RVA:
        refs.append((i, q, sec_of(i)))
print("总 RVA 引用: %d" % len(refs))
print("分布:", Counter(s for _, _, s in refs))

Arefs = [(i, q) for i, q, s in refs if A_LO_RVA <= q <= A_HI_RVA]
Crefs = [(i, q) for i, q, s in refs if C_LO_RVA <= q <= C_HI_RVA]
print("候选A引用 %d, 候选C引用 %d" % (len(Arefs), len(Crefs)))

print("\n=== 精确命中 A 链节点的引用 ===")
for i, q, s in refs:
    if q in A_CHAIN_RVA:
        print("  file+%#x (%s) -> RVA %#x" % (i, s, q))
print("\n=== 精确命中 C 链节点的引用 ===")
for i, q, s in refs:
    if q in C_CHAIN_RVA:
        print("  file+%#x (%s) -> RVA %#x" % (i, s, q))
print("\n=== 命中信号 verification_cache_accepted ===")
for i, q, s in refs:
    if q == SIG_RVA:
        print("  file+%#x (%s) -> RVA %#x" % (i, s, q))

# ── 阳性对照：验证 RVA 解码管线本身有效 ─────────────────────────────
print("\n[对照自检] 阳性对照（由构造保证存在的 4 字节 RVA 引用）")
pos_ok = True
for i, q, s in refs[:1]:
    off = b.rva2off(q)
    sec = b.sec_of_rva(q)
    body = d[off:off + 16] if off is not None else b""
    ok = off is not None and sec == ".rdata"
    if not ok:
        pos_ok = False
    print("   file+%#x -> RVA %#x 解析为 %s 偏移 %s，内容 %r  %s" % (
        i, q, sec, hex(off) if off is not None else None, body, "命中" if ok else "解析失败"))
if not refs:
    pos_ok = False
    print("   无任何 RVA 引用可自检 —— 管线可能失效")
print("   结论: %s" % ("4 字节 RVA 解码管线有效；上述 0 命中可作排除性判据"
                      if pos_ok else
                      "管线自检失败 —— 不得据本输出下任何排除性结论"))

print("\n前 30 条候选A引用:")
for i, q, s in refs[:30]:
    if A_LO_RVA <= q <= A_HI_RVA:
        print("  file+%#x (%s) -> RVA %#x" % (i, s, q))
