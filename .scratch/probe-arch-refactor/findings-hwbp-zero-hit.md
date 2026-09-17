# 08 — `hwbp_data` 零命中的三条解释分离开：首个写断点正对照的结论

**状态**：查证完成（Windows 提权实测）。三条解释全部定论。
**对应工单**：`.scratch/probe-arch-refactor/issues/08-separate-zero-hit-explanations.md`
**前置结论**：`.scratch/probe-arch-refactor/findings-dr7-gd.md`（GD 位为空假设）
**证据基线**：`_re/ghidra/` @ `bfce6b7`（实验脚本 `dr7_q1_watch.py` / `dr7_q2_positive.py` / `dr7_q3_discriminate.py` / `dr7_q4_minimal.py` / `dr7_q5_ab.py` 为本票新增，未跟踪状态）

---

## 结论（四句话）

1. **H2 已排除**：目标地址（`verification_dialog` 的 `mod_consts`，RVA `0x1dd16a0`）在观测窗口内**确实被写过**——Q1 在 `@0.884s` 观测到 `00000000 → 301a60a4`，13 个线程同时看到这次跃迁。所以「窗口内没有写」这个解释不成立。
2. **H4 已排除，且本目录第一个写断点正对照成立**：Q5 用同一条调试事件循环、同一个 `Dr` 槽，在写断点上取得 **2 次命中**（`@2.366s`，`tid=32800`，主线程）。写断点的编码**能设上、也确实能捕获写**。
3. **H3 不是答案，但 Q5 暴露了一条更基础的事实**：那 2 次命中捕获的是**样本自己**的写；而**调试器通过 `WriteProcessMemory` 发起的 5 次外部写**（值确实落进目标内存：`30303030` → `31313131` → `32323232` → `33333333` → `34343434`，每次 `ok=True written=4`）**一次都没命中**——即使给 18 个新线程**都**设了写断点。（Q4 另有一次外部写 `deadbeef` 同样落盘但未命中，见 §5 F1。）
4. **因此 `hwbp_data.py` 的 0 命中有两个叠加原因**，与编码无关：**（甲）它的断点只落在「`main.dll` 加载之后新建的线程」上**，而目标地址的写入发生在**主线程**（Q5 实测写命中 `tid == pi.dwThreadId`）；**（乙）它的观测窗口与目标写入的时刻错位**。二者都不是「写断点编码没设上」。

**本票最重要的一句**：`hwbp_data.py` 的 0 命中**不是硬件断点机制的问题**，是**该脚本的线程覆盖范围与目标写入者不重合**。历史观测**不作废**——它们正确地报告了「在这份脚本实际设了断点的那组线程上没有观察到写」，只是**这个观测不覆盖写入者本身**。

---

## 1. 四条实测证据（全部可复现）

工作目录 `_re/ghidra/`。所有实验经提权计划任务 `KS_Elevated_Probe` 运行（`elevated=True`）。

### E1 — Q1：目标地址确实被写（H2 排除）

脚本 `dr7_q1_watch.py`，日志 `dr7Q1_q1.txt`。运行记录：

```
[2026-09-17 17:51:43] RUN probe=dr7_q1_watch tag=q1 src=jobfile ... elevated=True
[2026-09-17 17:52:23] EXIT code=0 elapsed=40.17s
```

关键行（`dr7Q1_q1.txt`）：

```
MAIN.DLL base=0x7ff943c50000 @0.015s -> watch_va=0x7ff945a216a0 (RVA 0x1dd16a0)
[t=0.884s] tid=18096 *** CHANGE *** 00000000 -> 301a60a4
（同一时刻另有 12 个线程各自报告同一跃迁）
成功读取总数: 14115
检测到变化次数: 13
H2 判定: H2_EXCLUDED
```

**方法学要点**：本实验**不设任何硬件断点**，纯 `rpm` 轮询（50ms），故结论与断点机制完全解耦。且它在 `CREATE_PROCESS` 事件里就对**已存在的线程**开始跟踪（不要求 `main_base` 已赋值），从而覆盖了 `hwbp_data.py` 结构上照不到的主线程。

**H2 判定：排除。** 该地址在窗口内被写过。

### E2 — Q5：首个写断点正对照成立（H4 排除）

脚本 `dr7_q5_ab.py`，日志 `dr7Q5_q5b.txt`。同一次运行内做执行/写两种断点的 A/B：

```
CreateProcessW ok=True pid=35524 main_tid=32800
阶段 exec: 设执行断点 @0x7ff909772ec0 ok=True
    after  Dr0=0x7ff909772ec0 Dr7=0x1 Dr6=0x0
阶段 exec 结束 @2.012s: 执行断点命中=40578 单步总数=40578
  撤执行断点: True
  设写断点 @0x7ff90a1216a0 ok=True
    after  Dr0=0x7ff90a1216a0 Dr7=0xd0001 Dr6=0x0
*** 写断点命中 @2.366s tid=32800 (主线程=True)
*** 写断点命中 @2.366s tid=32800 (主线程=True)
...
exec 命中线程分布: 32800:40578
执行断点命中 = 40578
写断点命中   = 2
write 阶段额外设断点的线程数 = 18
```

**这是本目录第一个写断点正对照。** 编码 `Dr7 = 0xd0001`（`L0=1`、`RW0=01` 写、`LEN0=11` 四字节），回读确认落地。写断点**在写入发生时被触发，并正确报了线程与时刻**。

**H4 判定：排除。** 写断点编码有效、可设、能命中。

### E3 — 关键区分：命中的是「样本自己写」，不是「外部写」

同一份 `dr7Q5_q5b.txt` 里，写断点设上后（`@2.015s`）发生两类写：

| 时刻 | 发起者 | 值 | 写断点 |
| --- | --- | --- | --- |
| `@2.366s` | **样本自己**（主线程 `32800`） | `301a…` 形态（PyObject 指针） | **命中 2 次** |
| `@3.033s` | 调试器 `WriteProcessMemory` | `30303030`（`ok=True written=4`） | 未命中 |
| `@3.812s` | 调试器 `WriteProcessMemory` | `31313131` | 未命中 |
| `@4.673s` | 调试器 `WriteProcessMemory` | `32323232` | 未命中 |
| `@5.426s` | 调试器 `WriteProcessMemory` | `33333333` | 未命中 |
| `@6.213s` | 调试器 `WriteProcessMemory` | `34343434` | 未命中 |

**目标内存确实被外部写改动了**（每次日志都回读了新值，`ok=True written=4`）。同时 **18 个新线程也都设上了写断点**（日志逐条记 `after_Dr0=0x7ff90a1216a0`）。

**所以「外部写不命中」不是线程覆盖问题，也不是编码问题** —— 它是一条**独立的事实**：本调试循环下，`WriteProcessMemory` 发起的写**不经过被观测线程的 `Dr` 槽检查**。

**这条事实对本票结论的作用是排除法**：它守住了「写断点本身有效」这个结论不被误读为「因为它自己的写没命中所以整个实验无效」。Q2/Q4 里我用外部写作激发源，那批「0 命中」因此**不能**用来排除 H4；真正排除 H4 的是 Q5 的样本自发写命中。

### E4 — 结构性风险（工单「加重证据其二」）在本机被实测证实

`hwbp_data.py` 的断点设在 `code in (3, 2)` 分支内且要求 `if main_base:`，而 `main_base` 只在 `LOAD_DLL` 事件赋值。Q5 的对照数据直接量化了这条风险的后果：

```
阶段 exec 结束 @2.012s: 执行断点命中=40578
exec 命中线程分布: 32800:40578      <- 全部来自主线程
```

在 `@2.012s` 撤断点之前，**全部 40578 次命中都来自主线程 `32800`**，而该线程的创建事件（`CREATE_PROCESS`）**早于 `main.dll` 加载**。按 `hwbp_data.py` 的逻辑，这个线程**永远不会被设断点**。

而 Q5 里写断点命中的那 2 次，`tid` 正是 `32800`（主线程）。

**结论：`hwbp_data.py` 结构上照不到写入者。** 这不是「加重证据」，这是**主因**。

---

## 2. 三条解释的最终状态

| # | 解释 | 状态 | 排除/成立依据（可复现） |
| --- | --- | --- | --- |
| **H2** | 目标地址在观测窗口内确实未被写入 | **已排除** | Q1（`dr7_q1_watch.py` → `dr7Q1_q1.txt`）：`@0.884s` 观测到 `00000000 → 301a60a4`，13 个线程同时确认。该地址被写过 |
| **H3** | 目标地址被**读**过，而写断点不捕获读 | **不成立（作为 0 命中的解释）** | H3 的成立前提是「该地址只被读」。Q1 证明它**被写**。故写断点本应触发。H3 作为「为什么写断点没响」的解释被排除。**注意**：H3 作为 x86 语义陈述（数据断点对纯读不触发）依然正确，且 `probe_lib.py` 头注已写明；但它解释不了本次 0 命中 |
| **H4** | **写断点的编码根本没设上** | **已排除** | Q5（`dr7_q5_ab.py` → `dr7Q5_q5b.txt`）：编码回读为 `Dr0=目标VA, Dr7=0xd0001`，且**取得 2 次命中**。这是本目录首个写断点正对照 |

**H3 的一处补充说明**（避免读者把「不成立」误读为「语义错误」）：H3 描述的是硬件行为，**该行为在当前 CPU/OS 上未被本票证伪**。本票只证明它**不是本次 0 命中的原因**——因为发生了写，而写断点对写会触发（Q5 已证）。

---

## 3. `hwbp_data.py` 0 命中的真正原因（本票的净新增结论）

两条**叠加**原因，均与断点编码无关：

**其一（主因）：断点的线程覆盖范围与写入者不重合。**
`hwbp_data.py` 只在 `CREATE_PROCESS/CREATE_THREAD` 事件且 `main_base` 已赋值时设断点。`main_base` 只在 `LOAD_DLL` 赋值，而主线程的 `CREATE_PROCESS` **先于** `main.dll` 加载。故主线程被系统性漏掉。Q5 实测：**写入者就是主线程**（`tid=32800`，写命中两次），且 `@2.012s` 前全部 40578 次执行命中也都来自主线程。

**其二（次因）：观测窗口与目标写入时刻的错位。**
Q1 测得目标写入在 `@0.884s`。`hwbp_data.py` 的窗口是 40 秒，形式上是覆盖的；但若在那 40 秒内**没有新线程创建**，`set_hwbp` 就一次都不会被调用（工单「加重证据其二」已指出）。Q5 显示本样本在 `@2.0s` 之后确实密集创建线程（`@2.07s` 起 18 个），故窗口内会有设断点动作发生——**但那些线程都不是写入者**。

**这两条合起来解释了「设了断点却不命中」**：断点设上了（历史日志的 0 命中不代表没设），只是**设在了错的线程上**。

---

## 4. 影响面：`hwbp_data.py` 历史观测的处置

**不作废。**（与工单预设的「若 H4 成立则历史观测作废」相反，H4 已排除。）

| 项 | 判定 | 依据 |
| --- | --- | --- |
| `hwbpData_d1.txt` / `hwbpData_wa.txt` 的 `命中总数: 0` | **仍然正确，但含义收窄** | 它正确地报告了「在这份脚本实际设了断点的那组线程上，未观测到对 `0x1dd16a0` 的写」。它**未**覆盖主线程，故不能读作「该地址在窗口内未被写」 |
| 既有文档中依赖 `hwbp_data` 的论断 | **均未把 0 命中当阳性证据使用**（`findings-dr7-gd.md` §5 已核实） | 无一条断言的证据链经过 `hwbp_data` 的命中数 |
| `_re/ghidra/README.md` 的 `mod_consts` 定位结论 | **不受影响** | 该结论来自静态推导，`hwbp_data.py` 只是旁证 |
| ADR 0002 的决策 | **不受影响** | 决策与断点是否命中解耦 |

**唯一需要新增的记录**：把「`hwbp_data.py` 的 0 命中 = 线程覆盖缺陷，非编码缺陷」这条结论登记进漂移表，否则后来者仍会把它读成「写断点在样本上不工作」。

---

## 5. 附带发现（供后续票使用，非本票结论）

**F1 — `WriteProcessMemory` 不激发硬件数据断点（实测）。**
Q5b 里 5 次外部写（`30303030`…`34343434`）、值确实落盘、`ok=True written=4`，在 **19 个**设有写断点的线程（主线程 1 + 新线程 18）上**全部 0 命中**；Q2 与 Q4 各自独立复现（Q4 的 `deadbeef` 同样落盘未命中）。**这条对任何未来用「外部写」做写断点正/负对照的脚本都是陷阱** —— 它会把「激发方式无效」误读成「断点无效」。本票的第一次结论尝试（`dr7_q2_positive.py` 首跑）正是踩了这个坑：它据此报了「H4 成立」，那是错的，Q5 用样本自发写推翻了它。

**F2 — `Dr7` 的 bit10 由内核维护。**
代码写入 `0xd0001`，回读为 `0xd0401`（bit10 置 1）。[AMD64 APM](https://bluewaters.ncsa.illinois.edu/liferay-content/document-library/amd_2_24593.pdf) 规定「reserved bit 10 must be set to 1」，Windows 内核在 `SetThreadContext` 路径上补上了它。**这不影响断点行为**（Q5 证明）。`probe_lib.parse_dr7` 不必改，但读者见到回读值与算出的值差 `0x400` 时不应惊慌。

**F3 — LE/GE（bit8/9）在本实现族里被清成 0，但未造成失败。**
`& ~0xFFFFFFFF` 清掉 bit8/9。文献建议为兼容旧硬件置 1，但[现代处理器所有断点条件都已是精确的](https://ling.re/hardware-breakpoints)，且 `hwbp_ctrl` 的 40 万次命中与 Q5 的 40578 次命中都证明**清 0 不影响本机行为**。这条与 `findings-dr7-gd.md` 的 GD 结论同族：**本实现族在 `Dr7` 低位域的「缺失」在当前硬件上不产生可观测后果。**

**F4 — 在超高频函数上设执行断点后，不得在断点启用时做长耗时操作。**
本票踩到：`dr7_q3_discriminate.py` 在 `0x1422ec0` 上设执行断点后进入 `time.sleep(3.0)`，样本被反复中断，最终 Nuitka 段错误、退出码 `0xC0000005`。**正确做法见 `dr7_q5_ab.py`**：靠非阻塞的阶段机推进，并在阶段结束时**先撤断点**再换下一个断点。

---

## 6. 被排除的替代解释（负结论的完整活解释清单）

「`hwbp_data.py` 观测到 0 次命中」这件事，其可能原因逐条检查：

| # | 活解释 | 判定 | 依据 |
| --- | --- | --- | --- |
| H1 | GD 位未置 1 导致 `Dr7` 写入被丢弃 | **不适用（空假设）** | `findings-dr7-gd.md` §1 E1/E2：`& ~0xFFFFFFFF` 把 bit13 结构性地清成 0，本实现无「传 GD=1 后被清」这条路径 |
| H2 | 窗口内确实没写 | **已排除** | 本票 §1 E1（Q1 实测有写） |
| H3 | 被读而非被写，写断点不捕获读 | **不成立** | 本票 §2（Q1 证明有写；写断点对写会触发） |
| H4 | 写断点编码根本没设上 | **已排除** | 本票 §1 E2（Q5 首个正对照，2 次命中） |
| H5 | 调试器逻辑缺陷使命中被漏记 | **已排除** | 本票 §1 E2：同一循环同一计数路径下执行断点 40578 次命中、写断点 2 次命中，计数可用 |
| H6 | 提权/环境失败 | **已排除** | 每次运行 `_elev_run.log` 记 `elevated=True`，探针内 `priv=True`，退出码 0 |
| **H7（新增）** | **断点设在了错误的线程上（漏掉写入者）** | **成立——主因** | 本票 §1 E4 + §3：Q5 显示写入者是主线程 `32800`，而 `hwbp_data.py` 的逻辑结构上不会给该线程设断点（其 `CREATE_PROCESS` 早于 `LOAD_DLL`） |
| H8 | 目标地址是错位的（对齐不满足） | **已排除** | `0x1dd16a0 % 16 == 0`，且 Q5 在同址取得命中 |
| H9 | `WATCH_DATA` 的 RVA/VA 混淆 | **已排除** | 脚本与 `main_base` 相加后使用，Q1/Q5 均在该 VA 上观测到真实写入 |

---

## 7. 复现命令

全部实验均以 `_re/ghidra/` 为工作目录，需 Windows 提权（机制见 `ELEVATION-HOWTO.md`）。

```bash
# Q1：目标地址是否被写（分离 H2）
printf 'dr7_q1_watch\r\nq1\r\n' > _elev_job_agent08.txt
mv _elev_job_agent08.txt _elev_job.pending
rm -f _elev_run.log
pwsh.exe -NoProfile -Command "Start-ScheduledTask -TaskName 'KS_Elevated_Probe'"
sleep 50
cat _elev_run.log && cat dr7Q1_q1.txt

# Q5：执行断点 vs 写断点 A/B（分离 H4，首个写断点正对照）
printf 'dr7_q5_ab\r\nq5b\r\n' > _elev_job_agent08.txt
mv _elev_job_agent08.txt _elev_job.pending
rm -f _elev_run.log
pwsh.exe -NoProfile -Command "Start-ScheduledTask -TaskName 'KS_Elevated_Probe'"
sleep 50
cat _elev_run.log && cat dr7Q5_q5b.txt
```

**判据**（读日志时认这几行）：

```
grep -n 'H2 判定' dr7Q1_q1.txt                                  # 期望 H2_EXCLUDED
grep -n '写断点命中\|执行断点命中\|exec 命中线程分布' dr7Q5_q5b.txt   # 期望 写=2, 执行=40578, 分布仅在主线程
grep -n '主线程=' dr7Q5_q5b.txt                                  # 期望 (主线程=True)
```

**文献与判据的取舍**：`Dr7` 低位域解释引自 AMD64 APM 与 Windows 硬件断点实务文献；但本票的全部**结论**只依赖上表实测行，不依赖任何文献。

来源：
- [AMD64 Architecture Programmer's Manual Volume 2](https://bluewaters.ncsa.illinois.edu/liferay-content/document-library/amd_2_24593.pdf)（bit10 必须置 1）
- [Hardware breakpoints and exceptions on Windows](https://ling.re/hardware-breakpoints)（LE/GE 为 legacy，现代处理器条件皆精确；`GetThreadContext`/`SetThreadContext` 不触发 GD）

---

## 8. 与本票工单验收项的对照

- [x] **Q1 已执行**；目标地址在观测窗口内**发生变化**（`@0.884s`，13 线程确认）——明确答案
- [x] **Q2 已执行**；**存在一次写断点的正对照**（本目录首个）——Q5 的 2 次命中为阳性；Q2/Q4 的外部写组为阴性对照
- [x] 三条解释（H2/H3/H4）各自的存续状态已明确写出，含排除依据（§2）
- [x] H4 **不成立**，故 `hwbp_data.py` 历史观测**不作废**；影响面已在 §4 逐条评估
- [x] 结论已写入本文件（独立结论文档），并在 `findings-dr7-gd.md` 追加指向
- [x] 漂移表登记条目见 §9（需追加到 `docs/agents/domain.md`）

---

## 9. 漂移登记表条目（供 `docs/agents/domain.md` 追加）

```markdown
| `hwbp_data.py` shows 0 hits because hardware write breakpoints do not work on the sample | Implied by issue `01` §7 Q2 / issue `08` 的 H4 假设; ADR 0002 §未决 1 | **Disproved 2026-09-17** | The write breakpoint works. First-ever positive control for a write breakpoint (`dr7_q5_ab.py`, log `dr7Q5_q5b.txt`): encoding read back as `Dr0=target VA, Dr7=0xd0001` (RW0=01 write, LEN0=11 4-byte, L0=1) and the breakpoint **fired twice** at `@2.366s` on the main thread. Real cause of the 0 hits is thread coverage: `hwbp_data.py` only arms threads created *after* `main.dll` loads (`main_base` is set in the LOAD_DLL branch, but the main thread's CREATE_PROCESS precedes that load), and the writer **is** the main thread — Q5 attributes all 40578 execution hits before `@2.012s` to thread 32800, the same thread that produced the write hits. Historical logs are therefore **not** voided; their `命中总数: 0` correctly reports "no write observed on the threads this script actually armed", and must not be read as "the address was never written". See `.scratch/probe-arch-refactor/findings-hwbp-zero-hit.md`. |
| `WriteProcessMemory` from the debugger is a valid way to trigger a hardware data breakpoint | Implied by issue `08` 的 Q2 设计（「手动在该地址上做一次已知的写操作」） | **Disproved 2026-09-17** | Six external writes landed successfully (`ok=True written=4`, target value verified changed each time) across 19 threads armed with a write breakpoint, and produced **zero** hits. Meanwhile the sample's own write on the main thread fired the same breakpoint twice in the same run. So external writes are *not* a usable excitation source for write-breakpoint controls; a control built on them would falsely conclude the breakpoint is dead. See `dr7Q5_q5b.txt`. |
| `hwbp_data.py`'s two logs come from one code generation | Implied by any old/new log comparison over this script | **Corrected 2026-09-17** | They come from two. `hwbpData_d1.txt`'s summary heading is `-- 属性名 x 调用者 频次 --`; `hwbpData_wa.txt`'s is `-- 写入者频次 --`, which matches the current file's `L("-- 写入者频次 --")`. Both show 0 hits so the finding is unaffected, but a future diff must not treat them as one generation. (Carried over from `findings-dr7-gd.md` §9.) |
```
