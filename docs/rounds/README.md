# `_re/ghidra/` 脚本与产物索引

本目录是 **KeySteam v2.99 静态分析 + 运行期调试**的工作区（882 MB，2026-09-16/17 一轮密集产出）。
本文件是该目录**唯一**的 `.md`，用途有二：**索引**（谁是什么）与**归档策略**（什么能删什么不能删）。

> 本目录**不在 git 仓库树内**（`_re/` 不是 `keysteam-unlock-spike` 的一部分），
> 故无版本控制保护 —— 这份索引就是唯一的可读性凭据。

---

## 一、目录结构

| 路径 | 内容 |
|---|---|
| `tools/` | **静态分析工具**（capstone + 直接读 DLL）。19 个脚本（含 `binlib.py`），**全部可在 Linux 跑** |
| `*.py`（根，80 个） | **运行期调试器 / 驱动脚本**（ctypes 调 Win32）。**Windows 专用，Linux 下无法执行** |
| `*.bat` | 脚本启动器（提权 + 日志重定向），与同名 `.py` 配对 |
| `*.ps1` | PowerShell 侧探测（x64dbg headless 驱动、进程监视、提权） |
| `*.txt` | **运行输出**（89 个）。多为同名脚本的 stdout/日志 |
| `*.rips` | RIP 命中记录（`mydbg2.rips` 13.8 MB 为最大单文件） |
| `ks_analysis.rep/`、`main_dll.rep/` | Ghidra 工程仓库 |
| `out/`、`scripts/` | 早期产物 |

---

## 二、`tools/` —— 静态分析工具（Linux 可跑）

### 共享模块

| 文件 | 职责 |
|---|---|
| **`binlib.py`** | **二进制元数据的唯一来源**：节表、`.pdata` 函数边界、RIP 相对扫描、常量池 blob 解析、路径常量、描述符表/初始化器锚点。改一个偏移只需改这里（#19 AC1） |

### 沿「Nuitka 常量池装配链」推进的工具

推导链：**模块描述符表 → 模块函数 → `mod_consts` → 槽 → 消费指令**

| 文件 | 作用 |
|---|---|
| `candidateA.py` | 从描述符表找 `src.gui.*` 模块，经 `lea rdx,[rip+mod_consts]`+`call INIT` 取 `mod_consts` |
| `find_consumers.py` | 全 `.text` 搜 `lea→BSS + call INIT` → 334 个候选基址；再找消费指令（1134 条） |
| `find_init.py` | 找 `createModuleConstants`（同函数内对同一 `.data` 目标多次 `lea`） |
| `find_mw.py` | 解析 `main_window` 池（1609 条）→ 条目序号即槽号 |
| `map_slots.py` | 解析 `verification_dialog` 池（351 条）→ 槽号 → 消费指令 |
| `bss_scan.py` | 扫 `.data` BSS 未初始化区的 RIP 引用（72895 个目标） |
| `ksdis.py` | 通用反汇编器（有 CLI：`ksdis.py <va> [count]` / `find <hex>`） |

### 定位 / 校核

| 文件 | 作用 | 状态 |
|---|---|---|
| **`rederive.py`** | **地址重导的唯一凭据**。四步链实时从原样本算出并与期望值比对：`16 项一致 / exit 0` | **有效** |
| `final_verify.py` | 改为 `rederive.py` 的**薄封装**（原版地址表是字面量硬编码，只重印不重导） | 已修正（#19） |
| `locate_mw_mc.py` | 用 8 个已知槽号反查 `main_window` 的 `mod_consts` | **定位法已否证**：327 个候选同为 8/8，无区分力（见下「负结果」） |
| `locate_mw2.py` | 用池条目数间隔约束反查 | 部分有效：间隔约束有区分力 |
| `disasm_A.py` | 反汇编候选 A 失败分支，标注槽引用 | 已修正（原硬编码 `0x181dac280` 是错的） |

### 扫描 / 形态检索

| 文件 | 作用 | 方法论 |
|---|---|---|
| `fullscan.py` | 任意操作码的 RIP 相对引用 → `.rdata` | 含阳性对照 |
| `fullscan2.py` | 同上，按 `.pdata` 分段 | 含阳性对照 |
| `rvarefs.py` | **4 字节 RVA** 形态的池引用（507 条） | 含阳性对照 |
| `iat_trace.py` | 从 IAT 名字串反查调用点 | 含阳性对照 |
| `modconsts.py` | 零槽法打分定位 `mod_consts` | **已否证**：真值落在 BSS，本脚本只读 `.data` 文件区，结构上不可能命中（见下「负结果」） |

---

## 三、根目录脚本 —— 按技术路线分组

> 每组内**按版本号列出**，每个迭代版都带演进 docstring，记录了上一次的失败原因。
> **这些迭代版是决策链的依据，一律归档不删**（见第四节）。

### A. x64dbg headless 驱动路线（`drive*.py` + `*.ps1`，2026-09-16 17:40–18:43）

`drive.py` → `drive2.py` → `drive3.py` → `drive4.py` → `drive5.py` → `drive6.py` → **`drive7.py`**（最终版）
配套：`t.ps1`…`t16.ps1`（16 个逐步试探）、`win.ps1`、`enum_run.ps1`、`winenum2.ps1`
输出：`hout*.txt`、`trace*.txt`（8 个）、`o*.txt`

**结局**：路线放弃（headless 无法可靠捕获内存访问断点），转向自写调试器。

### B. 自写调试器路线（`mydbg*.py`，22:13–22:37）

`mydbg.py` → `mydbg2.py` → `mydbg3.py` → `mydbg4.py` → `mydbg5.py` → **`mydbg6.py`**

- `probe_lib.py` —— **核心库**（页保护断点原理：`PAGE_READONLY|PAGE_GUARD` → `STATUS_GUARD_PAGE_VIOLATION` → 恢复 + 单步 + 重装 GUARD）
- `mydbg6.py` 关闭 guard-page arm，验证「纯附加调试器」下进程是否存活
- 输出：`mydbg2.rips`（13.8 MB）、`mydbg*.txt`

### C. 最小调试器 + 反调试判别（`minidbg*.py`、`disc*.py`，22:39–23:52）

`minidbg.py` → `minidbg2.py`；`disc.py`（三组对照 none/one/many）→ `disc16.py` → `disc16b.py`

**`disc.py` 是本路线最关键的对照实验**，也是 #19 AC3 的修复对象：
- 原 `:83` 有静默 fallback（`funcs[0][0] if funcs else base+0x1000`），`one` 组必然落入魔数地址
- **修复 + 阳性对照记录见 [`disc-fix-poscontrol.md`](disc-fix-poscontrol.md)**
- 输出：`disc_none.txt` / `disc_one.txt` / `disc_many.txt`

### D. 函数级执行覆盖（`cov*.py`、`covg*.py`、`x64_*.py`，23:10–00:12）

`covg.py` → `covg2.py`；`cov3.py` → `cov4.py` → `cov5.py` → `cov6.py`
`x64_cov.py` / `x64_many.py` / `x64_final.py`（x64dbg headless 版对照）
`hwbp16.py`（硬件执行断点 Dr0–Dr3，对样本零侵入）

### E. 页保护 / 内存监控（`hit_*.py`、`scan*.py`、`memlog*.py`）

`hit_core.py`、`hit_heap.py`、`hit_heap2.py`、`scan1.py`…`scan4.py`、`scan_str.py`、
`memlog.py` + `memlog_lib.py`、`extmon.py`（纯外部监控，不附加调试器）

### F. 进程内存直读 / 提权

| 文件 | 作用 |
|---|---|
| **`probe_lib.py`** | 调试器核心库；**ctypes 签名的唯一来源**（#19 AC2） |
| `ms.py` | 内存扫描工具库（提权 + `ReadProcessMemory`）。私有 `enable_debug_priv` 副本**已删**（#19 AC2） |
| `memread_test.py` | 验证能否读 kshost 内存。私有副本**已删**，改薄诊断包装（#19 AC2） |
| **35 个探针脚本** | 各自的 `def L(s)` 私有副本**已删**，改为 `L = make_L(<句柄>)`（工单 03）。日志**写哪个文件**仍由脚本自己决定（脚本特有，不进库）。句柄名保留原样：31 个为 `f`，4 个 `mydbg3`–`mydbg6` 为 `out_log` |
| `lf_test.py` / `stage.py` | **不在**上一条范围内：二者的 `L()` 带墙钟时间戳前缀（`[14:23:01]`），是其真实需求，**保留私有实现** |
| `attach.py` / `attach2.py` / `attachdbg.py` | 附加到运行中的 kshost 直读内存 |
| `privesc.py` / `privtest.py` / `elev_test.py` | 提权探测 |
| `ptrscan.py` / `analyze_ptrs.py` / `probe_mem.py` | 指针结构分析 |

### G. 零延迟 arm 与收窄实验（`zero_delay.py`、`zd_*.py`，00:14–00:35）

`zero_delay.py` → `zd_retry.py` → `zd_dlg.py`
`guard_multi.py`、`single_page.py`、`ldltest.py`、`probe_r12.py`、`catch_regs.py`
输出：`zd_*.txt`、`sp_*.txt`、`regs_*.txt`、`r12_*.txt`

### H. 其他小工具

`peek.py`、`stage.py`、`rtest.py`、`verify1.py`、`lf_test.py`、`find1.py`、
`cmds_help.py`、`probe_cmds.py`、`dbg_child.py`、`hlib.py`、`bp2.py`、`bp3.py`、`bp_test.py`

---

## 四、归档策略

### 不删（保留全部迭代版本）

- `locate1/2/3/4.py`、`cov3/4/5/6.py`、`covg/covg2.py`、`drive.py`..`drive7.py`、
  `mydbg.py`..`mydbg6.py`、`disc*/minidbg*/hit_*/scan*/zd_*/bp*`
- **理由**：每个都带**演进 docstring**，记录上一次为什么失败：
  - `locate3.py:3-4` 记 locate2 的失败原因
  - `locate4.py:3-5` 记 locate3 的 `break` bug（去重计数当循环终止条件，命中同址两次就少算）
  - `mydbg6.py` 记 v4 的 0.3s 退出归因
  这些是 `#14`/`#15`/`#19` **决策链的依据**，删掉即失去可审计性。

### 已删（纯噪声）

- `__pycache__/`、`tools/__pycache__/` —— **已于 2026-09-17 清除**（#19 AC4）
- 收尾时若再生成，可安全删除（它们是 `.pyc` 缓存，无信息量）

### 产物命名约定

- 脚本 `X.py` → 输出 `X.txt`（部分脚本带多次运行后缀：`zd_1.txt`/`zd_2.txt`/`zd_3.txt`、`sp_1.txt`…`sp_6.txt`、`regs_1.txt`/`regs_2.txt`）
- `.rips` 文件是 RIP 命中流水（`mydbg2.rips` 13.8 MB ≈ 全量命中，`locate4.txt.rips` 14 B ≈ 空）
- `.bat` 与同名 `.py` 配对；`.bat` 内容通常是「提权 + 执行 + 日志重定向」

---

## 五、负结果登记（本目录产出的、**已否证**的定位法）

> 方法论约定 `docs/agents/domain.md:86`：*an exclusion claim must state which terms were searched*。
> 任何「0 命中」结论必须先做**阳性对照**。以下两条是本目录现有的负结果，均附对照。

### 1. `modconsts.py` 的零槽打分法 —— 不可用于定位

- **主张**：`.data` 里零槽数最多的 8 字节对齐候选即 `mod_consts` 基址
- **否证方式**：阳性对照（已知真值 `verification_dialog` = `0x181dd16a0`，可由 `rederive.py` 独立重导）
- **结果**：真值**不在候选集合中**。原因：真值偏移 = `0x836a0` = 538784 > `rawsize` 59904，
  落在 **BSS 未初始化段**，而本脚本只读 `d[DA_RAW:DA_RAW+DA_SZ]`，**结构上不可能覆盖**
- **检索词表**：检索 `lea` 的 RIP 相对目标落在 `.data` **文件可见区**；**未检索** BSS 区
- **正确路径**：`bss_scan.py` → `find_consumers.py` → `find_init.py` → `rederive.py`

### 2. `locate_mw_mc.py` 的 8 槽约束 —— 不唯一

- **原主张**（docstring 原文）：「351 槽级约束下**唯一**」
- **否证方式**：阳性对照 + 区分度诊断
- **结果**：334 个候选中 **327 个**同时满足 8/8。因 8 个槽号全在 `8*n` 等差格点族上，
  任何落在同族格点的 `lea` 基址都会全中，约束退化为「该基址是否被 `lea` 引用过」
- **正确路径**：唯一性来自 `rederive.py` 的「模块名链 + 池条目数间隔自洽」
  （`main_window` = `0x181dc7420`，其后邻间隔 16784 ≥ `8*1609` = 12872）

---

## 六、方法论约定（本项目强制）

1. **每个结论标注验证深度**：直接观测 / 一层推断 / 多层推断。
2. **排除性结论必须附检索词表** —— 写明搜了哪些词。
3. **任何「0 命中」结论必须先做阳性对照** —— 挑一个应命中的目标验证方法有效，再下排除性结论。

**落实状态**（#19 复核，2026-09-17）：

| 工具 | 检索词表 | 阳性对照 |
|---|---|---|
| `fullscan.py` | 有 | 有（3 个 `.rdata` 字符串锚点） |
| `fullscan2.py` | 有 | 有 |
| `rvarefs.py` | 有 | 有（RVA 解码自检） |
| `bss_scan.py` | 有 | 有（已知槽消费指令） |
| `find_init.py` | 有 | 有 |
| `find_consumers.py` | 有 | 有（已确证 `verification_dialog` 锚点） |
| `locate_mw_mc.py` | 有 | 有（**并否证自身唯一性主张**） |
| `locate_mw2.py` | 有 | 有 |
| `modconsts.py` | 有 | 有（**并否证自身定位法**） |
| `map_slots.py` | 有 | 有（槽 6/10/25 锚点） |
| `patchpoint.py` | 有 | 有（3 条消费指令锚点） |
| `find_mw.py` | 有 | 有（7 条槽号锚点） |
| `iat_trace.py` | 有 | 有 |
| `disasm_A.py` | 有 | 有（`mod_consts` 与期望值比对） |
| `candidateA.py` / `ksdis.py` | 有 | 见 `binlib` 口径 |

> 本轮修复前，`tools/` 下**零个**工具记录检索词表、**仅 `rvarefs.py`** 有阳性对照（且是事后补的）。
> 现 15/15 覆盖。（`rederive.py` 与 `binlib.py` 本身是判据来源，不需要。）

---

## 七、如何运行

```bash
# 静态工具（Linux / Windows 均可；只需 capstone）
cd tools/
python3 rederive.py           # 地址重导回归：期望 16/16 一致、exit 0
python3 find_consumers.py     # 重跑「334 候选 + 1134 消费点」
python3 map_slots.py          # 重跑池解析（351 条）
```

```powershell
# 运行期调试器（需 Windows + 管理员；采样脚本示例）
Start-Process -Verb RunAs python.exe disc.py one
# 输出落在 _re\ghidra\disc_one.txt
```

**样本路径**：默认取 `KS_MAIN_DLL` 环境变量，未设时用仓库内
`_re/work/payload/main.dll`（源文件哈希 `cc869941663ed46bc8973bc18415d2cabd6e6fe7127a7d692fda450cdc405265`）。

---

## 八、相关文档

- `.scratch/run-20260916-102001/review-ticket-15.md` —— `#15` 双轴代码审查记录（本索引的大部分整改来源）
- `.scratch/run-20260916-102001/findings.md` —— `#15` 主成果
- `disc-fix-poscontrol.md` —— `disc.py` 静默 fallback 修复与阳性对照
- `docs/agents/domain.md` —— 方法论约定（检索词表 / 阳性对照）
