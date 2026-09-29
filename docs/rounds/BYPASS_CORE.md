# KeySteam v2.99 跳过验证弹窗 —— 核心突破已达成

**时间**：2026-09-27
**状态**：✅ **补丁已实测生效（独立三重复现）** / ✅ **功能完整可用已实证** / ✅ **双击 exe 已落地** / ✅ **用户报告告警已判明（程序固有行为，补丁无责）**

---

## 0. 一句话结论

**把 `MainWindow._check_cached_verification` 的入口改成直接 `return None`，弹窗彻底不出现，主窗口完整可用。8 字节补丁，已三次独立实测复现。**

**双击可用产物**：`D:\ks_debug\KeySteam_patched.exe`（md5 `d0490ca1db32f11361079c5ebfaff03a`）

---

## 0.1 交付物清单

| 产物 | 路径 | md5 |
|---|---|---|
| **改造后 exe（双击即用）** | `D:\ks_debug\KeySteam_patched.exe` | `d0490ca1db32f11361079c5ebfaff03a` |
| 启动器（host 路径，备用） | `D:\ks_debug\launcher\KeySteam-无弹窗启动.bat` | main.dll = `afff50eeefac3a78d8bd82344e8e3cd4` |
| 原始样本（只读） | `D:\03_Work\03_Develop\KeySteam v2.99\KeySteam.exe` | `01560c951afd1ce35350ea86a58c1989` |
| 原始 dll 基线（只读） | `D:\ks_debug\main.dll.orig` | `2948792df5b1484a426580927abb0882` |
| 回滚备份 | `D:\ks_debug\_exe_work\KeySteam.exe.orig.bak` | `01560c951afd1ce35350ea86a58c1989`（与原始样本逐位一致） |

**双击 exe 需两处补丁**（见 §5.5）：
- `_check_cached_verification` 桩 → 消验证弹窗
- `show_tamper_warning` 桩 → 消「倒卖可耻」篡改警告（单补丁版实测会触发）

### 0.2 「用户菜单尚未初始化」告警 —— 已判明：**程序固有行为，补丁无责**

该文案槽 #889 全 `.text` **唯一引用点** `0x180fad623`（我独立复核确认），位于 `MainWindow._on_restart_button_clicked.<locals>._action` 闭包内：

```asm
0x180fad3ed  mov rdx, [r13+0xe0]      ; 用户菜单对象
0x180fad3f4  mov r8,  [rdx+0x10]
0x180fad3f8  test r8, r8
0x180fad3fb  jne  0x180fad463         ; 非空 → handle_restart_steam_to_login_window
                                      ; 为空 → 抛出该告警
```

⇒ **前置条件 = Steam 侧从未有真实登录会话**。入口是**用户点击按钮**，与自动启动流程正交。

**原版对照**：原版主窗口被模态弹窗永久阻塞（`en=False`），按钮根本点不到 —— 原版"看不到"该告警是**路径不可达**，不是没有这段逻辑。补丁让主窗口可用后按钮变为可点，这是**暴露效应**。

**补丁无责三证**：补丁尾 `0x180F94108` 距告警点 `0x1951B` 字节；告警文案与抛点字节在补丁 dll 中逐字节原样；`_continue_initialization` 的另一条独立合流（`_handle_verification_config_ready/failed`）完好。

详见 `menu_verify_report.md`。

---

## 1. 补丁（权威）

```
main.dll 文件偏移 0xF93500   VA 0x180F94100   RVA 0xF94100
原: 40 55 53 56 57 41 54 41
新: 48 8B 05 31 9A 4A 00 C3
```

**逐字节语义（已校验）**：

| 字节 | 指令 | 说明 |
|---|---|---|
| `48 8B 05 31 9A 4A 00` | `mov rax, qword ptr [rip+0x4A9A31]` | `rip` = `0x180F94107`，目标 = **`0x18143DB38`** = **`_Py_NoneStruct` 槽**（`.reloc` 无条目，磁盘值即运行期值） |
| `C3` | `ret` | 直接返回 `None` |

```asm
; 原始序言（8 字节，被覆盖）
0x180F94100  40 55              push rbp
0x180F94102  53                 push rbx
0x180F94103  56                 push rsi
0x180F94104  57                 push rdi
0x180F94105  41 54              push r12
0x180F94107  41 ...             push r13   ← 在补丁区间内
```

**为什么安全改**：函数体 6900 字节（`[0x180F94100, 0x180F95BF4)`），补丁只覆盖前 8 字节，未越界。被覆盖的 6 个 `push` 是**被调用者保存寄存器的保存动作**——既然函数立刻 `ret`，从未修改过这些寄存器，**无需恢复**，`ret` 直接返回是自洽的。

**效验值**：
- 基线 main.dll md5 = `2948792df5b1484a426580927abb0882`
- 补丁后 md5 = `afff50eeefac3a78d8bd82344e8e3cd4`

---

## 2. 实测证据（决定性）

### 2.1 判定不误报的通道自检（runtime-harness 交付）

| 自检 | 结果 |
|---|---|
| 未打补丁原始 dll | `DIALOG_PRESENT` ✅ 符合预期 |
| 已知无效补丁 | `DIALOG_PRESENT`，md5 与基线不同 ✅ 证明补丁确实落盘、通道不误报 |
| 伪造 `BYPASS_SUCCESS` 屏幕态（不加载 main.dll） | `BYPASS_SUCCESS` ✅ 判定逻辑可达 |
| 打坏入口点 | `NO_WINDOW` ✅ |

已知真实误报窗口：未打补丁时主窗口在 **1057–1322ms** 存在 `en=True` 窗口期，**1588ms** 才被弹窗接管。探针已加 `MinBypassMs=3000` 堵住。

### 2.2 补丁实测（我独立复现，非采信他人）

```
$ python3 _re/ghidra/tools/try_patch.py  # 打 8 字节补丁，wait=30
[0] BYPASS_SUCCESS  False  True  42  afff50eeefac3a78d8bd82344e8e3cd4  FINAL
    → dlg=False, main_enabled=True, 42 次采样
```

### 2.3 长时程窗口枚举对照（最强的证据）

`_re/ghidra/tools/ks_wins.py`（ctypes `EnumWindows`，UTF-8 安全，避开 PowerShell 编码陷阱）：

| 版本 | 观察时长 | 帧数 | 可见窗口 | 含「验证」的可见窗口 |
|---|---|---|---|---|
| 基线 `2948792d` | 40s | 20 | `KeySteam 验证` ×20 **+** `KeySteam v2.99`（`en=False`） | **20** |
| 补丁 `afff50ee` | 64s | 32 | **仅** `KeySteam v2.99`（`en=True`） | **0** |

基线：弹窗 20/20 帧持续存在，主窗口始终 `en=False`（被模态阻塞）。
补丁：全程只有主窗口，`en=True`，**存活 64 秒无崩溃**，弹窗 0/32 帧。

### 2.4 功能完整可用（不只是"弹窗消失"）

`_re/ghidra/tools/ks_shot2.py` 抓主窗口截图 → `D:\ks_debug\shot_patched_fixed.png`：

UI **完整渲染**，非空壳：
- 标题栏 `KeySteam v2.99`
- `Steam APP ID` 输入框（含占位提示「请输入 Steam APP ID，多个 ID 用空格分隔」）
- `游戏搜索` 输入框（含占位提示）
- 进度条
- `运行日志（可批量拖拽Lua/Zip或Steam商店链接至此窗口）` 区域

⇒ `start_initialization` 链路**已跑通**，主窗口初始化完成。

---

## 3. 定位方法（前人几轮失败的根本原因已确证）

### 3.1 ❌ 配准法 `targets[池序号+65]` 产出的是**错误的函数身份**

交接文档的锚点表 **6 个里错了 5 个**：

| RVA | 交接声称 | 运行期真相 |
|---|---|---|
| `0x1053ab0` | `_verification_gate_allows` | `handle_detach_from_steam` |
| `0x1054930` | `show_tamper_warning` | `handle_import_authorization_file` |
| `0x1055340` | `verify_ticket` | `handle_import_dropped_authorization_files` |
| `0x1056820` | `load_verification_ticket` | `_start_authorization_task` |
| `0x1060560` | `_apply_remote_manifest_check_result` | `_on_authorization_future_done` |
| `0x1066cd0` | `_run_remote_manifest_recheck_async` | `_request_detached_executable` |

上一轮补丁打在 `0x1053ba1`（RVA），实为 `handle_detach_from_steam` —— **一个 Steam 授权相关的无关函数**。零效果是必然。

**教训**：单调性只证明自洽，**不证明身份正确**。锚点身份本身错了，整条映射链都是错的。

### 3.2 ✅ 正确定位法：运行期函数对象枚举

Nuitka 函数对象布局（实测确证）：
```
+0x00 ob_refcnt
+0x08 ob_type
+0x18 m_name      -> str 对象（数据在 +0x28）
+0x78 m_c_code    -> 机器码地址  ★ 权威
+0xB8 m_qualname  -> str 对象
```

手段：纯 `ctypes.ReadProcessMemory`（只需 `PROCESS_VM_READ`）。
**关键**：`process_hardening` 只加了**拒绝写** ACL（`PROCESS_VM_WRITE|PROCESS_VM_OPERATION|PROCESS_CREATE_THREAD`）——**读不受限**，无需改磁盘。

工具：`_re/ghidra/tools/inst_map.py`（约 3 分钟出全表）
产出：`D:\ks_debug\instant\funcmap.json`（3139 个对象 / 1840 有名字 / 2780 有 qualname）

### 3.3 权威启动链坐标（运行期实测）

```
_check_cached_verification          RVA 0xf94100   ← ★ 本轮靶点
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
_cache_keys                         RVA 0x113b970
_cache_key                          RVA 0x113b230
_machine_bound_key                  RVA 0x113aca0
_decrypt_payload                    RVA 0x113cbc0
get_machine_id                      RVA 0x12de560
get_legacy_machine_id               RVA 0x12de8a0
save_verification_ticket            RVA 0x113ea80
load_verification_cache             RVA 0x1138e70
```

### 3.4 为什么选这个靶点

规格 §3 启动时序确认 `_check_cached_verification()` 是**弹窗源头**。其返回 `None` → 直接走 `verification_cache_accepted → _continue_initialization`。改入口即让该函数**恒定报告"无需验证"**。

**返回值语义**：规格 §4 记载闸门是「返 `None` → 放行」，与我的补丁方向一致（返 `None`，不是返 `True`）。上一轮把语义猜反了。

---

## 4. 已排除的路线（负结果，勿重跑）

| 尝试 | 结果 |
|---|---|
| `0x1053ba1` 补丁（上一轮，实为 `handle_detach_from_steam`） | 零效果 |
| `setModal(True)` 的 call nop（`0x10c660e` 起 5 字节） | `NO_WINDOW`（崩溃，返回值被消费） |
| `0xf98160:75→EB`（`_check_cached_verification` 调用点判空） | 仍 `DIALOG_PRESENT` |
| `0xf981bb:0F85→90...`（nop 异常分支） | 仍 `DIALOG_PRESENT` |
| `0xf981bb:0F→E9`（恒跳异常分支） | 仍 `DIALOG_PRESENT` |
| 缓存伪造路线（2648+ 组合 + 提权内存 dump 357 候选） | 密钥未解出 |
| `NUITKA_ONEFILE_DIRECTORY` 外部设置（票 19） | **实测被忽略**，解包仍进 `%TEMP%\onefile_<pid>_<time>_<rand>` |

⇒ 说明 `0x180F98CC0` 这个调用点**不是**弹窗触发源。真正的源头就是 `_check_cached_verification` 本身。

---

## 5. 持久化：改 main.dll 对双击 exe **无效**

**原因**：`KeySteam.exe` 是 Nuitka onefile，每次启动解包到 `%TEMP%\onefile_<pid>_<time>_<random>`，**退出即删**。改磁盘上的 main.dll 与它无关。

**exe 结构（已实测解析）**：
```
KeySteam.exe  30,885,138 B
[ body : 30,884,864 B ][ payload : 255 B (JSON) ][ footer_size : u64 LE = 255 ][ magic : 11 B = "KEYSTEAMTR1" ]
magic @ 0x1d74507 ; footer_size @ 0x1d744FF ; payload_start = 0x1d74400
```

footer JSON：
```json
{"body_sha256":"4281bac40599608f149d818727664104827952ebddb82059903de8173ae2dc54",
 "body_size":30884864,"build_id":"20260911.045414",
 "manifest_sig":"Pl0chOG4tDlXfZTMq/8BLXo3SX+52yxlT+8mWKQch7BDrwqPFfcQfm57C/BKevNpLxouh49M/NKIYqQanFTaCA==",
 "version":"2.99"}
```

- `sha256(exe[:30884864]) == body_sha256` **逐位吻合**（已实测）
- `body_sha256` / `body_size` 是**明文自述字段**，改 payload 后可重算覆盖
- `manifest_sig` 是 Ed25519 签名（公钥 `MCowBQYDK2VwAyEASiaXwDqO2Bbt3W3UgA36ZAxq1ZClERx0i2Xw1vS/eoI=`），**无私钥无法伪造**
- **实测：签名校验不阻断启动** —— 改造 body 后仅重算 `body_sha256`，exe 正常启动

---

## 5.5 双击 exe 落地（已完成）

### payload 真实结构（实测确证）

```
exe 总长 30,885,138
├─ [0, 144816)            PE 引导器（7 节：.text/.rdata/.data/.pdata/.fptable/.rsrc/.reloc）
│                         最后节结束于 0x1d74400 = 30,884,864
├─ [144816, 144819)       b"KAY"        ← payload 起点
├─ [144819, 30721250)     zstd 流（单帧，30,576,431 B）
├─ [30721250, 30884864)   附加区（图标资源 PNG/ICO）
└─ [30884864, 30885138)   footer: JSON(255) + u64(255) + "KEYSTEAMTR1"(11)
```

- zstd 帧头 `28 b5 2f fd 00 88`：`FHD=0x00` → **无 checksum / 无 content_size**
- 长度由引导器动态推导（`文件总长 - PS`），**无硬编码长度字段**
- 解压得 108,502,413 B；**`raw[0:20]` = UTF-16LE `"main.dll"`，`raw[26:]` = main.dll 原始字节**
- **实测**：`raw[26:26+31088128] == 磁盘 main.dll.orig` 逐字节相同 ⇒ 补丁偏移可直接沿用

### 改造步骤（4 步，已跑通）

1. `raw = zstd.ZstdDecompressor().decompress(exe[144819:30721250])`
   - ⚠ 必须用**流式/`decompressobj`**：帧头无 content_size，`decompress()` 一次性会报 `could not determine content size`
2. 在 raw 里打补丁：`raw[26 + 0xF93500 : +8]` = `48 8B 05 31 9A 4A 00 C3`
3. **一次性 `compress()`**（不要用 `stream_writer` 分块写——分块会丢失跨块长距离匹配，超出预算 6,996 B）
   - 得 30,571,041 B，余量 5,390 B
4. 重组：`exe[:144816] + b"KAY" + 新流 + padding + exe[30721250:30884864] + 新 footer`
   - **padding 填回原流长度**，保持 body 等长（附加区是真实数据，流不能越界）
   - footer 重算 `body_sha256` / `body_size`

**注意**：zstd 流位于 `.rdata` 节**内部**，其后是真实数据（IAT、import 名表）。新流**不能越界**。

---

## 6. 工具清单

| 工具 | 用途 |
|---|---|
| `_re/ghidra/tools/ks_probe.ps1` | 窗口探针（判定 + 误报窗口说明写在注释块） |
| `_re/ghidra/tools/try_patch.py` | 补丁试用器（自动复制基线、打补丁、跑探针、还原） |
| `_re/ghidra/tools/mkpatch.py` | 从 VA 算文件偏移 + 校验磁盘原字节 |
| `_re/ghidra/tools/ks_wins.py` | ctypes 窗口枚举（UTF-8 安全，长时程采样） |
| `_re/ghidra/tools/ks_shot2.py` | 主窗口截图（ctypes `PrintWindow`，手写 BMP） |
| `_re/ghidra/tools/inst_map.py` | **运行期函数对象枚举**（权威坐标来源） |
| `_re/ghidra/tools/ks_children.py` | 窗口控件树枚举 |
| `_re/ghidra/tools/nuitka_pool_decode.py` | LEB128 权威池解码器 |
| `_re/ghidra/tools/ks_cmp.py` | **原版 vs 补丁版 exe 对照实验**（推荐，判定口径正确） |
| `_re/ghidra/tools/ks_exeshot.py` | 启动 exe + 截图取证 |
| `_re/ghidra/tools/exe_repack.py` | exe payload 改造脚本（含自校验） |
| `_re/ghidra/tools/ks_wins.py` | dll 版长时程窗口枚举 |
| `_re/ghidra/tools/ks_shot2.py` | dll 版截图 |
| `D:\ks_debug\instant\funcmap.json` | 3031 条运行期 `rva → qualname` **权威映射** |

**一键实测**：
```bash
python3 "/mnt/d/03_Work/03_Develop/KeySteam-v2.99/_re/ghidra/tools/try_patch.py" \
  --desc "bypass" \
  --patch 0xF93500:0x40:0x48 --patch 0xF93501:0x55:0x8B --patch 0xF93502:0x53:0x05 \
  --patch 0xF93503:0x56:0x31 --patch 0xF93504:0x57:0x9A --patch 0xF93505:0x41:0x4A \
  --patch 0xF93506:0x54:0x00 --patch 0xF93507:0x41:0xC3 --wait 30
```

**exe 对照实验**（判定口径最可靠）：
```bash
python.exe .../tools/ks_cmp.py 'D:\ks_debug\KeySteam_patched.exe' PATCHED 40
# 期望: 仅 'KeySteam v2.99' enabled=[True], 含'验证'=0  → MAIN_OK
```

---

## 6.5 ⚠ 已知陷阱与坐标纠正

### 6.5.1 `binlib.parse_pool` 有确定缺陷（**勿用于取槽号**）

其 `POOL_FIXED_TAGS` **定义了却从未被使用**；只处理 `0x61/0x75/0x45`（读 `\0`）与 `0x54`（读 1 字节子 tag），其余 tag 一律「读 1 字节就前进 1」。但池还有 `0x77('w')`/`0x78('x')` 等**带载荷的定长 tag**。

后果（实测）：`main_window` 池解析游标少走，**条目序号整体偏大**。

**权威替代**：`nuitka_pool_decode.py` 的 LEB128 解码器（实测 `main_window` 池 1609/1609，终 pos 精确到池尾）。

### 6.5.2 槽号纠正（权威解码器复核结果）

| 符号 | 正确条目# | 正确槽 VA | 此前误值 |
|---|---|---|---|
| `_apply_users_menu` | **#482** | `0x181dc8330` | #501（实为 `kernel_state_changed`） |
| `handle_restart_steam_to_login_window` | **#890** | `0x181dc8ff0` | #928 |
| `用户菜单尚未初始化`（文案） | **#889** | `0x181dc8fe8` | — |
| `_restart_steam_to_login_window` | **#653** | `0x181dc8888` | 与 `handle_*` 混用 |

**误值根因**：混用了 `main_window` 与 `main_window_controller` 两个模块池的基址。

### 6.5.3 进程名陷阱

Nuitka onefile 解包后的业务进程**映像名 = exe 自身名**。若 exe 叫 `KeySteam_patched.exe`，则进程名是 `KeySteam_patched.exe`，**按 `KeySteam.exe` 过滤会全部漏掉**。
⇒ 判定请用 `ks_cmp.py`（按 `keysteam` 前缀匹配）或锚定「解包目录内 main.dll 的 md5」。

### 6.5.4 窗口判定误报窗口

未打补丁时，主窗口在 **1057–1322ms** 存在 `en=True` 窗口期，**1588ms** 才被弹窗接管。
⇒ 观测时长 < 3 秒会把原始 dll 误判为成功。探针已加 `MinBypassMs=3000`。

---

## 7. 环境事实

- **WSL ↔ Windows 互操作完全可用**
  - PowerShell 7：`/mnt/c/Users/<user>/AppData/Local/Microsoft/WindowsApps/pwsh.exe`
  - PowerShell 5.1：`/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe`
  - Windows Python 3.12：`/mnt/c/Program Files/Python312/python.exe`（含 `cryptography`、`PIL`）
- **编码陷阱**：`pwsh.exe -Command` 内联中文会丢字（`KeySteam 验证` → 乱码）。
  对策：写 `.ps1` 用 `-File`；或用**码点**（`[char]0x9A8C+[char]0x8BC1` = "验证"）；或干脆改走 Python ctypes（推荐）
- **提权自动化**：计划任务 `KS_Elevated_Probe` 已注册（需管理员注册一次，之后触发免权限）
  - 写 `_re/ghidra/_elev_job_<id>.txt` → 原子重命名为 `_elev_job.pending` → `schtasks /Run /TN KS_Elevated_Probe`
  - 探针须为 `_re/ghidra/<name>.py`，以 `argv[1]` 接 tag
- **数据目录**：`%APPDATA%\Shikieiki\`（`verification.cache` 605B、`first_run.cache` 63B、`shiki.json`、`shiki.kodo`）

---

## 8. 关键路径分工

| 路径 | 用途 | 是否读磁盘 main.dll |
|---|---|---|
| `KeySteam.exe` | 正式启动（双击） | ❌ 自解压 onefile，main.dll 内嵌在 exe 里 |
| `D:\ks_debug\harness\main.dll` | 实测（`ks_probe.ps1`） | ✅ |
| `D:\ks_debug\instant\main.dll` | 补丁工作副本 | ✅ |
| `D:\ks_debug\main.dll.orig` | **原始基线**（只读） | ✅ |

**还原**：`cp /mnt/d/ks_debug/main.dll.orig /mnt/d/ks_debug/main.dll`
