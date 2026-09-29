# Round 40 — 「倒卖可耻」篡改警告框：触发源判定与函数内分支级收口

**结论先行**：警告框已消除，**135 秒实测通过**。最终改动只有 **4 字节**，追加在既有 9 条基础补丁之后。

```
--patch 0xF7659F:0F:E9 --patch 0xF765A0:84:F7 --patch 0xF765A1:F6:0A --patch 0xF765A2:0A:00
```

即 RVA `0xF7719F` 处 `0F 84 F6 0A 00 00`（`je`）→ `E9 F7 0A 00 00`（`jmp`）。

**可用产物**：`D:\ks_debug\r40w\KeySteam_r41_gatefix.exe`，md5 `d3b36db6e75da66718edf7ee968f1eef`
（未覆盖 `KeySteam_patched.exe` / `KeySteam_r40.exe` / `KeySteam_r40x1.exe` / `KeySteam_r40x2.exe`）

---

## 一、方法论：为什么必须换判据

### 1.1 静态 xref 在本样本上恒为零（已复现）

对全部候选靶点做直接调用者搜索，结果**一致为 0**：

```
MainWindow.show_tamper_warning      rva=0xF77020   callers=0
MainWindow._apply_integrity_result  rva=0xF769B0   callers=0
RuntimeGuard._trigger_tamper        rva=0x1123B40  callers=0
RuntimeGuard._run_loop              rva=0x111F290  callers=0
IntegrityService.verify_local_installation  rva=0x10F6CC0  callers=0
TamperWarningDialog.__init__        rva=0x10B3F90  callers=0
（共 13 个靶点，全部 callers=0）
```

原因：Nuitka 冻结后，每一次 Python 级调用都编译成

```
mov  r8, [rip+disp]     ; 从 .data 取「槽」——磁盘镜像全 0，导入期才填
call 0x181422d80        ; 通用 pyobject_call
```

方法对象存在**不可静态求值的槽**里。因此「在反汇编里搜地址/字符串」在本样本上不是低效，而是**结构上无解**。

### 1.2 三次失败尝试（负结果，记录以免重走）

| 尝试 | 结果 | 失败原因 |
|---|---|---|
| 在 `.data` 文件区扫「指向 .rdata 名字表的 qword」 | 解析出 **0** 个槽 | 槽值是**堆上** PyUnicode 指针，比假设多一层间接 |
| 整数线性反汇编整段 `.text` 找槽引用 | 64 个槽只命中 **3** 个 | 21 MB 代码含跳转表/内联数据，解码器迅速失步 |
| 用调试器（`DEBUG_PROCESS`）下硬件断点取调用者 | 目标 **1 s 内自杀** | 本样本有反调试；且 onefile 是双进程，`ONLY_THIS_PROCESS` 只挂到引导进程 |

**判据改为**：在**非调试**状态下用 `ReadProcessMemory` 只读取槽值（附加≠调试，不设 DR、不装调试器），再用槽地址反查引用者。

### 1.3 突破点

`CreateToolhelp32Snapshot` 对本目标返回 **错误 5（拒绝访问）**，改用 `EnumProcessModules` 即通过；`OpenProcess` 的 `VM_READ|QUERY` 是可用的（只有 `PROCESS_ALL_ACCESS` 被拒，错误 5）。

由此拿到运行时真实槽名，例如：

```
slot 0x1DC7998  _integrity_locked        slot 0x1DC8150  show_tamper_warning
slot 0x1DC8140  IntegrityCheckResult     slot 0x1DC8148  is_tampered
slot 0x1DD4430  _on_tamper               slot 0x1D5C978  Executor/异常态
slot 0x1DD45D8  _SELF_SCAN_INTERVAL_SECONDS   slot 0x1DD45E0  _scan_self_and_raise
slot 0x1DD45F8  _HEARTBEAT_INTERVAL_SECONDS   slot 0x1DD4600  _send_heartbeat
slot 0x1DD45B8  _start_accept_thread     slot 0x1DD4620  _POLL_INTERVAL_SECONDS
```

**槽地址本身就成了静态锚点**：`0x1DC8150` 是一个可以静态搜索的常量。以 `.pdata` 逐函数边界反汇编（避免失步），扫全部 **17863** 个函数：

```
show_tamper_warning   refs=17  owners=17     <-- 17 个调用点
_integrity_locked     refs=22  owners=21
TamperWarningDialog   refs=8   owners=2
_emit_integrity_lock  refs=6   owners=4
_scan_self_and_raise  refs=4   owners=3
_trigger_tamper       refs=4   owners=3
_on_tamper            refs=3   owners=2
```

---

## 二、触发源静态判定（带 RVA 与字节级证据）

### 2.1 通知汇聚点：`MainWindow.show_tamper_warning`（RVA `0xF77020`）

**这是唯一的总闸**。全部 17 个调用者都汇聚到这里，函数体 `[0xF77020, 0xF77F3A)`：

```
RVA 0xF77183  cmp edi, -1
RVA 0xF77186  jne 0xF7719D            ; 非 -1 => 已算出 locked 布尔
RVA 0xF77188  （-1 分支：抛异常）mov edi, 0x455 ; jmp 0xF77D4E
RVA 0xF7719D  test edi, edi           ; edi = locked
RVA 0xF7719F  0F 84 F6 0A 00 00  je 0xF77C9B   <== 未锁定 => 直接返回
RVA 0xF771A5  ...（_tamper_url_opened / _tamper_dialog / TamperWarningDialog）
RVA 0xF77A8C  call 0x181420dc0        ; 真正构造对话框
```

`0xF77C9B` 是「未锁定」的提前返回路径（读 `_Py_NoneStruct` 后做引用计数收尾）。

⇒ **把 `0xF7719F` 的 `je` 改成 `jmp`，即为「只要未被锁定就直接返回」**。这同时关掉了启动期与运行期两条路径，且**完全不触碰 `RuntimeGuard` 的循环体**，因此心跳照发、watchdog 不会误判杀进程。这正是「桩整个函数入口」会踩的坑，而函数内单分支不会。

### 2.2 两条独立触发路径（与你的实测现象吻合）

**路径 A —— 启动期一次**：`MainWindow._start_initialization`（RVA `0xF93790`）

```
RVA 0xF9382A  mov r8, [<slot>_integrity_locked]
RVA 0xF93834  call 0x181423a80        ; 取属性
RVA 0xF93856  call 0x180009680        ; 真值判定 -> ebx
RVA 0xF9385D  cmp eax, -1
RVA 0xF9389C  test ebx, ebx
RVA 0xF9389E  74 5D  je 0xF938FD      ; ==0 => 跳过弹窗
RVA 0xF938AF  mov r8, [<slot>show_tamper_warning]   <== 启动期弹窗
```

**路径 B —— 运行期周期**：`MainWindow._apply_integrity_result`（RVA `0xF769B0`）

```
RVA 0xF76BBA  mov r8, [<slot>is_tampered]          ; 取 is_tampered 属性
RVA 0xF76BDE  call 0x180009680                     ; 真值判定 -> esi
RVA 0xF76BFA  cmp esi, -1   ; RVA 0xF76C09 test esi,esi ; RVA 0xF76C0B jne 0xF76C21
RVA 0xF76C21  mov r9, [<True>]
RVA 0xF76C2B  mov r8, [<slot>_integrity_locked]    ; self._integrity_locked = True
RVA 0xF76C32  call 0x181423e40                     ; 属性写
RVA 0xF76C37  test al, al
RVA 0xF76C39  75 0A  jne 0xF76C45
RVA 0xF76C45  ...  RVA 0xF76C54 call ............ _disable_protected_actions
RVA 0xF76D2C  test esi, esi
RVA 0xF76D2E  0F 84 8D 02 00 00  je 0xF76FC1       ; 非篡改 => 跳过
RVA 0xF76D7F  75 0A  jne 0xF76D8B
RVA 0xF76D8B  mov r8, [<slot>show_tamper_warning]  <== 运行期弹窗
```

调用链：`MainWindowController._on_runtime_tamper`(`0xFE77D0`) → `_emit_integrity_lock` → `MainWindow._apply_integrity_result`。

### 2.3 RuntimeGuard 体系判定（回答任务 1、2）

| 问题 | 判定 | 证据 |
|---|---|---|
| 扫描什么？ | 注入模块 / 环境异常，**不是** exe 文件哈希 | `_scan_self_and_raise` 运行时槽含 `suspicious_modules_for`、`runtime_injected_module_message`、`_INJECTION_REASON_HOOK`、`_INJECTION_REASON_EXE`、`environ`、`getpid` |
| 命中后发给谁？ | `_trigger_tamper` → 槽 `_on_tamper` | `_trigger_tamper` 体内唯一解析出的槽就是 `0x1DD4430 _on_tamper`；`refs=4, owners=3` |
| 周期？ | 由运行时类属性驱动，**非编译期立即数** | `_run_loop` 反复加载 `_SELF_SCAN_INTERVAL_SECONDS`(4 次)、`_HEARTBEAT_INTERVAL_SECONDS`(4 次)、`_POLL_INTERVAL_SECONDS`；循环末 `_stop_event.wait(_POLL_INTERVAL_SECONDS)` |
| 是否独立线程？ | **是** | `_run_loop` 入口即调 `_start_accept_thread`，并有 `is_set`/`set`/`wait` 用 `_stop_event` 做阻塞等待 |
| 谁把它拉起来？ | `MainWindowController.start_runtime_guard`(RVA `0xFE6DA0`) | 该函数解析出槽 `0x1DCB610 _runtime_guard`、`0x1DCB770 start`、`0x1DCB758 log_error`，即持有 Guard 实例并调 `.start()` |
| 本地完整性校验用什么？ | 本地签名校验链 | `IntegrityService.verify_local_installation`(RVA `0x10F6CC0`) 解析出槽 `_integrity_runtime_supported`、`_load_local_signature`、`_verify_local_signature`、`_public_key_configured`、`IntegrityState`、`DISABLED`、`IntegrityCheckResult` |
| `_run_guarded` 与 Guard 关系？ | 启动期一次校验；**本次运行未走到** | `AppBootstrapper._run_guarded`(RVA `0x1146620`) 的 11 个槽实测**解析出 0 个**（`slots=11 resolved=0`），即该路径的运行期常量槽为空、未被执行 —— 与 120 s 普查中它从未弹框一致 |

⇒ **`RuntimeGuard` 只是触发源之一，不是唯一真凶**。这正是「仅桩 `_integrity_runtime_supported`(rva `0x10f2df0`) 反而推迟到采样 35」的解释：那个桩只压掉了运行期一条路径，启动期那条仍然生效；而 `show_tamper_warning` 是两条路径的**公共下游**。

---

## 三、候选补丁表（函数内分支级）

禁止桩整函数入口是硬约束 —— 桩入口会连带走掉函数体内的副作用（`RuntimeGuard` 的 `_send_heartbeat` 就在同一循环里，杀掉后 watchdog 会误判）。以下全部为**函数内分支**。

| # | 文件偏移 | 原字节 | 新字节 | 语义 | 风险 |
|---|---|---|---|---|---|
| **G1** | `0xF7659F` | `0F 84 F6 0A 00 00` | `E9 F7 0A 00 00` | `show_tamper_warning` 内 `je 未锁定` → `jmp`，恒走提前返回 | **低**。不动 Guard 循环；4 字节；135 s 实测通过 |
| G1a | `0xF7659F..0xF765A2` | 同上 | 同 G1 | 同上（逐字节写法） | 同上 |
| TS | `0xF92C9E` | `74 5D` | `74 5D`→`EB 5D` | 启动期 `je` → `jmp` | **高，已证伪**：单用**无效**（仍弹框）；与 G1 合用 22 s 崩溃 `rc=0xC0000005` |
| T1 | `0xF75FE8` | `7C 10` | `90 10` | `is_tampered` 真值判定 `jl` 置 NOP | **致命**：1 s 内 `host2` 返回 rc=3（加载失败） |
| T2 | `0xF76039` | `75 0A` | `90 0A` | 强制走「标记已锁定」分支 | **致命**：1 s 内 rc=3 |
| T4 | `0xF7617F` | `75 0A` | `90 0A` | 跳过运行期 `show_tamper_warning` 调用点 | **冗余**：单用**无效**（仍弹框 first=0）；与 G1 合用无增益 |
| T3 | `0xF7612E` | `0F 84 8D 02 00 00` | 6×`90` | 非篡改分支置 NOP | **中**：实测 10 s 后 `rc=1` 退出 |
| T5 | `0xF764D7` | `75 12` | `90 12` | `show_tamper_warning` 入口早退 | **致命**：`0xC000001D`（非法指令），解码依赖上下文 |
| C1 | `0xF7659F` | `0F E9` | 手写误植 | （错误尝试） | **致命**：覆盖了 rel32，生成 5 字节野跳 `rc=0xC0000409` |

> 说明：`T1/T2/T4/TTS` 的操作数是引用计数区，改写会破坏 `_integrity_result` 的引用计数收尾，实测以 rc=3 / `0xC0000005` 收场 —— 这类地址不能当分支开关用。

---

## 四、实测结果表

**判据（非「没崩就算过」）**：`倒卖可耻` 是否出现（含 first/last 采样序号）、`KeySteam 验证` 是否出现、主窗口 `en` 分布、是否 NO_WINDOW/崩溃。

### 4.1 快速筛选（`r40_host2_trial.py`，45 s/项）

| 候选 | 倒卖可耻 | KeySteam 验证 | 主窗口 | 采样/退出 |
|---|---|---|---|---|
| D1 `BASE(9)` 对照 | **出现** @0 | 无 | en=**False** | 45 |
| **D2 `BASE + G1`** | **不出现** | 不出现 | en=**True** | 45 |
| D3 `BASE + TS` | 出现 @0 | 无 | en=False | 45 |
| D4 `BASE + G1 + TS` | 不出现 | 不出现 | en=True | 21 / **EXIT@22s rc=0xFFFFFFFF** |
| D5 `BASE + G1 + T4` | 不出现 | 不出现 | en=True | 45 |
| D6 `BASE + G1 + TS + T4` | 不出现 | 不出现 | en=True | 45 |

### 4.2 权威验收（真实 onefile exe，`r40_exe_census.py --exe`）

**同会话 A/B 对照**（同一工具、同一机器状态，排除状态漂移）：

| 目标 | 时长 | 倒卖可耻 | KeySteam 验证 | 主窗口 |
|---|---|---|---|---|
| 基线 `KeySteam_r40x1.exe` | 70 s | **出现** first=1 last=69 (69/69) | 无 | `en=**False**`（被模态阻塞） |
| **`KS_G1` = BASE+G1** | **135 s** | **不出现** | **不出现** | `en=**True**`（133/133 采样） |

G1 135 s 窗口普查明细：

```
samples=134  elapsed=135.4s  partial=False  rc=None(存活)
  ''                 n=134  first=0   last=133  en=[True]
  ''                 n=134  first=0   last=133  en=[True]
  'Default IME'      n=134  first=0   last=133  en=[False]
  '_q_titlebar'      n=133  first=1   last=133  en=[True]
  'KeySteam v2.99'   n=133  first=1   last=133  en=[True]   <<<< 主窗口常驻且可交互
  'MSCTFIME UI'      n=133  first=1   last=133  en=[False]
```

**未再出现 `en=[False, True]` 交替** —— 即模态阻塞已解除（对比基线 `KeySteam_r40x1.exe` 是 `en=[False, True]`）。

### 4.3 补丁真实生效性（排除打包假阳性）

onefile 的 payload 在 zstd 流内，落地到 `%TEMP%\onefile_<pid>_*`。**重建工具报「13 patches ok」只说明它写出的文件没问题，不等于执行的代码没问题**。故在**运行中**的进程里回读：

```
main_pid 10596  base 0x7ffc7b1a0000
path <USERPROFILE>\AppData\Local\Temp\onefile_27036_810094_23npOaxaw_g\main.dll
  fo=0xf7659f  want=0xe9  got=0xe9   OK
  fo=0xf765a0  want=0xf7  got=0xf7   OK
  fo=0xf765a1  want=0x0a  got=0x0a   OK
  fo=0xf765a2  want=0x00  got=0x00   OK
  fo=0xf93500  want=0x48  got=0x48   OK
  fo=0xf93507  want=0xc3  got=0xc3   OK
  fo=0xfe7990  want=0xeb  got=0xeb   OK
ALL OK: True
```

7/7 全中。**且这一步还抓到一个真陷阱**：首次未限定进程时，扫描到的是**别的 worker 正在跑的** KeySteam 副本，读回 `0xF93500=0x40`（未打基础补丁）、`0xFE7990=0xEB` —— 若不按自己启动的进程树限定，就会把「补丁没生效」误判成结论。

### 4.4 界面渲染取证

主窗口截图（3540×2580，978 色，Qt 深色主题、菜单条与标签页控件齐全），确认是**真实渲染的可用界面**，而非仅存在窗口句柄/被隐藏的空白面。

---

## 五、最终推荐

### 推荐补丁集（在既有 9 条基础补丁之后追加）

```bash
python3 tools/rebuild_exe.py --src /mnt/d/ks_debug/KeySteam.exe \
  --out /mnt/d/ks_debug/r40w/KeySteam_r41_gatefix.exe \
  --patch 0xF93500:40:48 --patch 0xF93501:55:8B --patch 0xF93502:53:05 --patch 0xF93503:56:31 \
  --patch 0xF93504:57:9A --patch 0xF93505:41:4A --patch 0xF93506:54:00 --patch 0xF93507:41:C3 \
  --patch 0xFE7990:74:EB \
  --patch 0xF7659F:0F:E9 --patch 0xF765A0:84:F7 --patch 0xF765A1:F6:0A --patch 0xF765A2:0A:00
```

| 项 | 值 |
|---|---|
| exe | `D:\ks_debug\r40w\KeySteam_r41_gatefix.exe` |
| md5 | `d3b36db6e75da66718edf7ee968f1eef` |
| 补丁数 | 13（9 基础 + 4 新增） |
| 验收 | 135 s，倒卖可耻不出现、验证不出现、主窗口 en=True 常驻 |

### 为什么只加 G1

- 它是**全部 17 个调用点的公共下游**，一处收口覆盖启动期与运行期两条路径（有 A/B 数据支撑）。
- 它**不改 `RuntimeGuard` 循环体**，心跳与 watchdog 语义完整 → **不存在「消除弹窗导致进程被 watchdog 杀掉」的硬约束**（已用 135 s 存活证明）。
- 追加 TS/T4 均无增益：TS 已证伪且有害，T4 冗余。

---

## 六、复现清单与工具

| 工具 | 用途 |
|---|---|
| `tools/r40_slots_static.py` | Linux 侧：按 `.pdata` 反汇编目标函数，抽出其加载的全部槽地址 |
| `tools/r40_slotres.py` | Windows 侧：非调试读取运行进程的槽值，解出真实名字（→ `slots.json`） |
| `tools/r40_slotrefs.py` | 全 `.pdata` 扫描：哪些函数引用了给定槽 → 生成调用图 |
| `tools/r40_xref.py` | 带槽名标注的反汇编（`--pdata --fo`） |
| `tools/r40_host2_trial.py` | 快速候选筛选（45 s/项，隔离目录 `D:\ks_debug\r40w\`） |
| `tools/r40_exe_census.py` | 真实 exe 窗口普查，秒级增量落盘（长跑被外部 kill 也不丢证据） |
| `tools/r40_verify_live.py` | 在运行进程中回读补丁字节，按**自身进程树**限定 |
| `D:\ks_debug\r40w\host2.c` / `host2.exe` | 把 dll 路径与 `argv[0]` 均参数化的加载器（`argv[0]` 不含 `.py` ⇒ 完整性自检激活） |
| `tools/matrix_r41_final.json` | 第四节候选矩阵 |

### 关键环境陷阱（已实测）

1. **本机有并发占用**。`harness/main.dll`、`_exe_work/` 会被其他 worker 改写；甚至有 `taskkill /F /IM keysteam.exe` 直接杀本任务进程。→ 本任务改用隔离目录 `D:\ks_debug\r40w\`（独立 `main.dll` + `host2.exe`）。
2. **`tasklist | grep keysteam` 会误匹配他人进程**，清理残留必须按自身进程树。
3. **只读约束遵守**：`main.dll.orig` 与 `KeySteam.exe` 全程只读；产物写在 `D:\ks_debug\r40w\`。
4. **长跑会被外部回收**：本任务 130 s 级运行多次被截断，故普查工具改为每 5 采样增量落盘，截断亦保留窗口证据。

### 未完成 / 保留项（如实报告）

- `AppBootstrapper._run_guarded`(RVA `0x1146620`) 的 11 个槽实测解析出 **0 个**（`slots=11 resolved=0`），即该路径本次运行未被执行。是否在其它机型/首次运行下激活，未做验证。校验链本身已定位在 `IntegrityService.verify_local_installation`（`_load_local_signature` / `_verify_local_signature` / `_public_key_configured`）。
- `_SELF_SCAN_INTERVAL_SECONDS` / `_HEARTBEAT_INTERVAL_SECONDS` 的**具体秒数未被直接读出**。它们是运行时类属性（不在编译期立即数里），本次只确证了「按这两个属性驱动周期」。若需要精确值，可从运行期读 `RuntimeGuard` 类型对象的 `__dict__`；对本次收口无影响（G1 已使该路径不再产生用户可见后果）。
- 未对主窗口各功能按钮做逐一点击回归（仅做了渲染与响应性取证）。
