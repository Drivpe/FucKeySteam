"""patchpoint.py —— 定位候选C(弹窗构造)的指令级 patch 点。

已确证:
  verification_dialog 的 mod_consts 基址(静态) = 0x181dd16a0
  池条目 #n -> 槽 n -> mod_consts + 8*n
  setModal        = 条目 #6  -> mod_consts+0x30
  'KeySteam 验证' = 条目 #8  -> mod_consts+0x40
  verificationDialog = #10   -> mod_consts+0x50
  _build_ui       = #25      -> mod_consts+0xc8

本脚本: 找引用这些槽的全部 .text 指令, 并给出上下文。

**检索词表（docs/agents/domain.md:86）**：检索**任意操作码**的 RIP 相对内存操作数，
目标落在 [MC, MC+351*8)。不按操作码白名单过滤。

**阳性对照**：末尾「[对照自检]」段以 rederive.py 可独立重导的
`setModal` 槽 6 消费指令 `0x1810c7203` 验证「槽 -> 消费指令」检索管线。
该指令必须出现在结果中，且其 rip 目标须等于 MC+6*8。

节表 / .pdata / RIP 相对判定 / 路径常量全部来自 binlib。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from binlib import Bin, IB

DLL = os.environ.get("KS_MAIN_DLL", None)
b = Bin(DLL) if DLL else Bin()

MC = 0x181dd16a0
ENTRIES = 351

TARGETS = {6: "setModal", 8: "'KeySteam 验证'", 10: "verificationDialog",
           25: "_build_ui", 29: "_show_config_error", 0: "resizeEvent",
           5: "setFixedHeight", 9: "setObjectName", 11: "setWindowFlag",
           12: "setMinimumWidth", 13: "setMaximumWidth"}

# 收集所有指向 mod_consts+8n 的引用（任意操作码）
refs = []
for addr, tgt, mn, opstr, fstart in b.rip_refs():
    if MC <= tgt < MC + ENTRIES * 8:
        refs.append((tgt, (tgt - MC) // 8, addr, mn, opstr, fstart))
print("指向 mod_consts(verification_dialog) 的引用: %d" % len(refs))
print()
for slot, name in TARGETS.items():
    addr = MC + slot * 8
    sel = [r for r in refs if r[1] == slot]
    print("槽 %3d  %-20s 槽地址=%#x  引用数=%d" % (slot, name, addr, len(sel)))
    for t, sn, a, mn, os_, fs in sel[:6]:
        print("      %#x  %s %s   (函数 %#x)" % (a, mn, os_, fs))
print()

# ── 阳性对照：已知消费指令必须出现在结果中 ──────────────────────────
print("[对照自检] 阳性对照（锚点来自 rederive.py，可独立重导）")
KNOWN = {
    0x1810c7203: (6, "setModal"),
    0x1810c7248: (8, "'KeySteam 验证'"),
    0x1810c75ab: (25, "_build_ui"),
}
pos_ok = True
for va, (slot, name) in KNOWN.items():
    want = MC + slot * 8
    hit = any(a == va and sn == slot for _t, sn, a, _m, _o, _f in refs)
    ins = b.disasm(va, 1)
    got = Bin.rip_target(ins[0]) if ins else None
    coord_ok = (got == want)
    if not (hit and coord_ok):
        pos_ok = False
    print("   %#x 槽%-3d %-18s 在引用结果中: %-4s  rip目标 %s == %#x: %s" % (
        va, slot, name, "命中" if hit else "缺失",
        hex(got) if got else None, want, "是" if coord_ok else "否"))
print("   结论: %s" % ("槽->消费指令检索管线有效，坐标换算一致"
                      if pos_ok else
                      "管线自检失败 —— 不得据本输出下任何排除性结论"))

print("\n=== setModal(槽6) 全部引用 ===")
for t, sn, a, mn, os_, fs in refs:
    if sn == 6:
        print("   %#x  %s %s  (函数 %#x)" % (a, mn, os_, fs))
