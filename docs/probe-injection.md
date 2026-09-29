# 进程内注入实测：能否消除 KeySteam v2.99 启动验证弹窗

**日期**：2026-09-16
**性质**：实测（非理论分析）。所有「能/不能」均附可重放命令与本机实测输出。
**样本**：`D:\03_Work\03_Develop\KeySteam v2.99\KeySteam.exe`
SHA256 `8f6dc31084888c64a7e442a91eeb51118dce051649a53076fa7412fc343d803a`（全程未变）

**坐标约定**：本文所有 `0x9...`（10 进制 9003891 等）均为 `rdata.bin` 的**节内偏移**。
节内偏移 → VA 加 `0x143d000`，再加 ImageBase `0x180000000`。

---

## 结论先行

**不能。**

不是「注入失败」，也不是「注入成功但被杀」——是**注入成功、载荷正常运行、弹窗行为完全未变**。

一句话因果：唯一可写的进程是 onefile 的 **bootstrap 父进程**，而弹窗属于它 fork 出来的 **Qt GUI 子进程**；
GUI 子进程的 DACL 被 `process_hardening` 定向拒绝 `PROCESS_CREATE_THREAD / PROCESS_VM_OPERATION / PROCESS_VM_WRITE`，
所有进程内注入手段都在同一个 `OpenProcess` 调用上失败（`err=5`）。而 bootstrap 阶段注入的载荷**看不到 GUI 进程的任何窗口**，
因为它们是**不同进程**。

三种情形的实测归属：

| 情形 | 是否发生 | 证据 |
|---|---|---|
| 注入手段失败（权限/DACL） | **发生**（对 GUI 进程） | `OpenProcess(VM_WRITE)` → `err=5`，四轮一致 |
| 注入成功但被 RuntimeGuard 杀掉 | **未发生** | 注入 bootstrap 成功，存活至我主动结束，无 kill |
| **注入成功但弹窗行为未变** | **发生**（对 bootstrap） | `stage=1→4`，`dlg_found=0 win_total=0`，GUI 侧 8/2 形态不变 |

---

## 一、进程拓扑（一切结论的前提）

**实测**（`run_bootinj.ps1` 及独立复现）：

```
2344  (ppid=1708)   KeySteam.exe            win=0        ← 启动器 / onefile bootstrap
 └─ 23504 (ppid=2344) KeySteam.exe           win=200226   ← Qt GUI 主进程（弹窗在这里）
     └─ 28800 (ppid=23504) KeySteam.exe --watchdog \\.\pipe\keysteam_guard_66236805e66c81d9
```

**GUI 是 bootstrap 的子进程，不是同一进程。** 这是本任务最关键的事实——
`_NUITKA_ONEFILE_DLL_MODE` 下 bootstrap `LoadLibraryExW(main.dll)` 后**重新派生**一个进程来跑 Qt，
而不是在原地转入 GUI。

**判据混淆警告**：三个进程**同名同路径**，只能靠 `ppid` / 窗口数 / 命令行区分。
按名字取「第一个 PID」会瞄到 bootstrap（我第一轮就犯了这个错，见第六节）。

---

## 二、逐手段实测

### 2.1 核心障碍：定向 DACL

**实测矩阵**（`dbgmatrix.exe`，非管理员会话，记事本作同权限对照，同一时刻采样）：

| 权限 | 记事本（对照） | **KeySteam GUI** |
|---|---|---|
| `PROCESS_QUERY_LIMITED_INFORMATION` | OK | OK |
| `PROCESS_QUERY_INFORMATION` | OK | OK |
| `PROCESS_VM_READ` | OK | OK |
| **`PROCESS_VM_WRITE`** | OK | **DENIED (err=5)** |
| **`PROCESS_VM_OPERATION`** | OK | **DENIED (err=5)** |
| **`PROCESS_CREATE_THREAD`** | OK | **DENIED (err=5)** |
| `PROCESS_SUSPEND_RESUME` | OK | OK |
| `PROCESS_SET_INFORMATION` | OK | OK |
| `PROCESS_TERMINATE` | OK | OK |
| `DebugActiveProcess` | **SUCCESS** | **FAILED (err=5)** |

**失败面被精确限定为三个权限**——正是 `process_hardening` 的常量：

```
0x1cd26fc  _INJECTION_ACCESS_MASK        (rdata 9000519)
0x1cd265f  _DENY_ACCESS
0x1cd266d  _NO_INHERITANCE
0x1cd270d  _PROCESS_CREATE_THREAD
0x1cd2727  _PROCESS_VM_OPERATION
0x1cd273e  _PROCESS_VM_WRITE
0x1cd267f  「阻止同权限普通进程直接向当前进程写内存或创建远程线程」（模块 docstring）
```

ACL 操作四件套（`src.security.process_hardening`）：`OpenProcessToken` → `GetSecurityInfo`
→ `SetEntriesInAclW` → `SetSecurityInfo`，配 `_TOKEN_USER` / `_TRUSTEE_IS_SID` / `_TRUSTEE_IS_USER`。

**时序**：`perlproc.exe` 以 150 ms 采样，GUI 进程**在其出现的第一个采样点（0.338 s）就已 `E5`**。
→ DACL 不是「弹窗出现后收紧」，而是 GUI 进程初始化早期即设好。**没有可抢的时间窗。**

（注：我最初假设「弹窗后才收紧」，被自己的 0.338 s 数据否证，此更正保留。）

### 2.2 `CreateRemoteThread` + `LoadLibraryW`

- 对 **GUI 进程**：`OpenProcess` 失败 `err=5`，**注入从未发起**。四轮实测一致。
- 对 **bootstrap**：**成功**。`LoadLibraryW 返回=0x3d500000`，远程线程 `wr=0`。
- 但见 2.6：载荷活在 bootstrap 里，对弹窗零影响。

### 2.3 `QueueUserAPC`

需要 `PROCESS_VM_WRITE`（写参数）+ `PROCESS_CREATE_THREAD`（取线程上下文）。
**与 2.2 撞同一道墙**，`OpenProcess` 阶段即失败，无需单独实测。
bootstrap 理论可做，但同样受 2.6 限制。

### 2.4 `SetWindowsHookEx`

机制上要求：`WH_CBT` / `WH_GETMESSAGE` 等需要目标有 GUI 线程且能向其写 hook 过程地址
→ 需要 `PROCESS_VM_WRITE` + `PROCESS_VM_OPERATION`。**同样是这三个被拒权限。**

关于「Qt 有自己的消息泵」：Qt 在 Windows 上**确实**跑标准 `GetMessage/DispatchMessage` 循环
（`qt6core.dll` 内部），所以 hook 类型层面无障碍——**障碍在 ACL，不在消息循环**。
即：即便 Qt 消息泵兼容，`SetWindowsHookEx` 仍会因无法写入 GUI 进程而失败。

### 2.5 `DebugActiveProcess`（唯一不走 `VM_WRITE` 的路）——**实测失败**

这是唯一未被 ACL 直接枚举否证的手段，故单独实测。

**关键对照**（排除「缺 `SeDebugPrivilege`」这一解释）：

```
会话身份：DESKTOP-<host>\<user>，IsAdmin=False
令牌权限：SeLockMemory / SeShutdown / SeChangeNotify / SeUndock / SeIncreaseWorkingSet / SeTimeZone
          —— 无 SeDebugPrivilege

DebugActiveProcess(notepad, pid=2984)          → True      （成功）
DebugActiveProcess(KeySteam GUI, pid=14812)    → False, err=5
```

**同一非管理员会话，对普通进程成功、对样本失败。**
这**彻底排除**「权限不足」的解释。失败原因是 `DebugActiveProcess` 内部需要
`PROCESS_VM_OPERATION`——正是被 `_INJECTION_ACCESS_MASK` 拒绝的三个之一。

（主会话曾提示注意区分「失败在 `SeDebugPrivilege`」与「失败在目标 DACL」；此处已用对照分离：
答案是**后者**。）

### 2.6 bootstrap 注入（唯一成功的注入）——**成功但不影响弹窗**

`bootinj.exe` 在样本启动后 **3 ms 轮询**捕获，抢在 Qt 建窗之前注入。

**实测输出**：

```
[ 0.729] 捕获到 1 个样本进程: 27780
[ 0.738]   pid=27780  wins=0 VM_WRITE=OK MODSNAP=OK   KeySteam.exe
[ 0.743] 试注入 pid=27780 可写=是
[ 0.744] 注入: 远程线程 wr=0 LoadLibraryW 返回=0x3d500000
[ 0.744] *** 注入成功于 pid=27780 ***
[ 0.755] SHM: stage=1 dlg_found=0 win_total=0
[ 1.174]   pid=26372  wins=0 VM_WRITE=E5 MODSNAP=DENY    ← GUI 子进程诞生（不同 PID）
[ 1.174] SHM: stage=4 dlg_found=0 win_total=0           ← 载荷枚举完，看不到任何窗口
[ 1.596]   pid=26372  wins=5 VM_WRITE=E5 MODSNAP=DENY
[20.857]   pid=27780  wins=0 VM_WRITE=OK MODSNAP=OK     ← bootstrap 依然存活
[20.857]   pid=26372  wins=8 VM_WRITE=E5 MODSNAP=DENY   ← 弹窗形态 8 窗口
```

**载荷（`ksprobe.dll`）自身回报的观测**：`stage=1`（DllMain 进入）→ `stage=4`
（`EnumWindows` 完成，`dlg_found=0`、`win_total=0`）。

**结论**：载荷成功运行在 bootstrap 进程内，但 bootstrap **永远没有窗口**（`wins=0` 僵持 20 秒），
因为 Qt 的一切都在子进程 26372 里。**注入 bootstrap 对弹窗无任何作用。**

---

## 三、`RuntimeGuard` 检测能力

### 3.1 静态证据（均**未经运行验证**）

**`_KNOWN_HOOK_FILE_NAMES` 的完整常量表 —— 22 条**（`rdata` 偏移 9007534–9007855，逐串转储）：

```
minhook.dll        minhook.x64.dll
detours.dll        mhook.dll
easyhook.dll       easyhook32.dll    easyhook64.dll
frida-agent.dll    frida-gadget.dll  frida-core.dll    frida-gum.dll
scyllahide.dll
blackbone.dll      blackbone32.dll   blackbone64.dll
injector.dll       inject.dll
hook.dll           h.dll
overlay.dll        reshade.dll       reshade64.dll
```

**系统 DLL 白名单**（同区 9007610–9007530，紧邻名单之前，用于排除误报）：

```
xinput1_4.dll  xinput1_3.dll  xinput9_1_0.dll  xinput.dll
version.dll    winmm.dll      winmmbase.dll
d3d9.dll       d3d11.dll      dinput8.dll      dinput.dll
wsock32.dll
```

> **计数更正**：本报告初稿写「21 条」，漏计 `reshade64.dll`（`rdata` 9007834）。
> 精确边界为 `[9007534, 9007855)`，共 22 条，已复核。

注入原因常量：`_INJECTION_REASON_HOOK` / `_INJECTION_REASON_TEMP` / `_INJECTION_REASON_USER_DIR` / `_INJECTION_REASON_EXE`
对应文案：`疑似钩子注入模块` / `模块从临时目录加载/非应用解压目录` / `模块从非可信用户目录加载` / `异常进程镜像映射`。

**`temp_rule` 的 docstring 原文（`rdata` 9004273–9004535）**：

> `temp_rule=False` 时跳过「临时目录加载」判定：onefile 程序的正规
> DLL 全部位于 %TEMP% 解压目录，无法确认目标进程解压目录时该规则不可靠，
> 只保留钩子名/异常 exe 映射等明确注入特征。

**这解释了为什么可以把 DLL 放到任意路径**：对 onefile 形态，临时目录规则被跳过，
只剩「钩子文件名」与「异常 exe 映射」两条判据。

**`_has_hard_injection` 的 docstring（`rdata` 9006173–9006496）**：

> Only definite injection features (hook DLL / abnormal exe mapping).
> DLLs under user-writable or temp directories are often loaded by
> legitimate software such as IMEs; killing on those would crash normal
> users (e.g. after clicking the captcha input). A failed scan must not
> be treated as injection either.

**`RuntimeGuard` 类 docstring（`rdata` 9008119–9008406）**：

> 看门狗 / 注入检测。主进程侧守护定时扫描自身加载模块，并通过命名管道向独立看门狗进程
> 发送心跳。检测到可疑模块或看门狗异常时，通过 `on_tamper` 回调锁定程序，
> 并请求看门狗强制结束主进程。

**方法/常量符号**：`_scan_self_and_raise`、`_SELF_SCAN_INTERVAL_SECONDS`、
`_WATCHDOG_SCAN_INTERVAL_SECONDS`、`_HEARTBEAT_INTERVAL_SECONDS`、
`_WATCHDOG_HEARTBEAT_TIMEOUT_SECONDS`、`_WATCHDOG_RESTART_LIMIT`、
`_WATCHDOG_CONNECT_TIMEOUT_SECONDS`、`_trigger_tamper`、`_request_watchdog_kill`、
`_kill_main_process`、`_has_hard_injection`、`_process_alive`。

**降级路径文案**：`运行时守护进程多次异常` / `已降级为仅自检模式` /
`运行时守护进程重启失败` / `有界重启看门狗` / `重试用尽或启动失败时降级为仅自检模式`。
→ 看门狗有**有界重启**机制，失败则降级，不是无条件致命。

**kill 动作序列（静态推断）**：
`_scan_self_and_raise` 发现 `_has_hard_injection == True`
→ `_trigger_tamper`（`on_tamper` 回调，文案含「回调锁定程序」）
→ `_request_watchdog_kill` → 经管道发 `json.dumps({"kill":..., "reason":...})`
→ 看门狗 `_kill_main_process`。

**未取得代码级证据的点**（见第五节）：
- `temp_rule` / `strict` 的**默认值**
- 各 `_*_INTERVAL_SECONDS` 的**数值**
- 检测到之后的**具体延迟**（是立即 kill 还是先弹「倒卖可耻」）
- `_KNOWN_HOOK_FILE_NAMES` 匹配是**全路径**还是**basename**（从 `endswith('.dll')`/`endswith('.exe')`
  的邻近符号看像是 basename/后缀匹配，但未确证）

### 3.2 运行验证：**未能触发**（如实记录）

**实测**：把 `minhook.dll`（名单内）改名注入 bootstrap，成功加载（`LoadLibraryW=0x3d500000`），
载荷运行至 `stage=4`，**20 秒全程无任何 kill 或警告迹象**：

```
[ 0.744] *** 注入成功于 pid=27780 ***
[20.857]   pid=27780  wins=0 VM_WRITE=OK MODSNAP=OK   KeySteam.exe   ← 未被杀
```

**两种可能的解释，本任务无法区分**：

1. `RuntimeGuard` 的模块扫描**只覆盖 GUI 主进程**（`_scan_self_and_raise` + `Process(...).memory_maps()`），
   而 bootstrap 里那个 `RuntimeGuard` 实例尚未启动或已交出控制权；
2. 检测到了但因为 `temp_rule` 或 `strict` 的宽松设置而**未升级为 kill**。

**这不能推断「检测不存在」**——注入从未成功进入 GUI 进程，检测逻辑**没有机会被触发**。
GUI 侧的检测能力**本任务无法实测**，因为 `OpenProcess` 在 `VM_WRITE` 上就失败了。

> **对既有文档的勘误提示**：主会话在 `docs/suppressing-the-dialog.md` 中曾把
> 「注入会撞上 RuntimeGuard」当作既成事实引用。**本次静态证据不支持这句断言**——
> 静态常量只证明「检测逻辑存在」，不证明「一定能检测到并 kill」。
> 特别是 `temp_rule` 对 onefile 形态**明确跳过**临时目录判定，只留钩子名一条。
> 建议改为「检测逻辑存在，但对 onefile 形态的覆盖面未实测」。

---

## 四、为什么「弹窗失效」这条路整体不成立

即便解决 ACL（例如以管理员 + `SeDebugPrivilege` 运行注入器），仍有两道独立障碍：

**障碍一：`RuntimeGuard` 未验证的检测面。** 见 3.2，无法排除。

**障碍二（更根本）：弹窗是校验链的**正常分支输出**，不是可独立关闭的 UI 装饰。**
弹窗链 `_start_initialization → _check_cached_verification → _fetch_verification_config
→ _handle_verification_config_* → VerificationDialog` 是同步推进的；
`VerificationDialog` 是**模态**且被显式 `setModal`。
关掉它（或隐藏它）**不会**让 `verification_cache_accepted`（`0x86d749`）被发出，
于是槽 `_continue_initialization`（`0x86d765`）**永不会被调用**，
`_preload_memory_images` 不会执行——程序停在初始化中段。

**即：让弹窗「不出现」与让程序「正常可用」是两件事。** 前者能在 bootstrap 侧做实验，
后者要求命中校验链，而校验链的输入是**服务端签名的票据**。

这印证既有的 ADR 0001（走合法票据路线）。本报告只是从**注入**这个角度再确认了一次：
即便注入通道完全打通，它解决的也不是「让程序进入可用状态」这个问题。

---

## 五、「未能确证」清单

逐条列出**查不到代码级证据**的点，不含已实测项：

1. **`temp_rule` / `strict` 的默认值。**
   其 Python 函数签名默认参数在 `.text` 的 code object 常量区；
   在 `.rdata` 只有符号名与 docstring，无默认值。
   `.text` 中直接搜 UTF-8 串与 double 字面量均零命中（Nuitka 已把常量编译进 C 层，非 marshal 形态）。
   **得出该值需要运行期反射**（导入 `main.dll` 后读函数对象），本任务未做——
   因为即便拿到默认值，也改变不了 2.1 的 ACL 结论。
2. **各 `_*_INTERVAL_SECONDS` 的具体数值。** 同上原因。
3. **`_KNOWN_HOOK_FILE_NAMES` 的匹配语义**（全路径 vs basename）。
   邻近符号有 `endswith` + `u.dll` / `u.exe`，**倾向** basename 后缀匹配，但未构造实验确证。
4. **检测触发后的精确延迟与是否先弹「倒卖可耻」。** 需要一次成功的 GUI 侧注入才能观测，未取得。
5. **`strict=True` 时 `_INJECTION_REASON_TEMP` / `_INJECTION_REASON_USER_DIR` 是否升级为 kill。**
   从 `_has_hard_injection` docstring 看默认**不**升级（「killing on those would crash normal users」），
   但未取得该分支的代码级证据。
6. **GUI 进程的 `RuntimeGuard` 是否真的在扫描。** 无法实测（进不去）。
7. **`DebugActiveProcess` 若在管理员 + `SeDebugPrivilege` 下是否成功。**
   本会话非管理员，无法验证。**这是本报告最大的未覆盖面**——
   若需要绝对结论，应在提权会话重跑 `dbgmatrix.exe`。

---

## 六、方法学备注（踩过的坑，供复现者避让）

1. **同名三进程**：`KeySteam.exe` 同时存在 bootstrap / GUI / watchdog 三个同名进程。
   按名字取第一个 PID 会瞄到 bootstrap（无窗口，注入无效）。
   **必须用 `ppid` + 窗口数 + 可写性三重判据。**
2. **进程名可被改写**：兄弟会话的 `_re\probe\exe\KeySteam_probe.exe` 与本样本同名不同路径。
   **必须按 `ExecutablePath` 前缀筛选**，并排除 `\_re\probe\`。
3. **PowerShell 5.1 的 GBK 陷阱**：脚本含非 ASCII 注释时，PS 5.1 按 GBK 解码，
   会把注释后一行的 `$var = ...` 吞进注释，导致变量未定义且报错位置误导
   （表现为 `RedirectStandardOutput 参数为空`）。
   **所有 `.ps1` 一律写成纯 ASCII。**
4. **硬编码宽字符长度**：`_wcsnicmp(path, L"...", 39)` 中 39 是我手数的字符数，
   实际 `D:\...\KeySteam v2.99\` 是 **37** 个 `wchar_t`。多了 2 就永不匹配。
   **一律用 `wcslen()` 运行时求长。**
5. **`$args` 是 PowerShell 保留变量**：赋值会被忽略，需换名（我用 `$pargs`）。
6. **不得用 `timeout` 包裹样本**：会留孤儿。编排脚本一律显式 `Stop-Process` +
   事后核对残留。

---

## 七、环境完整性（每轮核对）

| 项 | 基线 | 本次终态 |
|---|---|---|
| `KeySteam.exe` SHA256 | `8f6dc310…803a` | `8f6dc310…803a` **未变** |
| 主号目录 `userdata\<main-id>` 文件数 | 537 | **537**（未写入） |
| `config\stplug-in` 文件数 | 5 | **5** |
| 我的样本进程残留 | 0 | **0** |
| `_re\probe\` 兄弟会话进程 | 5940 / 17304 / 25504 | **未触碰，仍存活** |
| 我创建的管道残留 | 0 | **0** |

样本本体**未做任何修改**；全部为运行期行为。

---

## 八、可重放命令

### 8.1 重建节转储

```bash
mkdir -p /tmp/ks2 && python3 - <<'PY'
import struct
p='/mnt/d/03_Work/03_Develop/KeySteam-v2.99/_re/bin/main.dll'
d=open(p,'rb').read()
e=struct.unpack_from('<I',d,0x3c)[0]
nsec=struct.unpack_from('<H',d,e+6)[0]
opt=e+24; sizeopt=struct.unpack_from('<H',d,e+20)[0]; secs=opt+sizeopt
for i in range(nsec):
    o=secs+i*40
    name=d[o:o+8].rstrip(b'\0').decode()
    vsize,vaddr,rawsize,rawptr=struct.unpack_from('<IIII',d,o+8)
    if name in ('.rdata','.text'):
        out='/tmp/ks2/'+name.strip('.')+'.bin'
        open(out,'wb').write(d[rawptr:rawptr+rawsize])
        print(name, out, rawsize, 'VA=%x'%vaddr)
PY
```

预期：`.rdata` 9504256 B、`.text` 21214208 B。

### 8.2 提取 hook 名单（复现 3.1 的常量表）

```bash
python3 - <<'PY'
import re
d=open('/tmp/ks2/rdata.bin','rb').read(); base=0x143d000
s=9007500; e=9007900
for m in re.finditer(rb'[\x20-\x7e]{2,}', d[s:e]):
    print(f"{s+m.start():8d} VA={base+s+m.start():#010x} {m.group().decode()!r}")
PY
```

### 8.3 编译注入工具（mingw 的 `-B` + `-I` + Windows 路径，见 `host/build.sh`）

```bash
# 配方要点：4 个 -B 覆盖 argv[0] 派生失败，-I 补头文件，路径统一转 Windows 形态
GCC_WSL="/mnt/c/Program Files/mingw64/bin/x86_64-w64-mingw32-gcc.exe"
GCC_VER="$(ls -1 '/mnt/c/Program Files/mingw64/libexec/gcc/x86_64-w64-mingw32/' | sort -V | tail -1)"
MW='C:\Program Files\mingw64'
"$GCC_WSL" -municode -O2 \
  -B "$MW\\libexec\\gcc\\x86_64-w64-mingw32\\$GCC_VER\\" \
  -B "$MW\\bin\\" -B "$MW\\x86_64-w64-mingw32\\lib\\" \
  -B "$MW\\lib\\gcc\\x86_64-w64-mingw32\\$GCC_VER\\" \
  -I "$MW\\x86_64-w64-mingw32\\include" \
  "$(wslpath -w probe.c)" -o "$(wslpath -w probe.exe)" -lpsapi -lntdll -luser32
```

### 8.4 复现 DACL 矩阵（结论 2.1）

```powershell
# 先起一个记事本作对照，再起样本，然后跑矩阵
powershell -NoProfile -ExecutionPolicy Bypass -File .scratch\ksinj\run_dbgmatrix.ps1
```

### 8.5 复现 bootstrap 注入（结论 2.6）

```powershell
# 探针必须先跑（3ms 轮询抢在 Qt 建窗前）；脚本已按此顺序编排
powershell -NoProfile -ExecutionPolicy Bypass -File .scratch\ksinj\run_bootinj.ps1 `
  -Dll "D:\…\.scratch\ksinj\payload\minhook.dll" -DurMs 20000
```

### 8.6 工具清单

全部位于 `D:\03_Work\03_Develop\keysteam-unlock-spike\.scratch\ksinj\`：

| 工具 | 作用 |
|---|---|
| `probe.c` / `probe.exe` | 综合探针：CRT/APC/debug 三手段 + 窗口形态 + 生存监控 |
| `payload.c` / `payload.dll` | 注入载荷：枚举窗口、按模式隐藏/关闭/重启用 |
| `acltest.c` | 初版 DACL 对照 |
| `acltime.c` | 时间序列 ACL（发现「与时间无关」） |
| `perlproc.c` | **逐进程 ACL 矩阵（2.1 的主证据）** |
| `dbgtest.c` | `DebugActiveProcess` 单点测试 |
| `dbgmatrix.c` | **调试器路径归因矩阵（2.5 的主证据）** |
| `bootinj.c` | **bootstrap 注入缝隙实测（2.6 的主证据）** |
| `payload\*.dll` | `ksprobe.dll`（自定义名）+ `minhook.dll`/`frida-agent.dll` 等名单内名副本 |

---

## 九、对既有结论的影响

1. **ADR 0001（走合法票据）得到加强**，而非削弱。
   注入路线在**三重**独立障碍上失败（GUI DACL、bootstrap 是另一进程、RuntimeGuard 未验证），
   且即便全部打通也不产出可用状态（第四节障碍二）。
2. **`docs/suppressing-the-dialog.md` 需勘误一处**：
   把「注入会撞上 RuntimeGuard」从「既成事实」降级为「逻辑存在，覆盖面未实测」。
   实测反证：名单内 `minhook.dll` 注入 bootstrap 后 20 秒未被杀。
3. **新增可直接引用的事实**：
   - GUI 是 bootstrap 的**子进程**（`_NUITKA_ONEFILE_DLL_MODE` 下 fork，非原地转 GUI）；
   - `process_hardening` 的拒绝面 = 精确三权限，**非**全面拒绝（`TERMINATE`/`SUSPEND_RESUME` 仍放行）；
   - `_KNOWN_HOOK_FILE_NAMES` 完整 **22 条**常量表（见 3.1）；
   - `temp_rule` 对 onefile 形态**显式跳过**临时目录判定（docstring 原文）。
