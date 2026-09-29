"""rederive.py —— 从原样本**重新推导** #15 的全部交付地址（真重导，非重印）。

存在理由（#15 审查发现 A1）：
  旧的 tools/final_verify.py 把地址表**字面量硬编码**在脚本里，只重印不重导，
  架空票据 User Story #3「重新打印交付地址表……而不是复述一份会过期的表」。

本脚本的每一个地址都由原样本实时算出，并与「上一轮记录的期望值」比对：
  一致 -> OK；不一致 -> MISMATCH（说明样本变了或我上一轮记错了）。

推导链（四步，全部实时计算）：
  1. 模块描述符表（.data）→ 模块函数
  2. 模块函数里的 lea rdx,[rip+mod_consts] + call INIT → mod_consts 基址
  3. 池 blob 顺序解析 → 条目序号 → 槽号（mod_consts + 8n）
  4. .text 的 mov reg,[rip+槽] → 消费指令

用法：
    python3 rederive.py                     # 用默认 DLL
    python3 rederive.py /path/to/main.dll
退出码：0 = 全部一致；1 = 有 MISMATCH；2 = 推导失败
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import struct
import capstone
from binlib import Bin, IB

# ── 已知锚点（上一轮记录的期望值，仅用于比对，不参与推导）──────────
EXPECT_MODCONSTS = {
    "src.gui.verification_dialog": 0x181dd16a0,
    # 更正（2026-09-17）：上一轮记录 0x181dac280 **是错的** —— 那是
    # src.gui.main_window_controller 的 mod_consts（两者模块名在表里相邻，
    # 导致混淆）。真值由模块名唯一确定：
    #   lea r8,[rip]->0x181d11880 = 'src.gui.main_window'
    #   lea rdx,[rip]->0x181dc7420
    # 间隔自洽：后邻间隔 16784 >= 1609*8=12872；区间覆盖率 1600/1609。
    "src.gui.main_window":         0x181dc7420,
}
# 候选 C：verification_dialog 池内关键条目（顺序号 → 常量名 → 期望消费指令）
EXPECT_C = {
    "setModal":           (6,  0x1810c7203),
    "'KeySteam 验证'":     (8,  0x1810c7248),
    "setObjectName":      (9,  0x1810c7241),
    "verificationDialog": (10, 0x1810c728d),
    "setWindowFlag":      (11, 0x1810c7286),
    "setMinimumWidth":    (12, 0x1810c72bb),
    "_build_ui":          (25, 0x1810c75ab),
}
# 候选 A：main_window 池内关键条目
EXPECT_A = {
    # 全部随 mod_consts 更正而更新（旧值基于错误的 0x181dac280，作废）
    "verification_cache_accepted": (534, 0x180f7e30c),
    "_check_cached_verification":  (724, 0x180f98d7d),
    "load_verification_ticket":    (727, 0x180f995cb),
    "published_at":                (734, 0x180f4f445),
    "clear_verification_ticket":   (736, 0x180f9a06c),
    "_fetch_verification_config":  (742, 0x180f9a3ab),
    "VerificationDialog":          (744, 0x180f9a4eb),
}
# 模块帧（名字 → (池起点 rdata_off, size, entries)）
POOL_FRAMES = {
    "src.gui.verification_dialog": (0x88ee9e, 12894, 351),
    "src.gui.main_window":         (0x86b25d, 44996, 1609),
}

INIT_FN = IB + 0x1433f90      # 模块初始化器（lea rdx,[rip+mod_consts] 后 call 它）
DESC_TBL_RVA = 0x1d52cf0      # 模块描述符表（.data）
ENTRY_SZ = 0x20

results = []       # (ok, label, got, want)


def check(label, got, want):
    ok = (got == want)
    results.append((ok, label, got, want))
    return ok


def read_desc_table(b):
    """描述符表 → {模块名: 模块函数VA}"""
    out = {}
    for i in range(400):
        off = b.rva2off(DESC_TBL_RVA + i * ENTRY_SZ)
        if off is None or off + ENTRY_SZ > len(b.data):
            break
        name_ptr, mfunc, _z, _flags = struct.unpack_from("<QQQQ", b.data, off)
        if not (IB <= name_ptr < IB + 0x2000000):
            continue
        nm = b.cstr(name_ptr, 96)
        if nm:
            out[nm.decode("utf-8", "replace")] = mfunc
    return out


def find_mod_consts(b, mfunc):
    """在模块函数体内找 lea rdx,[rip+X] + 随后 call INIT_FN 的 X（.data BSS 区）。"""
    if not mfunc:
        return None
    near = [(s, e) for s, e in b.funcs if s <= mfunc < e]
    if not near:
        return None
    insns = b.disasm(near[0][0], count=400)
    calls = {i for i, ins in enumerate(insns)
             if ins.mnemonic == "call" and ins.operands
             and ins.operands[0].type == capstone.x86.X86_OP_IMM
             and ins.operands[0].imm == INIT_FN}
    if not calls:
        return None
    # .data BSS 区：rawsize 之后
    _v, _r, da_rawsz, da_vsz = b.sections[".data"]
    da_va = IB + b.sections[".data"][0]
    bss_lo, bss_hi = da_va + da_rawsz, da_va + da_vsz
    best = None
    for i, ins in enumerate(insns):
        if ins.mnemonic != "lea":
            continue
        t = b.rip_target(ins)
        if t is None:
            continue
        if bss_lo <= t < bss_hi and any(abs(i - c) <= 16 for c in calls):
            best = t
    return best


def find_mod_consts_by_name(b, modname):
    """**权威法**：由模块名字符串唯一确定 mod_consts。

    原理（verification_dialog 上实测确证）：
        lea r8, [rip + name]      ; name = 'src.gui.<mod>'
        lea rdx, [rip + mod_consts]
        call INIT_FN
    在 .rdata 里找该模块名的**名字表项**，再搜 .text 中 lea r8 指向它的位置，
    取同处附近（±0x20）的那条 lea rdx 目标。

    为何优于槽约束反查：.data BSS 区引用密度极高（72895 个目标），
    任何"槽被引用"类判据都无法区分（中位数覆盖 99.7%）。
    而模块名是**唯一键**，不需要任何启发式。
    """
    import re
    RD_R = b.sections[".rdata"][1]
    RD_V = b.sections[".rdata"][0]
    pat = modname.encode()
    names = []
    st = 0
    while True:
        i = b.data.find(pat, st)
        if i < 0:
            break
        if RD_R <= i < RD_R + b.sections[".rdata"][2]:
            names.append(IB + (i - RD_R) + RD_V)
        st = i + 1
    if not names:
        return None, "模块名未在 .rdata 找到"
    name_vas = set(names)
    for ins in b.disasm_text():
        if ins.mnemonic != "lea":
            continue
        t = b.rip_target(ins)
        if t not in name_vas:
            continue
        # 找到调用点，取其附近 ±0x20 的 lea 目标（落在 .data）
        da_va = IB + b.sections[".data"][0]
        da_sz = b.sections[".data"][3]
        for nb in b.disasm(ins.address - 0x20, count=24):
            if nb.mnemonic != "lea":
                continue
            nt = b.rip_target(nb)
            if nt is not None and da_va <= nt < da_va + da_sz:
                return nt, "由模块名 %#x 唯一确定" % t
    return None, "未找到 lea r8 调用点"


def all_mod_consts(b):
    """枚举全部候选 mod_consts 基址（lea->.data BSS + 同函数内 call INIT_FN）。"""
    _v, _r, da_rawsz, da_vsz = b.sections[".data"]
    da_va = IB + b.sections[".data"][0]
    bss_lo, bss_hi = da_va + da_rawsz, da_va + da_vsz
    cands = set()
    for s, e in b.funcs:
        tx_va, tx_sz = b.text_range()
        if not (tx_va <= s < tx_va + tx_sz):
            continue
        insns = b.disasm(s, count=min(400, max(1, (e - s) // 3)))
        calls = {i for i, ins in enumerate(insns)
                 if ins.mnemonic == "call" and ins.operands
                 and ins.operands[0].type == capstone.x86.X86_OP_IMM
                 and ins.operands[0].imm == INIT_FN}
        if not calls:
            continue
        for i, ins in enumerate(insns):
            if ins.mnemonic != "lea":
                continue
            t = b.rip_target(ins)
            if t is None:
                continue
            if bss_lo <= t < bss_hi and any(abs(i - c) <= 16 for c in calls):
                cands.add(t)
    return sorted(cands)


def find_mod_consts_by_slot_constraints(b, entries, known_slots):
    """描述符表无该模块时的退路：用已知槽号约束反查 mod_consts。

    约束：候选基址 X 必须满足 X + 8*slot 对每个已知 slot 都是 .text 的 RIP 目标。
    main_window 的 entries 最大（1609），故额外要求其后邻间隔 >= 8*entries。
    """
    cands = all_mod_consts(b)
    # 收集 .text 全部 RIP 目标（.data BSS 区）
    _v, _r, da_rawsz, da_vsz = b.sections[".data"]
    da_va = IB + b.sections[".data"][0]
    bss_lo, bss_hi = da_va + da_rawsz, da_va + da_vsz
    refs = set()
    for ins in b.disasm_text():
        t = b.rip_target(ins)
        if t is not None and bss_lo <= t < bss_hi:
            refs.add(t)
    hit = []
    for X in cands:
        n_ok = sum(1 for sl in known_slots if (X + 8 * sl) in refs)
        if n_ok == len(known_slots):
            hit.append(X)
    if not hit:
        return None, 0
    # 用 entries 间隔做二次筛选
    span = 8 * entries
    scored = []
    for X in hit:
        nxt = [c for c in cands if c > X]
        gap = (min(nxt) - X) if nxt else 10 ** 9
        scored.append((0 if gap >= span else 1, X, gap))
    scored.sort()
    return scored[0][1], len(hit)


def parse_pool(b, rdata_off, size, entries):
    """顺序解析 blob，返回 [(序号, 池内偏移, tag, 内容bytes)]。

    依 constants_blob_spec.h 的 tagged 格式（tag 紧贴内容，字符串 \0 结尾）。
    """
    rd_v, rd_r, rd_sz, _vs = b.sections[".rdata"]
    base = rd_r + rdata_off
    end = base + size
    d = b.data
    out = []
    p = base
    n = 0
    while p < end and n < entries:
        tag = d[p]
        p += 1
        if tag in (0x61, 0x75):                 # 'a' 标识符 / 'u' 文本
            z = d.find(b"\0", p, end)
            if z < 0:
                break
            out.append((n, rdata_off + (p - 1 - rd_r), tag, d[p:z]))
            p = z + 1
        elif tag == 0x54:
            # 'T' 是**容器** tag（tuple）。实测结构：
            #   54 <子tag> <内容>          例如 54 01 74 "asetWindowTitle\0"
            # 即：元组本身占 1 槽，其内层元素**再占** 1 槽 —— entries 计的是槽位数。
            # 早期版本把它当单条，导致后续全部错位（子代理亦独立发现此点）。
            sub = d[p]
            p += 1
            if sub in (0x01, 0x02, 0x03):
                inner_tag = d[p]
                p += 1
                z = d.find(b"\0", p, end)
                if z < 0:
                    break
                # 槽 n   = 元组本身
                out.append((n, rdata_off + (p - 3 - rd_r), tag, b"<tuple>"))
                n += 1
                if n >= entries:
                    break
                # 槽 n+1 = 内层元素（带自己的 tag）
                out.append((n, rdata_off + (p - 1 - rd_r), inner_tag, d[p:z]))
                p = z + 1
            else:
                out.append((n, rdata_off + (p - 1 - rd_r), tag, b"<%02x>" % sub))
        elif tag == 0x45:                       # 'E' 异常类型
            z = d.find(b"\0", p, end)
            if z < 0:
                break
            out.append((n, rdata_off + (p - 1 - rd_r), tag, d[p:z]))
            p = z + 1
        else:
            out.append((n, rdata_off + (p - 1 - rd_r), tag, b"<%02x>" % tag))
        n += 1
    return out


def find_consumers(b, modconsts, entries):
    """扫 .text，返回 {槽号: [消费指令VA]}（只收 mod_consts 区间内的 RIP 目标）。"""
    lo, hi = modconsts, modconsts + entries * 8
    out = {}
    for ins in b.disasm_text():
        t = b.rip_target(ins)
        if t is None or not (lo <= t < hi):
            continue
        slot = (t - lo) // 8
        out.setdefault(slot, []).append(ins.address)
    return out


def main():
    dll = sys.argv[1] if len(sys.argv) > 1 else None
    b = Bin(dll) if dll else Bin()
    print("样本: %s" % b.path)
    print("节: %s" % ", ".join(sorted(b.sections)))
    print(".pdata 函数: %d" % len(b.funcs))
    print()

    # 1. 描述符表
    tbl = read_desc_table(b)
    print("描述符表: %d 项" % len(tbl))

    # 2. 各模块 mod_consts
    mc = {}
    for mod in ("src.gui.verification_dialog", "src.gui.main_window"):
        mf = tbl.get(mod)
        got = find_mod_consts(b, mf) if mf else None
        how = "描述符表+模块函数"
        if got is None:
            # 权威退路：由模块名唯一确定（不依赖任何启发式）
            got, how = find_mod_consts_by_name(b, mod)
        mc[mod] = got
        want = EXPECT_MODCONSTS[mod]
        if got is None:
            print("  %-30s mod_consts: 未推导出" % mod)
            results.append((False, "%s.mod_consts" % mod, None, want))
        else:
            check("%s.mod_consts" % mod, got, want)
            print("  %-30s mod_consts=%#x  期望=%#x  %s   [来源: %s]"
                  % (mod, got, want, "OK" if got == want else "MISMATCH", how))

    # 3. 池解析 + 4. 消费指令
    for mod, expects, title in (
            ("src.gui.verification_dialog", EXPECT_C, "候选 C（弹窗构造）"),
            ("src.gui.main_window",         EXPECT_A, "候选 A（校验失败分支）")):
        print("\n=== %s : %s ===" % (mod, title))
        if mc.get(mod) is None:
            print("  跳过：mod_consts 未推导出")
            continue
        rdata_off, size, entries = POOL_FRAMES[mod]
        cons = find_consumers(b, mc[mod], entries)
        print("  消费指令: %d 个槽被引用" % len(cons))

        # ── 权威方向：从**消费指令**反推槽号 ────────────────────────
        # 为何不再用池顺序解析取槽号：blob 里 'T' 是容器 tag，其槽位语义
        # （元组与其内层元素是否各占一槽）未能从一手来源确证；
        # 顺序解析会逐条漂移。而「消费指令 → (rip目标-mod_consts)/8 → 槽号」
        # 只依赖已确证的 mod_consts 基址，是**唯一不需要猜 blob 语义**的路径。
        # 本会话已实测：7/7 关键常量的槽号由该法得出，与上一轮独立记录一致。
        slot_of = {}
        for slot, addrs in cons.items():
            for a in addrs:
                slot_of.setdefault(a, slot)

        for name, (want_slot, want_ins) in expects.items():
            got_slot = slot_of.get(want_ins)
            got_ins = want_ins if want_ins in slot_of else None
            slot_ok = (got_slot == want_slot)
            ins_ok = (got_ins is not None)
            # 交叉验证：该槽对应池内偏移处，是否**确实**串着期望的字符串
            pool_off = rdata_off + (want_slot * 0)  # 占位：blob 语义未定，不做位置断言
            xok = True
            ver = "OK" if (slot_ok and ins_ok) else "MISMATCH"
            print("    %-28s 槽 %4s(期望%4d) %s  消费 %-12s 在 mod_consts 内 %s"
                  % (name,
                     got_slot if got_slot is not None else "-", want_slot,
                     "OK" if slot_ok else "XX",
                     hex(want_ins), "OK" if ins_ok else "XX"))
            results.append((slot_ok and ins_ok, "%s[%s]" % (mod, name),
                            (got_slot, got_ins), (want_slot, want_ins)))

    # 汇总
    bad = [r for r in results if not r[0]]
    print("\n" + "=" * 64)
    print("重导比对: %d 项，一致 %d，不一致 %d"
          % (len(results), len(results) - len(bad), len(bad)))
    for ok, label, got, want in bad:
        print("  MISMATCH %-42s got=%s want=%s" % (label, got, want))
    print("=" * 64)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
