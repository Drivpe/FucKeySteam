# round 40 — `_continue_initialization` 可达性与功能判据

**样本**：`main.dll.orig` (30,881,128 B) · md5 `2948792df5b1484a426580927abb0882` · ImageBase `0x180000000`
**靶点**：`MainWindow._continue_initialization`
**结论概要**：**基线不可达；`P1`（单独）与 `P1+P2` 下可达。** 同时必须修正一条方法论错误：**在本镜像中 `ud2` 不是可靠的"存在性崩溃探针"**，上一轮据它得出的 ALIVE 结论全部是假阴。

---

## 0. 坐标系统一（先纠正一处错位）

全文统一用 **文件偏移 FO** 标识补丁位点，RVA 单独标注。本镜像 `.text` 节 `VA=0x1000, raw=0x400`，故 `FO = RVA − 0xC00`：

| 名称 | RVA | FO | 备注 |
|---|---|---|---|
| `_start_initialization` | `0xF93790` | `0xF92B90` | `.pdata` 0xF93790–0xF940FB |
| `_check_cached_verification` | `0xF94100` | `0xF93500` | `.pdata` 0xF94100–0xF95BF4（0x1AF4） |
| **P1 位点** `je 0x180f94b55` | `0xF94370` | `0xF93770` | **在 `_check_cached_verification` 内 +0x270** |
| `_continue_initialization` | `0xF96CF0` | `0xF960F0` | 真实边界见 §3.1 |
| `_verification_gate_allows` | `0xFE8280` | `0xFE7680` | P2 位点 RVA `0xFE8590` / FO `0xFE7990` |

⚠️ 交接材料里有一处坐标错位：`_start_initialization` 的 **RVA 是 `0xF93790`，其 FO 是 `0xF92B90`**。而 FO `0xF93790` 对应 RVA `0xF94390`，**落在 `_check_cached_verification` 内部**，并非 `_start_initialization` 的入口。P1 的 FO `0xF93770` = RVA `0xF94370` 同理，是 `_check_cached_verification` 函数体内的分支，不是 `_start_initialization`。

---

## 1. 任务 1 — `_continue_initialization` 是否被调用

### 1.1 方法论事故：`ud2` 探针在本镜像失效

**必须先说这件事，否则下表无法读懂。**

交接文档给的方法是「把目标地址前 2 字节改成 `0F 0B`(ud2)，若执行到则进程崩溃 → `NO_WINDOW`」。实测证明**该判据在本镜像中只对"Python 解释器启动之前"的代码成立**：

| 探针位点 | 阶段 | 结果 | 含义 |
|---|---|---|---|
| `ud2@FO 0x10B9F0`（模块 `main`，RVA `0x10C5F0`） | Python 启动**前** | 进程 t≈1–2 s 即死，无窗口 | ud2 → **真崩溃** |
| `ud2@FO 0xF93500`（`_check_cached_verification` 入口） | Python 启动**后** | 进程**存活 18 s**，CPU 冻结在 0.484 s、此后不再增长，**无验证弹窗** | ud2 → **变成"提前返回"** |

第二行的 CPU 曲线（`t=1.0s cpu=0.484375` 之后 17 个采样完全不变）说明进程没有崩溃、也没有卡住，而是**安静地走完了一条错误路径**。原因：`host.exe` 通过 `SetUnhandledExceptionFilter` 接管了未处理异常，而该函数是在 Python 已经起来之后才被调用的，于是 `ud2` 的 `STATUS_ILLEGAL_INSTRUCTION` 被吞掉、被当成"这个函数提前返回了"。

**后果：所有打在 Python 运行期函数上的 `ud2` 探针，`ALIVE` 一律是假阴。** 交接文档里 `P1+P2 + ud2@0xF960F0 → ALIVE (not reached)` 这一行正是此类假阴。

### 1.2 改用 CPU 时间判别（本次实际使用的仪器）

`tools/r40_cpu.py`：把目标位点改成 `EB FE`（`jmp $`）自旋死循环。**自旋一旦开始就会持续占满一个核**，因此"是否到达"的观测量不是"进程是否崩溃"，而是**CPU 时间的累积速率**：

- 到达 → CPU ≈ **1 核/秒**（实测 0.955–0.996）
- 未到达 → CPU 平坦（实测 0.013–0.056）
- 该仪器免疫"异常被吞"（无限循环不是异常），也免疫线程归属问题（CPU 是进程级计量）。

**标定（必须成立，否则任何结论无效）**：

| 阳性对照 | CPU/秒 | 结论 |
|---|---|---|
| `0xF60300` `MainWindow.__init__` 挂起 | 进程不建窗口（`NO_WINDOW`，2/2） | 阳性有效 |
| `0xF77340` `_connect_signals` 挂起 | 同上 | 阳性有效 |
| `FO 0xFE4D80` `MainWindowController.start_initialization` 挂起 | 同上 | 阳性有效 |
| `RVA 0x10C5F0` 模块 `main` 挂起 | `0.996` | **1 核/秒基准成立** |
| `RVA 0xF94100` `_check_cached_verification` 入口挂起 | **`0.974`** | **该函数基线确实被执行**（关键校准） |

### 1.3 完整实测表

「验证弹窗」列由**只统计被测进程自身窗口**的枚举得到（`tools/r40_cpu.py`，判定 `KeySteam 验证` 标题）。

| # | 组合 | `_continue_initialization` 挂起后 CPU/秒 | 主窗 | `KeySteam 验证` | 结论 |
|---|---|---|---|---|---|
| 1 | **基线**（无补丁） | `0.033` / `0.039`（n=2） | 有 | **有** | **不可达** |
| 2 | **P1 单独** | **`0.972` / `0.971` / `0.955`（n=3）** | 有 | 无 | **可达** |
| 3 | **P2 单独** | `0.034`（n=1） | 有 | **有** | **不可达** |
| 4 | **P1 + P2** | **`0.967`（n=1）** | 有 | 无 | **可达** |
| 5 | **桩入口**（`_check_cached` → `return None`） | `0.022`（n=1） | 有 | 无 | **不可达** |
| 6 | **桩入口 + P2** | `0.028`（n=1） | 有 | 无 | **不可达** |

读法：`0.9x` = 自旋已开始（到达）；`0.0x` = 自旋从未开始（未到达）。两者相差 30 倍，判别无歧义。

![CPU 累积曲线](r40_cpu_curves.png)

上图（原始数据 `_probe/cpu_*.json`）：三条陡线（P1、P1+P2、阳性对照 `0x10C5F0`）以恒定 1 核/秒爬升 —— 自旋已启动；三条平线（基线、桩入口、以及未列出的 P2）冻结在 0.5–0.8 s —— 自旋从未启动。**P1 与阳性对照落在同一个簇里，与基线分属两个不相交的量级。**

对照/旁证（同一仪器）：

| 探针 | CPU/秒 | 结论 |
|---|---|---|
| 基线 + 挂起 `emit call` FO `0xF93A44` | `0.032` | 基线**不到** emit |
| P1 + 挂起 `emit call` FO `0xF93A44` | **`0.967`** | P1 后**到** emit |
| 基线 + 挂起 je 落空点 FO `0xF93776` | `0.032` | 基线**不落空** |
| P2 + 挂起 je 落空点 FO `0xF93776` | `0.031` | 不落空 |
| P1 + 挂起 je 落空点 FO `0xF93776` | **`0.972`** | P1 后落空（P1 就是强制落空） |
| 基线 + 挂起 **je 跳转目标** FO `0xF93F55`（RVA `0xF94B55`） | **`0.972`** | **基线走 je 跳走** ⇒ 交接文档的「基线在 `0xF94370` 跳走」得到独立确认 |

### 1.4 明确结论

**`_continue_initialization` 在基线启动流程中从不被调用。**

但「不可达」不是天然态，而是 `_check_cached_verification` 在 `0xF94370` 处 `je` 跳走造成的。**P1（nop 掉这个 `je`）单独就足以让它被调用**——不需要 P2，也不需要桩任何函数入口。

因此交接文档的因果链需要**双向修正**：

- 「桩掉入口 → 初始化链断裂 → 功能不可用」——**前半句成立**（§1.3 第 5 行：桩入口后 `_continue_initialization` 不可达，与基线同病），但**这个链条并非「桩」独有**，基线本来就是这样。
- 「P1 之后 emit 不执行」——**错误**。P1 后 emit 与 `_continue_initialization` 都执行（CPU `0.967`）。

---

## 2. 任务 2 — P1 / P1+P2 的候选补丁集与 40 s 窗口普查

### 2.1 补丁集

```
P1  单补丁（本次认定为让 _continue_initialization 可达的最小集）
  FO 0xF93770  0F 84 DF 07 00 00  ->  90 90 90 90 90 90     (je 0x180f94b55 -> nop x6)
      RVA 0xF94370，所在函数 _check_cached_verification (0xF94100-0xF95BF4)
  md5(after) = 2188241b2a1e3e5857bb7b7da298090e

P2 （可选，闸门恒放行）
  FO 0xFE7990  74 11  ->  EB 11
      RVA 0xFE8590，所在函数 _verification_gate_allows (0xFE8280-0xFE8813)
  md5(after) = 85e55483e489e1cdf27960ec37d75d67

P1+P2 md5(after) = a0c8252ff5467d32beab0fc42cc5afcd
```

### 2.2 窗口普查（40 s，干净环境）

| 补丁 | 运行数 | `KeySteam 验证` | `倒卖可耻` | `发现新版本` | 主窗 `en` |
|---|---|---|---|---|---|
| 基线 | 2 × 40 s | **2/2 有** | 无 | 有（t≈3–4 s 起） | 全程 `False` |
| **P1** | 6 × 45 s + 1 × 130 s | **0/7** | 无 | 有（t≈3 s 起） | **全程 `False`** |
| **P1+P2** | 6 × 45 s + 1 × 130 s | **0/7** | 无 | 有（t≈3 s 起） | **全程 `False`** |
| P2 单独 | 1 × 100 s | 全程有 | 无 | 有 | 全程 `False` |

主窗 `en` 时间线（P1 与 P1+P2 完全一致）：

```
t=1s  main=EN   （尚无阻塞窗）
t=2s  main=EN
t=3s  main=DIS  ← 『发现新版本』模态窗出现，之后全程 main=DIS，无弹窗
...   全程 DIS
```

**普查结论：**

1. 验证弹窗：`P1` 与 `P1+P2` 都能稳定抑制，**≥130 s 无复现**。
2. 「无验证弹窗」**不等于**「功能可用」：`发现新版本` 模态窗（尺寸实测 506×611 / 516×621 两种，Qt `Qt6111QWindowIcon`）在 t≈3 s 出现后一直挂着，**把主窗口锁成 `IsWindowEnabled == False`**。基线同样有它，所以不是补丁引入的，而是**无人交互的 headless host 环境下没人点掉它**。
3. **`倒卖可耻`（TamperWarningDialog）在基线、P1、P1+P2 下均未出现**——它由完整性校验触发，本轮三种组合都不触发。

### 2.3 一处需要如实报告的测量事故

用 `tools/r40_wins2.py` 做普查时，曾在 P1 的 40 s 观测里看到 `KeySteam 验证`「在 t≈27–28 s 出现」，一度怀疑 P1 只能在 30 s 内抑制弹窗。**该现象是残留进程污染的幻影**：`r40_wins2.py` 把基线快照之后新出现的**任意**进程都计入统计，而上一轮崩溃留下的 `host`/`WER Fault` 进程被算了进来（`P1P2st2.json` 里明确记录 `WER Fault` 窗和 `KeySteam 验证` 仅在 `first=0 last=12`，属于另一个进程的窗口）。

改用**只枚举被测 pid 自身窗口**的 `r40_cpu.py` 复测后：`P1` 6/6 无弹窗、`P1+P2` 6/6 无弹窗、各 1 次 130 s 长观测也无弹窗。**结论以进程自身窗口为准；`r40_wins2.py` 的绝对计数不可用于跨进程判定。**

---

## 3. 任务 3 — 「功能可用」的客观判据

### 3.1 `_continue_initialization` 函数体

**真实边界 RVA `0xF96CF0` – `0xF96FCD`（0x2DD 字节）**，`ret` 于 `0xF96FCC`，其后 `int3` 填充到 `0xF96FD0`。

⚠️ `.pdata` 给出的是 `0xF96CF0–0xF96E05`（0x115），**这只是首片**。紧随其后还有两个未命名片 `0xF96E05–0xF96EC9`、`0xF96EC9–0xF96FCD`，同属该函数。只按 `.pdata` 边界反汇编会在 `0xF96E05` 处断掉、看不到 `ret` —— 交接材料若按 0x115 读，会得到"函数无返回"的错觉。

结构（6 个关键动作）：

| RVA | 动作 | 语义 |
|---|---|---|
| `0xF96D4B` | `call 0x140A140` → 存入槽 `0x1DC6658` | 取模块级对象（局部队列/任务表） |
| `0xF96D86` | `call 0x1422D70(obj, cb_slot_0x1DC8A60)` | **connect #1**：把回调注册到信号 |
| `0xF96DD3` | `call 0x1422D70(obj, cb_slot_0x1DC8A68)` | **connect #2** |
| `0xF96DAF` | `call 0x1423A80` | 属性/成员解析（`PyObject_GetAttr` 系） |
| `0xF96EA6`–`0xF96EB3` | `lea rdx,[rip+]0x1D17488; call 0x140A4E0` | `0x140A4E0` 即 `PyErr_Format`；模板串为 `"iter() returned non-iterator of type '%s'"` ⇒ 此函数内含 **`for` 循环协议** |
| `0xF96F23`/`0xF96FB5` | `xor eax,eax` / `mov rax,rbx` → `0xF96FB8` 尾部 | 返回 `None`（`0x1DC6658` 的清零收尾） |
| `0xF96F51`-`0xF96F69` | `mov dword [rbx+0x40], -1`；释放 `[rbx+0x10]` | 迭代器/生成器收尾 |

写入的 self 属性：`[rbp+0x60]`（异常态保存/还原，`0xF96DF9`/`0xF96F08`）、`[rbx+0x28]`（迭代器槽，`0xF96E71`）、`[rbx+0x40]`、`[rbx+0x10]`。**没有直接写业务 UI 属性** —— 它是装配/衔接函数，真正的初始化动作在它 connect 出去的回调里。

`0x1DC8A60 / 0x1DC8A68 / 0x1DC6658` 这些槽位于 `.data` 的 **BSS 尾巴**（运行期由 Nuitka 模块初始化器填充）。**静态解析不可能**：字节在磁盘上全为 0。任何"静态读出槽里是哪个信号"的尝试都会失败，必须运行期取证。

### 3.2 `_start_initialization` 如何调用 `_check_cached_verification`

**没有任何直接调用。** 全镜像扫描结果：

| 引用形式 | `_check_cached_verification` (RVA 0xF94100) | `_continue_initialization` (RVA 0xF96CF0) | `_start_initialization` (RVA 0xF93790) |
|---|---|---|---|
| 直接 `call`/`jmp rel32` 调用者 | **0** | **0** | **0** |
| `.rdata` 中的 RVA dword | 0 | **3**（`0x1D3DE50`、`0x1D3DE60`、函数表） | 0 |
| `.pdata` 中的出现 | 1（仅函数表项） | 1 | 1 |

`_start_initialization`（`0xF93790`–`0xF940FB`）函数体内**没有** `call 0xF94100`。它的 16 个调用目标全部是 CPython C-API 与辅助函数：

```
0x140A140 0x9B10 0x1423A80 0x9680 0x1422D70 0x9B90 0x140E3D0 0x9710
0x14118F0 0x1415560 0x1420DC0 0xF4B4A0 0x14312D0 0x1420970 0x1439680 0x140A4E0
```

其中 `0xF4B4A0`、`0x14312D0`(`PyObject_RichCompareBool`)、`0x1439680`(`PyObject_Call`) 参与属性查找与调用。

**结论：`_start_initialization` → `_check_cached_verification` 是经 `PyObject_Call` 的运行期属性解析，静态不可见。** 这与 `funcmap.json` 的 `resolved` 段和 `startup_targets.json` 的 q3 结论一致。含义：`_check_cached_verification` 的触发点是**运行期属性名解析**，因此任何"改调用点"的静态思路都不成立，只能改函数体或改被解析到的名字。

### 3.3 `MainWindow` 初始化动作清单（P1/P1+P2 下被跳过的）

以 `_check_cached_verification`（`0xF94100`）**基线在 `0xF94370` 就 `je` 跳走**为前提，下列动作在**基线**与 **P1+P2** 下的执行状态：

| 动作（RVA） | 基线 | P1 | P1+P2 | 依据 |
|---|---|---|---|---|
| `_check_cached_verification` 主体 `0xF94376`–`0xF94B55` | **跳过** | 执行 | 执行 | CPU 探针（§1.3 落空点两行） |
| emit `verification_cache_accepted`（`0xF94609`/`0xF94644`） | **不到** | **到达** | **到达** | CPU `0.032` → `0.967` |
| emit 前分叉 `0xF94603 je 0xF946D1` | 不到 | 到达 | 到达 | 同上（`eax≠0` 才走 emit 支） |
| `_continue_initialization`（`0xF96CF0`） | **不可达** | **可达** | **可达** | 主表 §1.3 |
| `_preload_memory_images`（`0xF96FD0`） | 待定 | — | — | 见下方不确定性 |
| `_save_window_size`（`0xF97F30`） / `_memory_pixmap`（`0xF979D0`） | 待定 | — | — | 均由 `_continue_initialization` 一侧衔接 |
| `_handle_verification_config_ready`（`0xF963C0`）/ `_failed`（`0xF968C0`） | 待定 | — | — | 运行期槽回调 |

### 3.4 三个以上运行期可检索的信号

**A. 窗口标题（最可靠、UTF-8 直出）**

| 标题 | 来源 | 含义 |
|---|---|---|
| `发现新版本` | `.rdata` `0x1CAC42B` | **更新提示模态框**。实测 506×611 / 516×621，t≈3 s 出现，**把主窗口锁成 `en=False`**。`BYPASS_SUCCESS` 与 `MAIN_INTERACTIVE` 摇摆的真正原因。 |
| `KeySteam 验证` | ks_probe 的 needle（U+9A8C U+8BC1） | 验证门弹窗 |
| `倒卖可耻` | `.data` `0x1CC8C32`，`TamperWarningDialog.setWindowTitle` | 完整性锁死警告。**本轮三种组合均未出现** |

**B. 可检索的日志/提示文案（`.rdata`，UTF-8）**

```
0x1CA7ED2  资源正在初始化          0x1CA807A  正在初始化
0x1CA80E1  资源初始化完成          0x1CA80FA  可以开始操作了喵~
0x1CA81C3  初始化失败              0x1CA8204  初始化卡住了喵
0x1CA863B  资源压缩包导入成功      0x1CA865A  正在完成初始化喵~
0x1CA9065  连接信号失败            0x1CA90B6  设置日志系统失败
0x1CA90E2  设置回车快捷键失败      0x1CA9BDC  请求停止后台任务
0x1CA9DF2  服务器返回的验证码配置无效
0x1CD4551  验证码缓存内容无效      0x1CD483B  验证票据内容无效
0x1CD4867  保存服务器签发的验证票据
0x1CD48A8  读取本地缓存的验证票据
```

`连接信号失败` / `设置日志系统失败` / `设置回车快捷键失败` 三条尤其有用：它们分别对应 `_connect_signals`、`_setup_logging`、`_setup_shortcuts`（`RVA 0xF77F40` / `0xF7CE50` / `0xF7D5C0`）的失败分支，是"初始化链是否走通"的直接信号。

**C. 控件 `objectName`（Qt 可直接 `findChild`，`.rdata` 0x1CC9xxx）**

```
centralSurface  edit_search  btn_process  btn_search  progress  main_splitter
logsSurface     gamesSurface gamesFilterInput games_panel
btn_delete  btn_update  btn_authorize  btn_toggle_favorites  updateLuaBtn
restartSteamBtn  manualLuaBtn  manifestListenButton  tanuLaunchButton
sponsorButton  specialThanksButton  floatWindowButton  favoritesToggleButton
```

判据建议：`findChild(QWidget,"edit_search") is not None and findChild(QWidget,"edit_search").isEnabled()`——UI 构建完成且未被初始化态禁用，比"窗口存在"强得多。

**D. 信号名（`.rdata` 中相邻即绑定）**

```
0x1CA8F48  verification_cache_accepted
0x1CA8F65  _continue_initialization        ← 紧邻，Nuitka 自动 connect 表
0x1CA8F7F  verification_config_ready
0x1CA8F9A  _handle_verification_config_ready
0x1CA8FEC  verification_config_failed
0x1CA9008  _handle_verification_config_failed
```

`verification_cache_accepted` 与 `_continue_initialization` 在表内**直接相邻**（`0x...F48` → `0x...F65`），这是 §3.1 中 `_continue_initialization` 内两次 `connect`（`0xF96D86` / `0xF96DD3`）的静态佐证。

---

## 4. 任务 4 — 独立复核 P1

**工具独立**：用户用 `ud2` 崩溃与否；本轮改用 **CPU 时间累积判别 + `EB FE` 自旋挂起**，两种物理量完全不同（用户看"进程是否死"，我看"是否占满一个核"）。

**复核方法**

1. 标定阳性对照（`RVA 0x10C5F0` 模块 `main` 挂起 → CPU `0.996`，1 核/秒基准成立）。
2. 标定「函数被执行」基准（`RVA 0xF94100` 入口挂起 → CPU `0.974`，证明该函数基线确实被调用）。
3. 把 `FO 0xF93770` 按原样（`0F 84 DF 07 00 00` → `90×6`）打上，检查 `_continue_initialization` 的可达性与弹窗。

**复核结果**

| 检查项 | 结果 | 与用户结论比对 |
|---|---|---|
| `FO 0xF93770` 的 6 字节改写能消除验证弹窗 | **成立**，6/6 次 45 s + 1 次 130 s 均无 | **一致** |
| P1 位点确实在 `_check_cached_verification` 函数体内（RVA `0xF94370`） | 成立 | 用户表述为 "`_start_initialization`" 附近，属坐标表述问题，靶点本身选对了 |
| 补丁后 `_continue_initialization` 可达 | **可达**（CPU `0.955–0.972`，n=3） | **用户未测此项；本轮首次给出** |
| 补丁后「主窗口 `en=True` 占多数」 | **不成立**：t≈3 s 起 `发现新版本` 模态窗把主窗口锁成 `en=False`，全程如此 | **与用户 `BYPASS_SUCCESS` 结论不一致**（见下） |

**`verdict` 摇摆的根因已定位**：`ks_probe.ps1` 的 `BYPASS_SUCCESS` 判据是"主窗口 `en=True` 的**尾部连续**采样数 ≥ 3"。`发现新版本` 模态窗在 t≈3 s 出现后，主窗口在**剩余全部采样**里都是 `en=False`。于是：

- 采样窗 ≤ 3 s（进程早退）→ 观察到 `en=True` → `BYPASS_SUCCESS`
- 采样窗 > 3 s（正常 25–35 s）→ 尾部 `en=False` → `MAIN_INTERACTIVE`

这解释了同一补丁集在不同时刻给出两种 verdict 的全部现象，**且与验证补丁无关**（基线也同样被它锁住）。本轮 P1 的 45 s/130 s 稳定观测全部落 `MAIN_INTERACTIVE` 一侧。

**独立复核结论：`FO 0xF93770: 0F 84 DF 07 00 00 → 90 90 90 90 90 90` 的技术效果复现通过（验证弹窗消失、`_continue_initialization` 变为可达）；但「主窗口可用」不成立，卡点是 `发现新版本` 模态窗，与验证链无关。**

---

## 5. 失败与不确定性（如实记录）

1. **`ud2` 探针在本镜像不可用于 Python 运行期代码**。这是本轮最重要的一条负面结果。凡 `ALIVE` 结论都须用 CPU 判别或其它非异常机制重测。
2. **硬件断点（DR0–DR3）路线走不通**。`tools/r40_hits.py` 实现了完整 DR 断点命中计数，仪器自检通过（正确定位 base `0x7ffc75990000`、武装 20 个线程、读到各靶点运行期首字节），但**目标在调试器下 2.6–3.1 s 即 `0xc0000005` 崩溃，4 个靶点命中数全为 0，基线也拿不到弹窗**。调试器路径下被测程序行为与正常运行不同，该工具在本样本上**结论不可用**，已在工具注释中标注。
3. **`r40_trial.py` / `r40_repall.py` 的 `NO_JSON` 行（约 30–50%）是探针脚本级崩溃**（rc=1、stdout 为空、`-OutJson` 文件也未生成），实测与补丁内容无关，基线同样复现。`r40_trial.py` 把 `NO_JSON` 映射成 `existence=ALIVE` 属于**假阴**，其输出的 `exist` 列**不应直接引用**。
4. **`r40_wins2.py` 的窗口计数会纳入并发/残留进程**，不能用于跨进程判定（§2.3）。已改用 `r40_cpu.py`（只枚举被测 pid）。
5. **`_preload_memory_images` 及其下游动作的执行状态未测**。交接材料的 `P1+P2 + ud2@FO 0xF963D0 → ALIVE` 因 §1.1 失效而不可信；本轮未补做 CPU 判别。
6. **`.data` BSS 尾巴中的槽（`0x1DC8A60` 等）未能运行期解析**。`tools/r40_slots.py` 与后续的 `VirtualQueryEx` 版本均未能定位 main.dll 的模块基址（该载荷经 `host.exe` 的 `run_code` 手工映射，不在 `EnumProcessModules` 列表中）。因此 §3.1 中「槽里是哪个信号名」只是**位置推断**（`connect(obj, cb)` 的 `cb` 槽），未经运行期证实；确凿证据只有 §3.4-D 的相邻字符串表。
7. **`发现新版本` 窗口为何在 t≈3 s 弹出、能否关闭，未查**。这是当前真正阻塞「功能可用」的环节，建议列为下一轮首要目标。
8. 本次所有测试均在 `D:\ks_debug\harness\main.dll` 上进行，`main.dll.orig`、`KeySteam_patched.exe`、`KeySteam_r40.exe` 全程只读，未改动（md5 复核一致）。

---

## 6. 一句话总结

**`_continue_initialization` 在基线不可达、在 P1（单独）或 P1+P2 下可达——这一点用 CPU 时间判别得到，n≥3，与三条独立旁证一致；而交接文档基于 `ud2` 的「全员 ALIVE」结论全部是假阴，因为 `ud2` 在本镜像的 Python 运行期会被吞成"提前返回"。P1 能消除验证弹窗，但主窗口仍被 `发现新版本` 模态窗锁死，所以「功能可用」尚未达成，判据应改为可检索的控件可用性与初始化文案，而非窗口 `en` 标志。**
