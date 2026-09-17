# 09 — 修正设断点时机：主线程与早期线程被系统性漏掉

**What to build:**

修掉 hwbp 组三个脚本共有的一个缺陷：**设断点依赖 `main_base`，导致主线程与 DLL 加载前创建的线程永远设不上断点。**

## 缺陷

三个脚本（`hwbp16b.py` / `hwbp_ctrl.py` / `hwbp_data.py`）的设断点逻辑完全相同：

```
elif code in (3, 2):   # CREATE_PROCESS / CREATE_THREAD
    if main_base:      # ← 问题在这里
        set_hwbp(ht, main_base + <目标 RVA>)
```

而 `main_base` **只在 `LOAD_DLL` 分支赋值**。调试事件顺序是
`CREATE_PROCESS(3) → CREATE_THREAD(2) → … → LOAD_DLL(6)`，所以：

- 主线程的 `CREATE_PROCESS` 到来时，`main_base` 仍是 `None` → **主线程永远设不上断点**
- DLL 加载前创建的任何线程，同理

**实测时间线**（工单 08 的 Q5，`dr7Q5_q5b.txt`）：

```
[0.004] CreateProcessW ok=True pid=35524 main_tid=32800
[0.012] MAIN.DLL base=... @0.012s          ← LOAD_DLL 在 12ms 才到
```

而 Q1 的记录显示多个线程在 `@0.060s` 已存在（`dr7Q1_q1.txt`）。

## 为什么只有 `hwbp_data.py` 暴露了后果

三个脚本结构相同，但监视的目标不同：

- `hwbp16b` / `hwbp_ctrl` 监视 `AUX_RVA`（`0x1422ec0`），它在 **@2.2s** 才被访问——那时已有大量新线程创建，断点设上了，故命中 40 万次
- `hwbp_data` 监视 `verification_dialog` 的 `mod_consts`（RVA `0x1dd16a0`），**主线程在 @0.884s 就写它**（工单 08 的 Q1 实测），**早于任何新线程** → 0 命中

**所以这不是 `hwbp_data` 独有的问题，是三个脚本共有的。** 只是前两个的观测目标恰好在"断点已设上"之后才被触碰。

## 修法（有真实取舍，需设计）

主线程的 `CREATE_PROCESS` 事件里**拿不到** `main_base`（DLL 尚未加载），而断点地址需要它。所以不能简单"无条件设断点"。

可选方向：

- **在 `LOAD_DLL` 分支里补设主线程的断点**——`LOAD_DLL` 时已知道 `main_base`，且能拿到主线程句柄
- **缓存待设断点的线程 ID**：`CREATE_PROCESS`/`CREATE_THREAD` 时先记下来，`LOAD_DLL` 后统一补设
- **区分目标类型**：对"模块初始化期写入"这类目标（如 `mod_consts`），补设是必需的；对"运行期访问"类目标（如 `AUX_RVA`），现有行为已够

**这是设计决策，不是机械修改。** 实施前需先定：补设的时机是否引入新的窗口（DLL 加载到补设之间，目标已被写怎么办）？

## 与重构主线的关系

**本票不属于 `probe_lib` 收口的范围。** 它是工单 08 的副产物，独立成立。

**依赖**：`hwbp16b` / `hwbp_ctrl` / `hwbp_data` 三个文件也被工单 04/05/06 触及。**本票应在那些票完成后再做**，避免同文件多方编辑。

## 验收

- [ ] 主线程在观测窗口内**确实设上了断点**（有日志或回读 `Dr0`/`Dr7` 证明）
- [ ] `hwbp_data.py` 重跑后命中数**不再为 0**，或若仍为 0，能说明是"该地址在该线程上确实未被写"而非"断点未设上"
- [ ] 三个脚本（`hwbp16b`/`hwbp_ctrl`/`hwbp_data`）的既有观测不受破坏——`hwbp16b`/`hwbp_ctrl` 的命中量级应与修改前相当（40 万级）
- [ ] 补设时机若引入新窗口，已明确说明该窗口内发生写会怎样
- [ ] 结论与证据写入 `../findings-hwbp-zero-hit.md` 或独立文档

**Blocked by:** 04、05、06（同文件，须先完成重构迁移以避免并发编辑）
