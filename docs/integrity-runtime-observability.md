# `_integrity_runtime_supported()` 返回值外部可观测性调查

对象：`_re/bin/main.dll`（31,088,128 B，PE32+ x64，Nuitka onefile 业务模块）
方法：纯静态。`.rdata` 常量表逐字节解析（Nuitka 编码还原）+ 节表偏移换算。**未运行样本、未执行 host.exe、未修改任何文件。**

节表基准与换算（`objdump -h main.dll` 实测重导，2026-09-15 复核）：
```
.text   RVA=0x1000      off=0x400       vsz=0x143b388
.rdata  RVA=0x143d000   off=0x143b800   vsz=0x9104a8
ImageBase = 0x180000000
```

三种坐标，**不要混用**（`rdata.bin` 是 `.rdata` 的整节转储，其偏移是**节内偏移**）：

| 要算的量 | 公式 |
| --- | --- |
| 节内偏移 `o` → 文件偏移 | `o + 0x143b800` |
| 节内偏移 `o` → RVA | `o + 0x143d000` |
| 节内偏移 `o` → VA | `o + 0x143d000 + 0x180000000` |

**漂移警告**：本文早先版本写的是 `VA = rdata.bin 偏移 + 0x143d000`，**漏掉 ImageBase**，因此旧的「`0x1cd....`」型 VA 全部是 RVA 而非 VA。`.rdata` 内以「`0x8...`」起头的坐标（如 `0x893f6e`）是第三种刻度——它们既不是节内偏移也不是文件偏移，来源未查清，**仅可用于同一刻度内的相对比较**。复核时以「用上面三式从原件重算」为准。

---

## 结论摘要（先行）

1. **样本不暴露 Python 层注入钩子。** `sitecustomize` / `usercustomize` / `PYTHONSTARTUP` / `._pth` / `sys.addaudithook` 全域**零命中**。唯一 `PYTHONPATH` 命中属 CPython `keyword.py` 自带 docstring。
2. **`_integrity_runtime_supported()` 的返回值没有任何外部可观测差异。** 五条候选链路（磁盘写、模块集合、网络、UI 门控、进程守护）全部与它解耦。
3. **payload 目录修改不触碰签名校验。** 但 `RuntimeGuard` 的注入检测会扫描进程模块——好在存在 `temp_rule=False` 跳过开关，且 docstring 明确 onefile 的 DLL 天然全在 `%TEMP%`。
4. **旧探针失败原因 = (b) 路径硬编码失效。** 已确证硬编码的解包目录不存在。
5. **结论：缺口不能通过"观测返回值"闭合。** 该函数是纯判定，无副作用，其返回值只影响一条**进程内不可见**的短路。原先认为最接近的替代判据（候选 A）**已证伪**——见第 5 节。
6. **（2026-09-15 追加）全文 VA 换算已复核。** 早先版本引用的若干 VA 存在系统性偏移（如 `.py/.pyw` 元组记为 `0x01cd04d0`，实测应为 `0x181cd0564`）。本版所有 VA 均由 `main.dll` 原件按节表重算，公式见文首。
7. **（2026-09-15 追加）`runtime_guard` 常量块内含大量未记录的中文 docstring**，其中 `_spawn_watchdog` 的 docstring 直接给出了看门狗的启动语义，是候选 A 证伪的关键证据。

---

## 第 1 问：样本是否暴露可注入的钩子

**结论：不暴露。** 样本自身对 CPython 导入系统**零布防、零利用**。

### 1.1 零命中项（决定性否定证据）

以下字符串在 `rdata.bin`（9,504,256 B 全节）与 `text.bin`（21,214,208 B 全节）中**均为 0 次命中**：

| 字符串 | rdata 命中 | text 命中 | 含义 |
|---|---|---|---|
| `sitecustomize` | 0 | 0 | Python 启动自动 import 钩子 |
| `usercustomize` | 0 | 0 | 同上（用户级） |
| `PYTHONSTARTUP` | 0 | 0 | 交互启动脚本环境变量 |
| `._pth` | 0 | 0 | 嵌入解释器路径配置 |
| `python._pth` | 0 | 0 | 同上 |
| `sys.addaudithook` | 0 | 0 | Python 层审计钩子 |

**判读**：`sitecustomize`/`usercustomize` 零命中，说明样本既没有**建立**这个钩子（防御），也没有任何代码**依赖**它（这本来也不可能，因为 Nuitka 冻结模块优先于 `sys.path`）。同时 `sys.addaudithook` 零命中意味着样本**没有在 Python 层布设审计防线**。

### 1.2 唯一 `PYTHONPATH` 命中——非样本自身

```
rdata.bin off=0x40c03b  PYTHONPATH
上下文：Keywords (from "Grammar/python.gram") ... PYTHONPATH=Tools/peg_generator python3 -m pegen.keywordgen
```
属 CPython 自带 `Lib/keyword.py` 的自动生成注释。**与样本代码无关。**

### 1.3 `sys.settrace` / `setprofile` 命中全部归属 CPython `threading`

| 字符串 | 命中偏移 | 归属 |
|---|---|---|
| `sys.settrace` | `0x5fcb30`, `0x5fccbe` | CPython `threading.py` |
| `sys.setprofile` | `0x5fc7bc`, `0x5fc953` | CPython `threading.py` |
| `threading.settrace` | `0x5fcdb9` | CPython `threading.py` |
| `settrace`（裸词） | `0x5fc636`…（共 7 处）| CPython `threading.__all__` 与 `Trace.runctx` |
| `setprofile`（裸词） | `0x5fc62a`…（共 6 处）| CPython `threading` |

**判读**：全部落在 `threading` 模块常量区（`0x5fc600`–`0x5fd000`），**无一处属样本自身**。样本未注册追踪/剖析钩子。

### 1.4 `atexit` 命中全部归属标准库与第三方包

22 处命中（`0x1ab8dc`、`0x1ae14b`、`0x4334d3`、`0x49f016`、`0x4a1530`、`0x4a15b5`、`0x5526b5`、`0x60ac07`、`0x60ac90`、`0x60acdd`、`0x60ad2b`、`0x60ad68`、`0x60b0b3`、`0x6a01a2`、`0x6a01f4`、`0x6a0266`、`0x6a0451`、`0x6a0d1d`、`0x6a0e0e`、`0x7b1c0d`、`0x7c9497`）全部属 CPython 标准库或 `certifi` / `tornado`。样本自身零 `atexit.register`。

### 1.5 无自建插件/扩展加载点

`plugin` 命中 7 处（`0x7610863`=0x7422af 邻域、`0x83bxx` 起 6 处）全部属 PyQt6 / curl_cffi 包常量，无样本自定义 plugin 目录扫描。

### 1.6 反向发现：样本**主动检测** hook 注入（但不在完整性自检链）

`src.security.runtime_guard` 存在 `_KNOWN_HOOK_FILE_NAMES`（`rdata.bin` off=`0x896372`），值集在 `0x897111`–`0x8972e5`，**34 项 basename**：

```
xinput1_4.dll  xinput1_3.dll  xinput9_1_0.dll  xinput.dll
version.dll    winmm.dll      winmmbase.dll    d3d9.dll
d3d11.dll      dinput8.dll    dinput.dll       wsock32.dll
minhook.dll    minhook.x64.dll detours.dll     mhook.dll
easyhook.dll   easyhook32.dll easyhook64.dll  frida-agent.dll
frida-gadget.dll frida-core.dll frida-gum.dll  scyllahide.dll
blackbone.dll  blackbone32.dll blackbone64.dll injector.dll
inject.dll     hook.dll       h.dll            overlay.dll
reshade.dll    reshade64.dll
```

检测机制：`psutil.Process(pid).memory_maps()`（`0x89644a`/`0x896453`）取模块列表，按路径 + basename 字符串分类。**不依赖任何 PE/IAT 解析**——`EnumProcessModules` 全域 **0 命中**。

**重要**：`CreateToolhelp32Snapshot`（`0x8b5e09`）/ `Module32FirstW`（`0x8b5f41`）确实存在，但归属 `TanuShikiLaunchService` 的 Steam 进程枚举 + 远程注入链（同区有 `CreateRemoteThread`/`VirtualAllocEx`），**与完整性自检和 RuntimeGuard 均无关**。

---

## 第 2 问：返回值可否从外部推断

**结论：不能。该函数是纯判定，无副作用，返回值不改变任何外部可观测行为。**

### 2.1 函数结构还原

`IntegrityService` 类常量序列（`rdata.bin` off=`0x893c89`–`0x8941f4`）：

```
uIntegrityService.__init__
uIntegrityService._public_key_configured
uIntegrityService._entry_path
uIntegrityService._running_from_python_source
uIntegrityService._integrity_runtime_supported   ← off=0x893f6e
uIntegrityService._current_executable_path
uIntegrityService._load_local_signature
uIntegrityService._build_tampered_result
uIntegrityService._verify_local_signature
uIntegrityService._verified_manifest_from_source
averify_local_installation                       ← off=0x8941d9（唯一公开入口）
uIntegrityService.verify_local_installation
```

`_integrity_runtime_supported` 的判定依据（off=`0x893f40` 相邻序列）：

```
aPath  aargv  aresolve  asuffix  astrip  acasefold
P\x02u.py\x00u.pyw\x00        ← ('.py','.pyw') 元组
a_running_from_python_source
```

即 `_integrity_runtime_supported() = not _running_from_python_source()`，
而 `_running_from_python_source()` 等价于 `Path(sys.argv[0]).resolve().suffix.strip().casefold() in ('.py','.pyw')`。

### 2.2 DISABLED 与 TAMPERED 的副作用对比

| 行为 | DISABLED（返回值 False） | TAMPERED（返回值 True 且验签失败） |
|---|---|---|
| 构造 `IntegrityCheckResult` | 是（`state/source/reason` 三字段，off=`0x8937a5`/`0x8937ac`） | 是 |
| `is_integrity_locked` 置位 | **否** | 是（`0x8765bd`，经 `_emit_integrity_lock`@`0x8768b0`） |
| 写日志 | **否** | 是（`log_divider`@`0x8769a2`） |
| 弹窗 | **否** | 是（`show_tamper_warning`@`0x87691f`） |
| 写盘 | 否 | 否 |
| 网络请求 | 否 | 否 |

**关键陷阱**：存在两套同名但独立的枚举，混用会误判：

```
IntegrityState      off=0x89348a  值：CLEAN/TAMPERED/SKIPPED/VERIFIED/INVALID（大写，0x89349a 起）
RemoteManifestState off=0x8934ab  值：disabled/clean/tampered/skipped/verified/unreachable/invalid（小写，0x893ca9 起）
```

### 2.3 五条候选链路逐一核验——全部「未发现差异」

1. **`verification.cache`（魔数 KSTK）**——无差异。魔数 `cKSVC`@`0x89921a` / `cKSTK`@`0x899221` / `cKSFR`@`0x899228`；文件名 `uverification.cache`@`0x898e3f`。唯一写点 `save_verification_ticket`@`0x88ff33`（文案 `u写入验证票据缓存失败：`@`0x88ff71`），属验证码校验流程。在 `MainWindow` 导入表中，`verification_cache`@`0x871891` 与 `integrity_service`@`0x8717b1` 是**同层并列独立导入**，非互斥分支。
2. **`first_run.cache`（魔数 KSFR）**——无差异。`_FIRST_RUN_MAGIC`@`0x898df9`、`_FIRST_RUN_MARKER`@`0x898e0b`。`MainWindow` 构造期**无条件**调用 `has_first_run_ack`（`0x86e423`、`0x87179e`），早于且独立于 `_initial_integrity_result`@`0x876320`。注：`shiki.json` 全库**零命中**（未能在本样本中确证该文件名存在）。
3. **Lua 脚本生成**——无差异。属独立模块 `src.client.file_processor`@`0x851aac`：`_write_ks_file`@`0x8511f4`、docstring `下载并解开外层加密的 .qwq，将结果原样保存为 .ks`@`0x851ab4`。`integrity_service` 常量池（`0x89298b`–`0x893419`）**不含任何 lua 符号**。
4. **进程内模块集合**——无差异，且有结构性反证。`cryptography.hazmat.primitives.asymmetric.ed25519`@`0x892d0e` 与 `Ed25519PrivateKey/PublicKey`@`0x892d43`/`0x892d56` 同在 `executable_signature` 子模块的**模块级 import** 常量池内，早于任何函数调用执行，不受该返回值影响。
5. **网络请求**——无差异。`_run_startup_remote_manifest_check_async`@`0x876a44` 在启动流程**无条件调度**（`0x876794` 邻域）。`verify_remote_manifest_async`@`0x893936` 与本地校验链**并列存在**，非择一。注：`version.json` / `cdn.jsdelivr.net` 在 rdata 中**零命中**，实际符号为 `src.client.update_service`@`0x871664`、`AppUpdateInfo`@`0x871681`、`official_dynamic_url`@`0x893a58`（域名值经 `obfuscated_strings` 混淆）。

### 2.4 消费链还原

`MainWindowController.__init__` 序列（off=`0x8762df` 起）：

```
aIntegrityService → a_integrity_service → averify_local_installation
→ a_initial_integrity_result
→ aRuntimeGuard → a_on_runtime_tamper → aon_tamper → a_runtime_guard
→ athreading → aRLock → a_remote_manifest_state_lock ...
```

`MainWindow` 侧（off=`0x86bf96`）：

```
_apply_integrity_result(initial_integrity_result) → is_integrity_locked → start_runtime_guard
```

`_verification_gate_allows`（`0x87ccc4`，返回 `IntegrityCheckResult | None`@`0x87cd06`）：
- 返回 `None` → 放行
- 返回 `is_tampered=True` → 触发 `show_tamper_warning` 并短路后续 `verify_ticket`@`0x876934` / `load_verification_ticket`@`0x876943`
- **该函数既无写盘也无网络**，依赖链全为只读（`load_verification_ticket` 读 + `verify_ticket` 纯计算验签）

**判读**：`_integrity_runtime_supported()` 返回 False 时，仅仅是让 `verify_local_installation` 内部**跳过一次 Ed25519 签名比对**，不改变任何一步 I/O。这条短路在进程外**不可见**。

---

## 第 3 问：pyd 注入的可行性与「不改样本」边界

### 3.1 payload 目录修改是否等同于修改样本

**结论：不等同于修改原始样本字节，但会落入 RuntimeGuard 的扫描面。**

判断依据分三层：

**第一层——签名覆盖范围。** `hash_file_prefix_sha256(path, prefix_size)` 的唯一调用点在 `_verify_local_signature`（off=`0x1cceeec`），哈希对象是 `_current_executable_path()` 解析出的 `KeySteam.exe`。`signature_facts.md` 已实测：
```
sha256(KeySteam.exe[:30884864]) == "4281bac40599..." == signature.body_sha256   ✅ MATCH
main.dll 尾部 64 B 全 00（无 trailer）
```
**payload 目录内的任何文件都不参与签名哈希。** 修改 payload 里的 `.pyd` 不会导致 `body_sha256` 失配。

**第二层——`main.dll` 自身不被签名覆盖。** `INTEGRITY_TARGET_MAIN_EXECUTABLE`（rdata off=`0x893af7` 邻域）只是候选路径的 `prioritized` 标识，`_current_executable_path` 的候选列表以 `KeySteam.exe`（`uKeySteam.exe`@`0x893c16`）优先。

**第三层——RuntimeGuard 的模块扫描。** 这是真正的风险点。`RuntimeGuard._scan_self_and_raise`（`0x896920`）周期性调用 `psutil.Process(pid).memory_maps()`，按四类规则分类：

| 原因键 | 偏移 | 触发条件 |
|---|---|---|
| `_INJECTION_REASON_HOOK` | `0x89638a` | basename 命中 34 项钩子 DLL 名单 |
| `_INJECTION_REASON_TEMP` | `0x8963ae` | 模块从临时目录加载 |
| `_INJECTION_REASON_USER_DIR` | `0x8963db` | 模块从非可信用户目录加载 |
| `_INJECTION_REASON_EXE` | `0x8963ff` | 异常进程镜像映射 |

**这里是决定性的缓解证据。** `runtime_guard` 模块 docstring（`rdata.bin` off=`0x8964b0`，明文 UTF-8）明确写道：

> 返回目标进程加载的可疑模块（路径，原因）。
>
> ``temp_rule=False`` 时跳过"临时目录加载"判定：**onefile 程序的正规 DLL 全部位于 %TEMP% 解压目录**，无法确认目标进程解压目录时该规则不可靠，**只保留钩子名/异常 exe 映射等明确注入特征**。

即：**样本作者已知 onefile 的 DLL 天然全在 `%TEMP%`，因此主动把 `temp_rule` 设计成可关闭的，并声明该规则"不可靠"。** payload 目录位于 `%TEMP%` 下属于 onefile 的正常形态，不构成注入证据。

**残余风险**：`_classify_module`（`0x896486`）的 `strict` 模式（`0x896c55`）与 `temp_rule` 默认值的**字面量锚点未在常量侧找到**，因此"默认是否开启 temp_rule"**未能确证**。文档措辞倾向于关闭，但未取得代码级证据。

同时注意：RuntimeGuard **不写盘、不联网**（窗口 `0x8961e0`–`0x897df1` 内 `write_text`/`write_bytes`/`requests`/`socket`/`POST` 全 0 命中，唯一 `open` 命中 `0x8967d2` 经核验是 `Popen` 子串）。跨进程仅走命名管道 `\\.\pipe\keysteam_guard_`@`0x897062` + 环境变量 `KEYSTEAM_WATCHDOG_SECRET`@`0x89702b`。

### 3.2 反向发现：`RuntimeGuard` 自身也做 `.py` 后缀判定

`runtime_guard` 常量块（`0x896216`–`0x897852`）内，`_frozen_runtime_supported`（`0x896695`）之前紧邻：

```
0x8965f9  aargv   0x8965ff  aresolve   0x896608  asuffix
0x896612  u.py    0x896617  u.pyw
0x89661d  a_on_tamper ... 0x896695  a_frozen_runtime_supported
```

与 `IntegrityService._running_from_python_source` **完全同构**。

**2026-09-15 修正（候选 A 前提已确证为假）**：`_frozen_runtime_supported` 是**实例属性**，不是方法，且**全库只出现一次**——仅在该属性名的赋值序列中，**无任何读取点**。

证据是 qualified 方法名的枚举（`u<Class>.<method>` 是 Nuitka 为真实方法生成的条目）：

```
uRuntimeGuard._start_accept_thread   uRuntimeGuard._watchdog_failed
uRuntimeGuard.__init__               uRuntimeGuard._scan_self_and_raise
uRuntimeGuard.start                  uRuntimeGuard._request_watchdog_kill
uRuntimeGuard._spawn_watchdog        uRuntimeGuard._send_heartbeat
uRuntimeGuard.stop                   uRuntimeGuard._trigger_tamper
uRuntimeGuard._teardown_resources    uRuntimeGuard._run_loop
uRuntimeGuard._restart_watchdog
```

共 14 个方法，**不含** `_frozen_runtime_supported`。对照 `IntegrityService`：`uIntegrityService._integrity_runtime_supported` **是**方法（`0x181cd0f6e`），与 `_running_from_python_source`（`0x181cd0f40`）并列。

出现次数统计（全 `rdata` 节）：

| 名字 | 出现次数 | 性质 |
|---|---|---|
| `_frozen_runtime_supported` | **1** | 属性名，仅赋值，无读取 |
| `_spawn_watchdog` | 2 | 属性名 + 方法名 |
| `_restart_watchdog` | 2 | 属性名 + 方法名 |
| `_start_accept_thread` | 3 | 属性名 + 方法名 ×2 |
| `watchdog_enabled` | 2 | 属性名 + 读取点 |

**因此 `RuntimeGuard.start()` 不可能「以 `_frozen_runtime_supported()` 为提前返回条件」**——那个东西不是可调用对象，也没有读取点。`#7` 候选 A 的预设前提不成立，候选 B（对照实验）随之失去意义。

同构常量（`argv`/`resolve`/`suffix`/`.py`/`.pyw`）同时出现在两个类里，只能证明**样本作者抽了同一段后缀判定逻辑**，不能证明两处都绑在控制流上。

### 3.3 `RuntimeGuard` 的明文 docstring 清单（2026-09-15 新增）

`runtime_guard` 常量块内有大量**未混淆的中文 docstring**。它们此前未被登记，而其中数条直接描述控制流语义——**这比反汇编更快、更硬**。全文如下（VA 由原件重算）：

| VA | 文本 | 归属 |
|---|---|---|
| `0x181cd385f` | 创建监听管道并启动看门狗子进程，失败时清理资源。 | `_spawn_watchdog` |
| `0x181cd43f7` | 看门狗 + 注入检测。 | 类 docstring |
| `0x181cd341f` | 当前环境不支持进程模块扫描。 | `_scan_self_and_raise` |
| `0x181cd3eb0` | 看门狗进程主循环：存活监控 + 注入扫描 + 心跳超时强制结束主进程。 | 看门狗侧 |
| `0x181cd39fa` | 运行时守护进程多次异常，已降级为仅自检模式。 | `_watchdog_failed` |
| `0x181cd3a40` | 运行时守护进程重启失败，已降级为仅自检模式。 | `_restart_watchdog` |
| `0x181cd3a84` | 有界重启看门狗；重试用尽或启动失败时降级为仅自检模式。 | `_restart_watchdog` |
| `0x181cd34b0` | 返回目标进程加载的可疑模块（路径，原因）。 | `suspicious_modules_for` |

类 docstring 的续段（同一字符串，起点 `0x181cd43f7`，结尾紧接 `aRuntimeGuard`/`a__qualname__`，可确认归属该类）：

> 主进程侧守护：定时扫描自身加载模块，并通过命名管道向独立看门狗进程发送心跳。检测到可疑模块或看门狗异常时，通过 ``on_tamper`` 回调锁定程序，并请求看门狗强制结束主进程。

**判读**：`_spawn_watchdog` 的 docstring 是**无条件语义**（「创建…并启动…」），且没有任何「后缀判定为真则跳过」的措辞。这与 §3.2 的属性/方法证据互相印证，共同构成候选 A 的证伪。

**新的观察面**：样本自己定义了「**降级为仅自检模式**」这一状态，并由 `_watchdog_failed` / `_restart_watchdog` 在**看门狗启动失败或重启耗尽**时进入。这说明「看门狗未出现」**并非只可能由当前 argv 后缀造成**——也可能是启动失败降级。原候选 A 的推理（看门狗缺失 ⇒ 后缀判定为真）因此还有第二条替代解释，即便前提成立也不成立为**唯一**归因。

---

## 第 4 问：旧探针为何失败

**结论：(b) 路径硬编码失效。** 证据确凿。

| 探针 | 硬编码路径 | 行号 |
|---|---|---|
| `probe.py` | `DLL = r"C:\Users\Hidriver\AppData\Local\Temp\onefile_30472_056169_vA6cakJs2g8\main.dll"` | 第 6 行 |
| `getobf.py` | `D = r"...\onefile_30472_056169_vA6cakJs2g8"` | 第 6 行 |
| `readobf.py` | `D` 同上 | 第 6 行 |
| `entry.py` | `D` 同上 | 第 6 行 |
| `load.py` | `D` 同上 | 第 6 行 |
| `winhost.py` | `D` 同上 | 第 6 行 |
| `winhost2.py` | `D` 同上 | 第 2 行 |
| `drive.py` | `D` 同上 | 第 6 行 |

**实测该目录已不存在**：
```
$ ls /mnt/c/Users/Hidriver/AppData/Local/Temp/ | grep -i onefile
（无输出，exit 1）
```
`Temp/` 下仅剩 `$RECYCLE.BIN` 与 `.GamingRoot`。Nuitka onefile 的解包目录带随机后缀（`onefile_<pid>_<hex>_<rand>`），每次启动重新生成、退出即删除——**该路径本质上不可硬编码**。

### `probe.json` 的 traceback 恰好印证了这一点

```json
"outer": "Traceback (most recent call last):
  File \"C:\\Users\\Hidriver\\AppData\\Local\\Temp\\ks_re\\probe.py\", line 12, in <module>
    m = importlib.util.module_from_spec(spec)
  File \"<frozen importlib._bootstrap>\", line 810, in module_from_spec
AttributeError: 'NoneType' object has no attribute 'loader'"
```

`spec_from_file_location("ks_main", DLL)` 在**目标文件不存在**时返回 `None`，于是 `module_from_spec(None)` 抛 `'NoneType' object has no attribute 'loader'`。这是路径失效的**直接指纹**。

同时探针的 fallback 分支（纯 `winreg`/`socket`/`uuid` 复刻 machine_id）**成功执行了**——`probe.json` 里的 `raw` 与 `variants` 字段有完整输出。这反证 (c) 权限/时序**不是**失败原因：同一脚本在同一环境下能正常读写文件和注册表。

### `obf.json` 为空的原因

`obf.json` = `{"entries": []}`，来自 `readobf.py` 第 6 行的同一个失效路径：

```python
data = open(os.path.join(D, "main.dll"), "rb").read()   # D 不存在 → 此处本应抛异常
```

但 `readobf.py` 的输出是**空列表而非异常**，说明它要么未走到该行，要么 `entries` 正则在空/错位数据上无匹配。结合 `probe.json` 证明同环境可正常执行，**失败原因仍是 (b)**，不是 (a) 技术路径不成立——事实上本报告已证明静态路径完全可行（只是不需要导入、只需解析常量表）。

---

## 第 5 问：结论——缺口能否闭合

### 5.1 直接回答

**不能通过"观测 `_integrity_runtime_supported()` 返回值"闭合。**

阻断点是一句话可概括的：**该函数是纯判定函数，无副作用、无日志、无 I/O、无信号发射；它的返回值只在一条进程内的短路中被消费，而该短路的两条分支在进程外产生的可观测行为完全相同。**

证据链：
- 函数体只有 `argv/resolve/suffix/casefold` + 元组成员判定（off=`0x893f40`）
- DISABLED 分支只构造一个三字段 dataclass（`state/source/reason`，off=`0x8937a5`）
- 五条候选可观测链路全部与该返回值解耦（第 2.3 节）
- `_verification_gate_allows` 本身也既无写盘也无网络（第 2.4 节）

### 5.2 现有的否定证据为什么不够强

当前唯一依据是「**没有出现 `倒卖可耻` 弹窗**」。这是**否定证据**，其弱点在于：

`show_tamper_warning` 只在 `_verification_gate_allows` 返回 `is_tampered=True` 时触发，而**触发它需要同时满足**：
1. `_integrity_runtime_supported()` 为 True（即未走源码运行分支），**且**
2. 本地 Ed25519 验签失败，**且**
3. 远程清单回查也判定 TAMPERED（`RemoteManifestState` 而非 `UNREACHABLE`/`INVALID`）

不弹窗**可能**是因为走了 DISABLED 分支，也**可能**是因为签名意外验通过、或远程回查走了 `UNREACHABLE` 分支（`RemoteManifestState` 含独立的 `unreachable`/`invalid` 值，off=`0x893ce7`/`0x893cf4`）。**「不弹窗」无法区分这三种情况。** 所以它确实不足以作为正向判据。

### 5.3 最接近的替代观测

按证据强度排序，三条候选：

**候选 A —— 已证伪（2026-09-15）**

原表述：`RuntimeGuard._frozen_runtime_supported` 与 `IntegrityService._running_from_python_source` 同构，若运行期观察到看门狗未启动，即可间接证明后缀判定为真。

**该前提不成立。** 第 3.2 节的修正给出了代码级证据：`_frozen_runtime_supported` 是**实例属性**——不在 `RuntimeGuard` 的 14 个 qualified 方法名中，全库仅出现 1 次（仅赋值，无读取）。属性不可调用，也没有读取点，因此不可能是 `start()` 的条件判断。

同时，`start()` 的实际语义与假设相反。`RuntimeGuard._spawn_watchdog` 的 docstring（VA `0x181cd385f`，明文）是：

> 创建监听管道并启动看门狗子进程，失败时清理资源。

即「无条件创建管道 + 启动子进程」，**没有任何「据此提前返回」的表述**。

**候选 B —— 随 A 一并失效**

候选 B 是「在 suffix 判定为假的配置下跑一次，看看门狗是否启动」的对照实验。它的设计前提是 A（存在一条由该判定控制的分支）。A 已证伪，对照无对象。

**候选 C（中等）——`.pyd` 侧信道**

`_ctypes.pyd`（payload 目录，116,224 B）存在于 `python312.dll` 的导入解析路径上。若在 payload 副本内替换该文件并让其中一段代码把 `sys.argv[0]` 的解析结果写入 payload 目录外的临时文件，即可直接读出该判定的输入。**但**：
- 这**修改了 payload**（虽不影响 `KeySteam.exe` 的 `body_sha256`，见 3.1）
- 会新增一个模块映射，可能触发 `_INJECTION_REASON_*`（`temp_rule` 的默认值**未能确证**）
- 它**直接读出 `bool`**，是三条候选里唯一直接观测输入的手段

**候选 D（最弱，但零改动）——磁盘差异比对**

`signature_facts.md` 已确认启动期 `%APPDATA%\Shikieiki\verification.cache`（605 B）存在。但因第 2.3 节已证明**五条磁盘链路全部与该返回值解耦**，此路径**不成立**——无法用磁盘 diff 区分 DISABLED 与 TAMPERED。列出仅为排除。

**未解线索（供后续）——`watchdog_enabled`**

`RuntimeGuard` 存在 `watchdog_enabled` 属性，且有**读取点**（出现 2 次：属性名 + 消费）。它与 `_scan_self_and_raise`、`_send_heartbeat`、`_HEARTBEAT_INTERVAL_SECONDS` 同区，是看门狗启停的**真实开关**。本轮未追它的赋值来源。若它由 argv 后缀或环境决定，则「看门狗未出现」这条观测的价值可以恢复——但**必须先证明其赋值链**，不能重犯候选 A 的错（把「名字相邻」当作「控制流绑定」）。

### 5.4 一句话结论

**`_integrity_runtime_supported()` 的返回值本身在进程外不可观测**——它是纯判定，两条分支的外部行为完全一致。原先被认为「最接近」的替代观测（候选 A：看门狗未启动 ⇒ 后缀判定为真）**已被证伪**：那个判定是实例属性、无读取点；`start()` 的行为是无条件启停看门狗。剩余可行路径只有候选 C（`.pyd` 侧信道，直接读出 `bool`，代价是引入可检测面），或把 `watchdog_enabled` 的赋值链查清后重建间接判据。

---

## 附：未确认项（诚实标注）

1. **`integrity_clean_reason` 与 `INTEGRITY_LOCKED_MESSAGE` 的字面文本**——属 `obfuscated_strings` 表（`rdata.bin` off=`0x8944f0`–`0x894d40`）的 `_decode_segment(key_hex, encoded_hex)` 编码。已定位全部键名（`integrity_clean_reason`@`0x89526a`、`integrity_locked_message`@`0x895282`）与密钥表（`_MESSAGE_KEY_HEX`@`0x894c9e`，key=`bcb44307fc0935e7eaf24c4eae144189f2b6267cde6463c7`），但 XOR 组合（逐字节 / 循环 / ASCII 字符级）均未产出合法 UTF-8。**未能解出，不编造。**
2. **`_classify_module` 的 `strict` / `temp_rule` 默认值**——无字面量锚点。文档措辞（`0x8964b0` docstring）明确 onefile DLL 全在 `%TEMP%` 且该规则"不可靠"，倾向默认关闭，但**未取得代码级证据**。
3. **`RuntimeGuard.start()` 是否以 `_frozen_runtime_supported()` 为提前返回条件**——常量表仅证明该判定与 `.py/.pyw` 同构，**未证明控制流绑定**。
4. **`shiki.json` / `version.json` / `cdn.jsdelivr.net`**——在 `rdata.bin` 中**零命中**。实际符号是 `src.client.update_service`、`AppUpdateInfo`、`official_dynamic_url`（域名值已混淆）。
5. **HOOK 判定是否存在内存态 IAT 遍历**——常量侧零证据（`GetProcAddress`/`IAT`/`LoadLibrary` 在 `runtime_guard` 常量块内零命中）。
