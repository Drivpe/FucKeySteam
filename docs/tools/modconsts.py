"""modconsts.py —— 策略B: 用候选C池的 351 个条目做约束打分, 定位 mod_consts 基址。

原理(子代理一手来源确证):
  mod_consts 是匿名 struct 全局变量, 成员按常量序号排列: mod_consts + 8*n = 第 n 个常量的 PyObject*
  故: 对每个 .data 候选基址 X, 若 mod_consts 在 X, 则 X+8*n 的所有槽在代码里会被
      "先写入(初始化)后读取"。
  更强约束: 池内 entries=351 条 -> 结构体至少 351*8 = 2808 字节,
      且其**首地址必须是 lea 的目标**(createModuleConstants 里 lea rdx,[rip+mod_consts])。
  做法: 枚举 .text 里所有 lea reg,[rip+disp] 且目标落在 .data, 得到候选基址集合;
        再用 .data 的写引用(xref)密度与 8 字节对齐性打分。

**[复核记录 2026-09-17 —— 本脚本的定位法已被阳性对照否证，保留作负结果凭据]**
原 docstring 承认「零槽法打分无阴性对照」。补上阳性对照后结论如下：

  1. **真值不在候选集合中。** `verification_dialog` 的 mod_consts = `0x181dd16a0`，
     其 `.data` 内偏移 = `0x836a0` = 538784 > `rawsize=59904` —— 落在
     **BSS 未初始化段**。而本脚本的零槽打分只读
     `d[DA_RAW:DA_RAW+DA_SZ]`（文件内可见的 59904 字节），
     **结构上不可能覆盖真值**。所以「零槽数 > 300 的候选: 0」是**方法的盲区**，
     不是「样本中没有」。这正是 docs/agents/domain.md:86 那条约定的实例。
  2. **零槽法本身也缺少区分力。** 前 15 名零槽数在 143~276 之间单调递减，
     却没有一个达到 351 —— 说明打分梯度来自 `.data` 头部那几个连续零块，
     与 mod_consts 无关。

  **结论：本脚本不得用于定位或排除。** 正确定位路径是
  `bss_scan.py` → `find_consumers.py` → `find_init.py`（扫 BSS 引用而非 .data 文件区），
  最终由 `rederive.py` 的「描述符表 + 池条目数间隔」给出唯一真值。
  保留本文件是为记录这次负结果（符合票据「死代码归档不删」的要求）。

**检索词表（docs/agents/domain.md:86）**：本脚本检索的是 `lea` 的 RIP 相对操作数，
目标落在 `.data` **文件可见区** `[DA_VA, DA_VA+DA_SZ)`。
**未检索**：BSS 未初始化区 `[DA_VA+DA_SZ, DA_VA+DA_VSZ)` —— 见上面第 1 条。

节表 / RIP 相对判定 / 路径常量全部来自 binlib。
"""
import sys
import os
import struct
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from binlib import Bin, IB, DA_RVA, DA_RAW, DA_SZ, DA_VSZ

DLL = os.environ.get("KS_MAIN_DLL", None)
b = Bin(DLL) if DLL else Bin()
d = b.data

DA_VA = IB + DA_RVA
DA_HI = DA_VA + DA_VSZ

# 1. 收集 .text 中所有 lea reg,[rip+disp] 目标落在 .data 的指令
lea_da = []
for addr, tgt, _mn, _op, _f in b.rip_refs(mnemonics=('lea',)):
    if DA_VA <= tgt < DA_HI:
        lea_da.append((addr, tgt))
print("lea -> .data 总数: %d" % len(lea_da))
tgts = defaultdict(int)
for a, t in lea_da:
    tgts[t] += 1
print("不重复目标: %d" % len(tgts))
al = [t for t in tgts if t % 8 == 0]
print("8 字节对齐目标: %d" % len(al))

# 2. 读 .data 原始，看哪些 8 字节槽在文件里是 0（未初始化 -> 运行期填写）
da = d[DA_RAW:DA_RAW + DA_SZ]

# 3. 打分: 候选基址 X 若为 mod_consts, 则 X..X+2808 应为
#    (a) 8 字节对齐区域
#    (b) 文件里大多为 0（未初始化）
#    (c) 被 lea 引用（至少有 1 次）
cands = []
for t in al:
    o = t - DA_VA
    span = 351 * 8
    if o + span > len(da):
        continue
    zone = da[o:o + span]
    zc = sum(1 for k in range(0, span, 8) if zone[k:k + 8] == b'\x00' * 8)
    cands.append((zc, tgts[t], t, span))
cands.sort(reverse=True)
print("\n按 [零槽数, lea引用次数] 排序的前 15 个候选 mod_consts 基址:")
print("  %-12s %-8s %-8s" % ("VA", "零槽/351", "lea次数"))
for zc, refs, t, span in cands[:15]:
    print("  %#012x %-8d %-8d" % (t, zc, refs))

# 4. 交叉验证: 候选C池 entries=351 -> 需要至少 351 个成员
print("\n=== 对候选C模块(.src.gui.verification_dialog)的 351 条做一致性检验 ===")
print("351 条 -> 结构体最小 %d 字节" % (351 * 8))
top = [c for c in cands if c[0] > 300]
print("零槽数 > 300 的候选: %d" % len(top))
for zc, refs, t, span in top[:10]:
    print("  %#012x 零槽=%d refs=%d" % (t, zc, refs))

# ── 阳性对照：已知真值必须被排到前面 ────────────────────────────────
VD = 0x181dd16a0   # verification_dialog mod_consts，rederive.py 可独立重导
print("\n[对照自检] 阳性对照（已知真值 %#x）" % VD)
rank = None
for i, (zc, refs, t, _s) in enumerate(cands):
    if t == VD:
        rank = i
        print("   真值排名: 第 %d / %d  (零槽=%d, refs=%d)" % (i + 1, len(cands), zc, refs))
        break
if rank is None:
    print("   真值不在候选集合中 —— **本定位法的盲区**：")
    print("     真值 %#x 的 .data 内偏移 = %#x，超出 rawsize=%d，落在 BSS 段；" % (
        VD, VD - DA_VA, DA_SZ))
    print("     而本脚本只读 .data 文件可见区 [0, %d)，结构上不可能覆盖真值。" % DA_SZ)
    print("   结论: 打分法**不得**用于定位或排除。改用 bss_scan/find_consumers/find_init。")
elif rank < 20:
    print("   结论: 真值排进前 20 —— 打分法在该区间有区分度，可作为粗筛")
    print("         但**不可**作为唯一定位手段（零槽法对同构结构无区分力）")
else:
    print("   结论: 真值排名靠后 —— 打分法无区分度，其输出不得用于排除")
