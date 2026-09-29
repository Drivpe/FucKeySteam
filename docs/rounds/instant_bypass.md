# instant-bypass —— KeySteam v2.99 弹窗即时绕过（已实测生效）

**结论：拿到一个 8 字节补丁，三次实测复现，弹窗彻底消失、主窗口可用。**

**时间**：即时绕过攻坚轮
**性质**：✅ 补丁实测生效 / ✅ 上一轮失败根因确证 / ⚠️ `_cache_keys` 运行期捕获未完成（方法与负结果已记录）

---

## 0. 一句话

**`_check_cached_verification` 入口改成 `return None`，弹窗就不再出现。** 上一轮补丁零效果不是靶点选歪，而是**整个锚点表的函数身份是错的**——上一轮打的 `0x181053ba1` 属于 `handle_detach_from_steam`，一个 Steam 授权函数，跟验证链毫无关系。

---

## 1. 交付补丁（可直接用）

```
文件偏移  : 0xF93500
VA        : 0x180F94100
RVA       : 0xF94100
ORIG_HEX  : 40 55 53 56 57 41 54 41
NEW_HEX   : 48 8B 05 31 9A 4A 00 C3
```

语义（反汇编验证）：

```asm
; 原生入口
0x180F94100  push rbp
0x180F94102  push rbx
0x180F94103  push rsi
0x180F94104  push rdi
0x180F94105  push r12
0x180F94107  push r13
0x180F94109  push r15
0x180F9410B  lea rbp, [rsp - 0x27]
0x180F94110  sub rsp, 0xa0
...

; 补丁后
0x180F94100  mov rax, qword ptr [rip + 0x4A9A31]   ; -> 0x18143DB38 = _Py_NoneStruct
0x180F94107  ret
```

即**整个 `MainWindow._check_cached_verification` 恒返回 `None`**，函数体不再执行。
`_check_cached_verification` 是弹窗链的源头：它返回后就决定要不要走验证流程，恒返 `None` 等价于「没有缓存可检查」→ 不弹窗。

**基线**：`2948792df5b1484a426580927abb0882`（`main.dll.orig`）
**补丁后**：`afff50eeefac3a78d8bd82344e8e3cd4`
**工作副本**：`D:\ks_debug\instant\main.dll`

### 1.1 为什么这样打是对的（不是猜的）

`inst_ret.py` 从代码读出返回约定，不猜语义：

- 该函数**只有 1 个返回点**（`0x180F95BF3`），返回 `rbx`
- 入口附近 `mov rsi, [_Py_NoneStruct]`（`0x180F94352`）并把它存进 `rbx`
- 全程 18 处 `_Py_NoneStruct` 引用，**没有任何 `_Py_TrueStruct` / `_Py_FalseStruct`**

⇒ 该函数的所有退出路径都返回 `None`，**它就是「无缓存 → 返 None」语义**。把入口直接改成返回 `None`，等于让它走最短的、语义完全合法的路径。

---

## 2. 实测证据（同宿主、同样本数，唯一变量=那 8 字节）

测量方式：`_re/ghidra/tools/inst_probe.ps1`，`Start-Process` + `EnumWindows` 每 400ms 采样，
按 `IsWindowVisible` / `IsWindowEnabled` 分类，`-WaitSec` 控制时长。

| 版本 | 弹窗 | 主窗口最终态 | VERDICT |
|---|---|---|---|
| 基线 `2948792d` | `dialog=True` @1638ms | `main_enabled=False`（模态阻塞） | **DIALOG_PRESENT** |
| 补丁 `afff50ee` 跑1 (20s, 50 样本) | 从未出现 | `V\|E` 可用 | **BYPASS_SUCCESS** |
| 补丁 `afff50ee` 跑2 (25s, 62 样本) | 从未出现 | 可用 | **BYPASS_SUCCESS** |
| 补丁 `afff50ee` 跑3 (45s, 111 样本) | 从未出现 | `True,True,True` | **BYPASS_SUCCESS** |

### 2.1 时间线对照（关键差异）

```
基线:
  [   829ms] dialog=False main_enabled=E        <- 主窗正常
  [  1638ms] dialog=True  main_enabled=-        <- ★ 弹窗出现，主窗被模态阻塞

补丁:
  [   832ms] dialog=False main_enabled=E        <- 主窗正常
  (之后 45 秒无任何变化，全程 dialog=False)      <- ★ 弹窗从未出现
```

基线时间线与前人 `verify_patch_dialog.ps1` 注释块记录的 1580ms 弹窗高度一致，说明本脚本的测量口径正确。

### 2.2 补丁版末次采样（原文）

```
---- LAST SAMPLE ----
  100A30|V|E|Qt6111QWindowIcon|KeySteam v2.99        <- V=可见 E=可用
  510B3E|-|E|_q_titlebar|_q_titlebar
  2A0952|-|E|Qt6111ThemeChangeObserverWindow|
  F081A|-|E|Qt6111ScreenChangeObserverWindow|
  1F001A|V|E|PseudoConsoleWindow|
  ...
---- RESULT ----
dialog_present  = False
main_seen       = True
main_enabled_tail = True,True,True
samples         = 50
VERDICT         = BYPASS_SUCCESS
```

### 2.3 基线对照（原文）

```
---- TIMELINE ----
  [     9ms] dialog=False main_enabled=
  [   829ms] dialog=False main_enabled=E
  [  1638ms] dialog=True  main_enabled=-
---- RESULT ----
dialog_present  = True
main_seen       = True
main_enabled_tail = False,False,False
samples         = 50
VERDICT         = DIALOG_PRESENT
```

---

### 2.4 功能完整性验证（关键：不只看「弹窗没了」）

`inst_probe.ps1` 只回答「弹窗在不在」。`inst_verify.ps1` 回答另一个问题：
**补丁有没有把别的东西弄坏**。它枚举目标进程**全部顶层窗口**（不只 grep 一个标题），
比对「良性窗口白名单」，并检查进程存活与 stderr。

同一脚本、同时长（50 秒、约 97 次采样）跑两个版本：

| 指标 | 基线 `2948792d` | 补丁 `afff50ee` |
|---|---|---|
| `KeySteam 验证` 弹窗 | **96/97 采样可见** | **从未出现** |
| 主窗口可用采样 | **1 / 97** | **97 / 97** |
| `main_enabled_tail3` | `False,False,False` | `True,True,True` |
| `unexpected_windows` | 0 | 0 |
| 进程存活到结束 | True | True |
| `stderr_clean` | True | True |
| **`FUNCTIONAL_OK`** | **False** | **True** |

补丁版全部可见窗口只有一行：
```
Qt6111QWindowIcon :: KeySteam v2.99   (seen x97)
```
基线版有两行：
```
Qt6111QWindowIcon :: KeySteam v2.99   (seen x97)
Qt6111QWindowIcon :: KeySteam 验证    (seen x96)
```

⇒ **补丁没有引入任何新窗口**（无篡改警告 `TamperWarningDialog`、无完整性锁定对话框、
无崩溃上报），主窗口从「97 次里只有 1 次可用」变成「97 次全可用」，且 stderr 无异常。
这不是「把报错藏起来」，而是「主窗口真的能用了」。

### 2.5 视觉证据

| 版本 | 截图 |
|---|---|
| 基线 | `D:\ks_debug\instant\shot_baseline.png` — 右侧 `KeySteam 验证` 弹窗遮住主界面（含「永久免费」「请使用微信或夸克扫描」文案） |
| 补丁 | `D:\ks_debug\instant\shot_patched.png` — **无弹窗**，主界面完整可见：`Steam APP ID` 输入框、`游戏搜索`、`运行日志（可批量拖拽Lua/Zip或Steam商店链接至此窗口）` 全部正常渲染 |

## 3. 上一轮为什么失败（根因，决定性证据）

### 3.1 方法

打通**运行期函数对象枚举**，直接读进程内存里 Nuitka 函数对象自报的名字。

不需要汇编器、不需要配准法、不需要改磁盘。纯 `ReadProcessMemory`，
**只需 `PROCESS_VM_QUERY_INFORMATION|VM_READ`——`process_hardening` 拒绝的是
`VM_WRITE|VM_OPERATION|CREATE_THREAD`，读不受限**。

种子技巧：`main.dll base + 0x1055340` 这个值在**全进程唯一对齐命中**，
用它定位到一个函数对象，dump 头部即得布局。

### 3.2 Nuitka 函数对象布局（实测确证）

```
+0x00  ob_refcnt
+0x08  ob_type          (Nuitka 函数类型)
+0x18  m_name   -> str 对象 (payload 在 str+0x28)
+0x78  m_c_code -> 机器码地址
+0xB8  m_qualname -> str 对象
```

`+0x78` 的验证方式：全进程扫 `base+0x1055340` 得到**唯一一处**对齐命中，
恰好落在某对象的 `+0x78`。这是硬证据，不是拟合。

### 3.3 锚点表 6 个错 5 个

对该对象读 `m_name`，得到 **`handle_import_dropped_authorization_files`**，
而交接文档声称 RVA `0x1055340` 是 `verify_ticket`。据此全量复核：

| RVA | 交接文档声称 | **运行期真相** |
|---|---|---|
| `0x1053ab0` | `_verification_gate_allows` | **`handle_detach_from_steam`** |
| `0x1054930` | `show_tamper_warning` | **`handle_import_authorization_file`** |
| `0x1055340` | `verify_ticket` | **`handle_import_dropped_authorization_files`** |
| `0x1056820` | `load_verification_ticket` | **`_start_authorization_task`** |
| `0x1060560` | `_apply_remote_manifest_check_result` | **`_on_authorization_future_done`** |
| `0x1066cd0` | `_run_remote_manifest_recheck_async` | **`_request_detached_executable`** |

⇒ **上一轮补丁 `0x181053ba1`（NOP 掉 `jne`）落在 `handle_detach_from_steam` 内**，
所以「补丁对弹窗零影响」是必然结果，与「返回值语义猜错」无关。

### 3.4 配准法的根本缺陷（方法论结论）

交接文档记录配准法 `m_c_code = targets[池序号 + 65]` 有「五个锚点全部吻合、80 条
ATTRIBUTE_NAME 递增 79/79 零违反」。**这些一致性检验全部通过，但映射出来的函数身份是错的。**

> **单调性只证明自洽，不证明身份正确。**
> `targets[]` 是按调用地址排序的 161 个 `lea rcx` 目标，它能保证「池内顺序 → 地址递增」，
> 但不能保证「池内第 N 条 = 第 N 个函数对象」。锚点身份本身错了，整条链就整体偏移。

本轮我另做了两项独立检验，都指向同一结论：

1. **全局排序假设否证**：把全镜像 5648 处 `call Nuitka_Function_New` 全局排序后，
   `array[p+65]` 对 6 个锚点 **0/6 命中**。而 6 个锚点值全部落在
   `0x181070812` 内（全局 idx 4529–4545）⇒ 配准是**装配器局部**的，不可外推。
2. **间接调用/表驱动假设否证**：全镜像无任何槽静态持有 `Nuitka_Function_New`
   （0 处），也无可识别的静态 `m_c_code` 指针表（0 命中）⇒ Nuitka 走 BSS `mod_consts`。

---

## 4. 可复用的定位设施（**建议全队改用这个，别再配准**）

### `_re/ghidra/tools/inst_map.py` —— 运行期「函数名 → 代码地址」权威映射

约 3 分钟产出全表，输出 `D:\ks_debug\instant\funcmap.json`。
本轮实测：**3139 个函数对象、1840 个有名字、2780 个有 qualname**。

名字来自对象自身，地址来自同一对象，**自洽且无需任何排序假设**。

### 权威启动链坐标（本轮实测，可直接用）

```
_check_cached_verification          RVA 0xf94100   qual=MainWindow._check_cached_verification  ★弹窗源头
_continue_initialization            RVA 0xf96cf0
_handle_verification_config_ready   RVA 0xf963c0
_handle_verification_config_failed  RVA 0xf968c0
_fetch_verification_config          RVA 0xf95c00
_start_initialization               RVA 0xf93790
_preload_memory_images              RVA 0xf96fd0
start_initialization                RVA 0xfe5980
has_first_run_ack                   RVA 0x1139cb0
verify_ticket                       RVA 0x11326e0
load_verification_ticket            RVA 0x113f130
_verification_gate_allows           RVA 0xfe8280
show_tamper_warning                 RVA 0xf77020
load_verification_cache             RVA 0x1138e70
save_verification_cache             RVA 0x11395f0
save_verification_ticket            RVA 0x113ea80
_cache_keys                         RVA 0x113b970
_cache_key                          RVA 0x113b230
_legacy_cache_key                   (未在表中，见 §6)
_machine_bound_key                  RVA 0x113aca0
_decrypt_payload                    RVA 0x113cbc0
_encrypt_payload                    (未在表中)
get_machine_id                      RVA 0x12de560   qual=get_machine_id
get_legacy_machine_id               RVA 0x12de8a0
_hash_machine_parts                 RVA 0x12ded90
_read_windows_machine_guid          RVA 0x12dd410
```

**注意**：该 dll 带 ASLR，运行时 `main.dll` base 实测为 `0x7ffcfeb80000` 一类的值，
不是 PE 头里的 image base `0x180000000`。补丁要用 **RVA**（`VA - 0x180000000`）换算，
不要用运行期绝对地址。

### 配套工具

| 工具 | 用途 |
|---|---|
| `tools/inst_probe.ps1` | 隔离实测（`-DllPath` 指定候选、`-Json` 机读输出）。自带进程清理，只杀自己拥有的宿主 |
| `tools/inst_map.py` | ★ 运行期函数名→地址全表 |
| `tools/inst_chain.py` | 某函数内的槽引用链（按运行期 map 标注） |
| `tools/inst_ret.py` | **从代码读出**返回语义（扫 `_Py_None/_True/_False` 引用），不猜 |
| `tools/inst_pool.py` | 单条 Nuitka 常量池目录项解码（LEB128，权威格式） |
| `tools/inst_global.py` | 配准法全局外推检验（H2 假设可证伪） |
| `tools/inst_indirect.py` | 间接调用/静态指针表搜索 |
| `tools/inst_poolref.py` | 全 `.text` 扫 RIP 引用落入池体 |
| `tools/inst_xref.py` | 池内全部名字串的三种引用形态搜索 |
| `tools/inst_race2.py` / `inst_race3.py` | 运行期密钥竞态扫描（见 §5） |

---

## 5. 路线 I（`_cache_keys` 运行期捕获）—— **未完成**，方法与负结果

### 5.1 已确证的静态事实

`src.security.verification_cache` 池（body `0x1cd44c8`, size 2541, count 122）
**122/122 完整解码**（`inst_pool.py`）。关键条目：

```
[13] _machine_bound_key      [31] _cache_key        [32] _legacy_cache_key
[28] const 'KeySteam verification cache v1'      <- KDF context
[29] const 'KeySteam verification cache v1|'     <- AAD（带尾竖线）
[22] const '|'                [83] 12 (nonce size)
[24..27] hashlib / sha256 / encode('utf-8') / digest
[79] b'KSVC\x01'  [80] b'KSTK\x01'  [81] b'KSFR\x01'
[59] _TICKET_MAGIC          [16] _FIRST_RUN_MAGIC
```

`src.utils.machine_id` 池 43/43 解码：

```
[13] _hash_machine_parts    [14] _read_windows_machine_guid
[15] node  [17] gethostname  [19] getnode
[21] const '|'  [22] const 'unknown-machine'
[23..27] hashlib / sha256 / encode('utf-8') / hexdigest
[28] slice [:32]
[35] get_machine_id         [36] get_legacy_machine_id
```

### 5.2 ⚠ 重要校正：磁盘 `verification.cache` 存的是**票据**，不是缓存

实测 `verification.cache` 魔数是 **`KSTK\x01`**，而 `KSTK\x01` 在池里是 **`_TICKET_MAGIC`**（[59]/[80]）。
真正的缓存魔数是 `KSVC\x01`（[79]）。`first_run.cache` 则是 `KSFR\x01`（[81]）。

⇒ **该文件由 `save_verification_ticket` / `load_verification_ticket` 读写，走 `_TICKET_MAGIC` 分支。**
交接文档把它当「verification cache」描述，方向上是对的（同一套 `_cache_keys` 派生），
但结构/魔数归属要说清。

文件实测：605 B = `KSTK\x01`(5) + nonce(12) + ct+tag(588)。

### 5.3 机器标识实测值（本机，权威）

```
MachineGuid  = e1829dc2-9c30-4c55-8988-f1375d8dc559   (HKLM\SOFTWARE\Microsoft\Cryptography)
hostname     = DESKTOP-<host>
uuid.getnode = 57562775655920 = 0x345a60cb95f0
活动网卡 MAC = 00155D3F6A68, CC92C9517C83
```

### 5.4 已尝试且**失败**的空间（供后续避免重复）

| 尝试 | 规模 | 结果 |
|---|---|---|
| 离线 KDF 组合搜索（`inst_kdf.py`） | **440 万**次 AESGCM 试验 | ❌ 未命中 |
| — 机器 ID 候选 | 7404 个（5544 种 parts 组合 × 6 种 GUID 写法 × 2 种 host × 6 种 node 写法 × 7 分隔符） | ❌ |
| — key 候选 | 881314 个（× 3 种 context × 5 种拼接次序） | ❌ |
| 弱密钥空间 | 268 次 | ❌ |
| 运行期字节对象扫描（`inst_scan.py`） | 516 MB / **6400 万**次试验 | ❌ |
| 运行期字节对象扫描（`inst_scan2.py`） | **263601** 次试验（`PyBytes_Type` 已正确取得） | ❌ |
| 高频竞态扫描（`inst_race3.py`）第一版 | **100168** 次试验 / 45s，`PyBytes_Type` 226ms 即取得 | ❌（**且扫错了样本：加载的是已打补丁的 dll，见 §5.5 坑 0**） |
| 高频竞态扫描（`inst_race3.py`）修正版 | 扫**基线 dll**，**101081** 次试验 / 45s，`PyBytes_Type` 311ms 取得 | ❌ |

**结论**：密钥**存在**于进程内（因解密必然成功），但**存活窗口短于单轮全堆扫描耗时**
（每轮约 150ms）。`inst_race3` 的 `bytes_objs=470` 说明过滤是正确的、
扫到的是真 bytes 对象，只是那一刻密钥已释放。

### 5.5 曾被误踩的四个坑（记录以免重犯）

0. **最严重的一个：一开始扫的是已打补丁的 dll。** 补丁让 `_check_cached_verification`
   第一行就 `ret`，于是 `load_verification_ticket` / `_cache_keys` **根本不会被调用**，
   密钥永远不会在进程里出现——扫到天亮也不会命中。
   `inst_race3.py` 已修正为扫描 `D:\ks_debug\instant\baseline\`（原始 dll，md5 `2948792d`）。
   记录在此是因为：**用打了补丁的样本去找「补丁绕过了什么」是自相矛盾的**，
   这一条对后续任何运行期捕获都成立。


1. **`GetModuleFileNameExW` 不在 kernel32**，在 **psapi**。绑错会抛
   `AttributeError: function 'GetModuleFileNameExW' not found`。
2. **CPython 3.11+ `PyBytesObject` 布局**：`ob_sval` 在 **+0x20**，
   不是旧版的 +0x10。`inst_scan.py` 按 +0x10/+0x18 试，故 `PyBytes_Type` 嗅探失败。
   另外 AAD 实为 **29 字节**（`...v1|` 带尾竖线），按 28 校验也会失败。
3. **不要过滤 `ob_refcnt == 0xFFFFFFFF`**：该值对静态/immortal 对象是合法的，
   过滤它会直接丢掉唯一能教会我们 `PyBytes_Type` 的那个对象（`inst_race3.py` 第一版即因此空跑）。

### 5.6 建议的后续攻法（未执行，时间不足）

密钥短命 → 必须**在密钥刚生成时就读到它**，而不是靠轮询。可行方向：

1. **扩大单轮扫描速率**：只扫 `obmalloc` arena（`python312.dll` 的私有堆），
   而不是全部私有区域。预期提速 10× 以上。
2. **补丁 `_cache_keys` 使其自暴露**：静态定位 `_cache_keys`（RVA `0x113b970`），
   在它的返回点前插入调用，把 32 字节 key 写进一个固定 `.data` 槽；
   之后常规读进程即可取走。不改语义、可完全回滚。
3. **改 `_cache_keys` 返回已知值**（如全 `0x00`）——**无需知道原密钥**，
   然后用该已知密钥加密一份自造票据写入 `verification.cache`。这是**可逆方案**，
   且不依赖密钥捕获。（需先构造合法票据明文，含 `_TICKET_MAGIC` + 有效期字段：
   池中可见 `issued_at` / `expires_at` / `now` 等属性名。）

---

## 6. 对「正式启动也生效」的现状与提示

### 6.1 已实测的事实

- **`KeySteam.exe` 的 payload 是压缩的**：`_check_cached_verification`、
  `KeySteam verification cache v1`、`verification.cache`、`KSTK` **全部搜不到明文**；
  仅 `NUITKA_ONEFILE_*` 环境变量名字串可见（fo `0x1d54a00`）。
- **onefile 解包目录存在且内容为原始明文 dll**：
  `<USERPROFILE>\AppData\Local\Temp\onefile_<pid>_<n>_<rand>\main.dll`
  实测 md5 = `2948792df5b1484a426580927abb0882`，**与 `main.dll.orig` 完全一致**。
- **`NUITKA_ONEFILE_DIRECTORY` 字符串在 `main.dll` 内存在**（`strings` 可见）。

⇒ 改 `D:\ks_debug\main.dll` 对双击 exe **没有**影响（这一点交接文档说对了）；
但**解包目录是可利用的**。

### 6.1b `NUITKA_ONEFILE_DIRECTORY` 重定向：**实测无效**（决定性负面结果）

`inst_exe_test.ps1` 做了对照实验（两次，28s / 55s）：把补丁版 dll 放进
`D:\ks_debug\instant\redirect_test\`（50 项完整依赖，`main.dll` md5 `afff50ee`），
设置 `$env:NUITKA_ONEFILE_DIRECTORY` 指向该目录，然后 `Start-Process KeySteam.exe`。

```
new extraction dirs: onefile_22184_274483_DfUcQ0xnti8
  main.dll md5 = 2948792df5b1484a426580927abb0882   <- 原始版，不是补丁版
redirect_dir_intact = True (afff50ee)               <- 准备的目录没被动过
```

⇒ **exe 忽略该环境变量**，仍自行解包到 `%TEMP%\onefile_<pid>_<n>_<rand>\`，
且解出的是内嵌原始版。该变量字符串虽在 `main.dll` 内存在，但它是 `main.dll`
自己读取的——那时解包早已完成，对引导阶段不起作用。

**附带实测事实**：exe 会 re-exec 自身，GUI 窗口不在 `Start-Process` 返回的 PID 上，
而在另一个 PID（onefile 引导进程 → 实际进程）。故监控脚本必须按进程名+路径枚举，
不能只跟一个 PID。这也解释了本实验「`main_window_samples = 0`」的原因是找不到窗口，
**不是**「没启动」。

⇒ **exe 侧只剩两条路**：① 改 exe 内部压缩流（需解压→打补丁→重压→修长度/CRC）；
② 用启动器替代双击。

### 6.2 给 `exe-payload` 队友的可执行建议

1. **优先验证 `NUITKA_ONEFILE_DIRECTORY` 重定向**：若能生效，则把补丁版 dll
   放在该目录即可让双击启动走补丁，无需改 exe 内部压缩流。本轮已备好
   `D:\ks_debug\instant\redirect\`（51 项，含补丁版 `main.dll`，md5 `afff50ee`）可供其直接测试。
2. **若必须改 exe**：定位方式不要按固定偏移，按**入口序言特征**搜。
   本轮实测 `push rbp,rbx,rsi,rdi,r12,r13,r15 | lea rbp,[rsp-0x27] | sub rsp,0xa0`
   这条 23 字节签名在全 dll 命中 **3 处**（fo `0x8ed580`、`0xf73fa0`、`0xf93500`），
   需用**函数体特征**（如该函数独有的 `_Py_NoneStruct` 引用密度）区分，而非签名唯一性。
   裸 8 字节序言 `4055535657415441` 全图出现 **182 次**，绝不可当定位依据。
3. 补丁后必须验 md5 并复跑 `inst_probe.ps1` 确认 `BYPASS_SUCCESS`。

---

## 7. 方法与红线遵守情况

- **只读**了 `main.dll.orig`。所有写入限于自己的作用域：
  `D:\ks_debug\instant\`（含 `baseline\`、`redirect\`）、
  `_re/ghidra/instant_bypass.md`、`_re/ghidra/tools/inst_*.py`。
- **未触碰**：`D:\ks_debug\main.dll`、`main.dll.orig`、`_probe\`、`harness\`，
  以及他人文件 `mainwin_*.json`、`startup_targets.json`、`dialog_anchors.json`、
  `dialog_shortcuts.md`、`tools/map_mainwin.py`、`tools/find_dialog.py`、
  `tools/ks_probe.ps1`、`tools/try_patch.py`、`tools/mkpatch.py`。
- **红线遵守**：全程未用「函数体里有业务字符串」判定身份（实测全镜像池内名字串
  RIP 引用 0 命中，与交接一致）；返回值语义**从代码读出**（`inst_ret.py`），未猜测。
- **实测优先**：补丁结论来自 `inst_probe.ps1` 的三次复现 + 一次基线对照，
  而非静态推断。

---

## 8. 交付物清单

| 文件 | 内容 |
|---|---|
| `_re/ghidra/instant_bypass.md` | 本文件 |
| `D:\ks_debug\instant\main.dll` | **补丁版 dll（md5 `afff50eeefac3a78d8bd82344e8e3cd4`），已实测生效** |
| `D:\ks_debug\instant\baseline\` | 基线对照环境（原始 dll，可直接复跑对照） |
| `D:\ks_debug\instant\redirect\` | 供 `exe-payload` 测试 `NUITKA_ONEFILE_DIRECTORY` 重定向（含补丁版 dll） |
| `D:\ks_debug\instant\funcmap.json` | **3139 个函数的运行期「名字→代码地址」全表** |
| `_re/ghidra/cache_key.json` | ❌ 未产出（密钥未捕获，见 §5） |
| `_re/ghidra/tools/inst_*.py`（11 个） | 本轮自建工具，见 §4 表 |

**未产出**：`cache_key.json`。原因与已排除空间见 §5.4，后续攻法见 §5.6。
