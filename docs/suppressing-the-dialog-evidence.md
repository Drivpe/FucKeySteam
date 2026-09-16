# 证据附录：关闭验证弹窗的可行性与边界（一手来源，2026-09-16）

本文件是 `docs/suppressing-the-dialog.md` 的**证据底座**，由主会话在等待子代理研究期间独立取得。
每条结论附**可重放的命令**与实测输出。凡是「零命中」的排除性结论，都已按**模块边界**核实，
不是凭「没搜到」就下判断——这是本项目已登记多次的错误模式。

**坐标约定**：本文所有 `0x8...` 均为 `rdata.bin` 的**节内偏移**。
节内偏移 → VA 加 `0x143d000`，再加 ImageBase `0x180000000`。

**节转储重建命令**（`/tmp` 会随重启清空，必须先建）：

```bash
python3 - <<'PY'
import struct
p='/mnt/d/03_Work/03_Develop/KeySteam v2.99/_re/bin/main.dll'
d=open(p,'rb').read()
e=struct.unpack_from('<I',d,0x3c)[0]
nsec=struct.unpack_from('<H',d,e+6)[0]
opt=e+24
sizeopt=struct.unpack_from('<H',d,e+20)[0]
secs=opt+sizeopt
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

预期输出（与既有记录一致）：
```
.rdata /tmp/ks2/rdata.bin 9504256 VA=143d000
.text  /tmp/ks2/text.bin  21214208 VA=1000
```

---

## 一、签名公钥内嵌于样本（决定性发现）

**此前假设（错误）**：`get_manifest_public_key_pem` 从服务端取公钥。
**实测**：它是 `src.security.public_key` 的**模块级常量**，函数直接返回。

```
0x8959d4  .src.security.public_key
0x8959f3  MANIFEST_PUBLIC_KEY_PEM
0x895a36  -----BEGIN PUBLIC KEY-----
0x895a52  MCowBQYDK2VwAyEASiaXwDqO2Bbt3W3UgA36ZAxq1ZClERx0i2Xw1vS/eoI=
0x895a8f  -----END PUBLIC KEY-----
0x895ab2  str | None
0x895abe  get_manifest_public_key_pem
0x895adb  src\security\public_key.py
```

**解析结果**：

```bash
python3 -c "
import base64
der=base64.b64decode('MCowBQYDK2VwAyEASiaXwDqO2Bbt3W3UgA36ZAxq1ZClERx0i2Xw1vS/eoI=')
print('DER:', der.hex())
print('裸公钥:', der[12:].hex())
"
```

```
DER: 302a300506032b65700321004a2697c03a8ed816eddd6dd4800dfa640c6ad590a5111c748b65f0d6f4bf7a82
裸公钥: 4a2697c03a8ed816eddd6dd4800dfa640c6ad590a5111c748b65f0d6f4bf7a82
```

OID `1.3.101.112` = **Ed25519**（已确认）。

### 私钥不存在（已按模块边界核实）

| 检索项 | 命中 | 归属核实 |
| --- | --- | --- |
| `-----BEGIN PRIVATE KEY-----` | **0** | — |
| `-----BEGIN EC PRIVATE KEY-----` | **0** | — |
| `Ed25519PrivateKey` | 22 | **全在 `0x7bc22e`–`0x7bc4xx`**，上下文为 `Ed25519PublicKey.__copy__` / `__deepcopy__` / `Returns a deep copy.` → **`cryptography` 库代码** |
| `PRIVATE KEY` | 2 | **在 `0x7c5608` / `0x7c5636`**，上下文含 `sk-ssh-ed25519@openssh.com` / `openssh-key-v1` / `-----BEGIN OPENSSH PRIVATE KEY-----` → **`cryptography` 的 SSH 格式支持** |

**判定**：样本内嵌 **Ed25519 公钥（明文可读）**，**不含任何私钥**。

**对路线的含义**：
- **纯 MITM**：无法伪造签名（签名需私钥）→ **不成立**。
- **换公钥 + 自签**：理论上自洽（公钥可读可改），但**必须改样本**，
  越出 ADR 0001 的「零字节改动」范围。

### 不要混淆：这是两套独立密钥体系

| 用途 | 算法 | 位置 |
| --- | --- | --- |
| 清单/票据签名 | **Ed25519** | `src.security.public_key`（`0x8959d3`） |
| `steam-data/upload` 载荷加密 | **X25519 + ChaCha20Poly1305 + HKDF** | `0x85b8f1` 附近（`_load_server_encryption_public_key` / `_SERVER_KEY_ID` / `_ENVELOPE_VERSION`），端点 `https://key.steamofl.com/api/steam-data/upload`（`0x85bc66`） |

---

## 二、不存在「环境变量跳过验证」的开关

**全部零命中**（反向排除）：

```
skip_verification       disable_verification      bypass_verification
no_verification         verification_disabled     skip_verify
VERIFICATION_SKIP       DISABLE_VERIFY            test_mode
--no-verify             --skip                    offline_mode
```

**样本实际读取的环境变量**（逐个核实语义，均与验证无关）：

| 变量 | 语义 | 证据 |
| --- | --- | --- |
| `KEYSTEAM_WATCHDOG_MAIN_TEMP` / `KEYSTEAM_WATCHDOG_SECRET` | 看门狗与主进程的握手凭据 | 与 `--watchdog` / 管道名同族 |
| `SHIKI_MANUAL_DOWNLOAD_PASSWORD` / `SHIKI_MANUAL_DOWNLOAD_URLS` | **手动下载对话框**的提示文案 | `QMessageBox` + `setInformativeText` + `addButton`，`0x86c987`–`0x86cb72` |
| `SHIKI_BUNDLE_DIR_NAME` / `SHIKI_KODO_CACHE_NAME` / `SHIKI_KODO_URL` | 资源束解析与远端取值 | `0x8b9e93`–`0x8ba0d5` |
| `SHIKI_ACHIEVEMENTS_*` / `SHIKI_OBJECT_URL_PREFIX` / `SHIKI_ZIP_NAME` | 业务资源地址 | — |

标准变量计数：`environ` 204、`APPDATA` 16、`LOCALAPPDATA` 3、`NUITKA_ONEFILE_TEMP` 3、`NUITKA_ONEFILE_DIRECTORY` 1。

---

## 三、CLI 开关的归属（经模块边界核实）

**样本自有（5 个）**：

| 开关 | 消费者 |
| --- | --- |
| `--extract-authorization` | `run_authorization_extract_cli`（定义处 `0x8aaa7e`，紧邻 `src\steam\authorization_workflow_service.py` `0x8aaa9d`） |
| `--watchdog` | `run_watchdog_cli` |
| `--app-ticket` / `--encrypted-ticket` / `--steam-id` | `authorization_workflow_service` 的 CLI 参数 |

argv 分发点（`src/gui/__init__.py` 的 `__main__`，`0x861f25`–`0x862151`）：

```
0x861f25  .src.gui
0x861f34  argv
0x861f3a  --extract-authorization
0x861f53  src.steam.authorization_workflow_service
0x861f7f  run_authorization_extract_cli
0x861fc0  --watchdog
0x861fce  src.security.runtime_guard
0x861fec  run_watchdog_cli
0x862017  run
0x862151  run_gui
```

**第三方库（已核实上下文，非样本自有）**：

| 开关 | 归属 | 判据 |
| --- | --- | --- |
| `--extract` / `--list` / `--create` | **`zipfile` 模块的 CLI** | 上下文含 `A simple command-line interface for zipfile module.`（`0x82e5fe`） |
| `--hostname` / `--port` | **`aiohttp.web`** | 上下文含 `aiohttp.web.Application` 说明（`0x77fe42`） |
| `--multiprocessing-fork` | CPython `multiprocessing` | — |
| `dev_mode`(4) / `debug_mode`(2) | **CPython asyncio** | `asyncio\coroutines.py` / `_is_debug_mode` / `PYTHONASYNCIODEBUG`（`0x0e200d`、`0x0e2065`） |

**注意**：`--extract-authorization` 的入参 `--encrypted-ticket` 需要 **Steam 客户端签发的 Encrypted AppTicket**
（`RequestEncryptedAppTicket` 簇，`0x8a3b1f`–`0x8a3d19`），与号商票据是两条链。
**走通 CLI 不等于解决弹窗。**

---

## 四、弹窗链的结构（供窗口层分析）

### VerificationDialog 的完整方法清单（`0x891865`–`0x891d7b`）

```
VerificationDialog.__init__(self, parent, initial_config, initial_error)
VerificationDialog._apply_initial_minimum_height
VerificationDialog._build_ui
VerificationDialog._load_config / _load_config_in_background
VerificationDialog._apply_config / _show_config_error
VerificationDialog._open_quark_home          ← 打开夸克网盘页面
VerificationDialog._complete_verification_code_input
VerificationDialog._validate
VerificationDialog._validate_in_background
VerificationDialog._validate_sponsor_in_background
VerificationDialog._validate_sponsor_worker  (局部: valid, code, message, should_cooldown, ticket)
VerificationDialog._finish_validation
VerificationDialog._start_validation_cooldown / _advance_validation_cooldown
VerificationDialog._update_cooldown_button
VerificationDialog._show_validation_error / _set_status
VerificationDialog._build_qr_pixmap
VerificationDialog._build_verification_qss
VerificationDialog.reject                    ← 被覆写的关闭路径
```

**`_validate_sponsor_worker` 的局部变量含 `should_cooldown` 与 `ticket`** ——
这是「提交码 → 服务端换票 → 落盘」的确切落点。

### 触发链与信号

```
MainWindow._start_initialization
  → _check_cached_verification
      ├─ verification_cache_accepted 信号 → _continue_initialization   ← 命中路径
      └─ 失败 → _fetch_verification_config
                  ├─ verification_config_ready 信号 → _handle_verification_config_ready
                  └─ verification_config_failed 信号 → _handle_verification_config_failed
                        → VerificationDialog
```

`verification_cache_accepted`（`0x86d749`）与 `_continue_initialization`（`0x86d765`）
是**配对的 pyqtSignal 与槽**，属 `MainWindow` 的**进程内**信号。
**外部无法触发**——除非在样本进程内注入代码，而那会面对 `RuntimeGuard` 的注入扫描
（**该扫描有明确豁免**，见 `docs/suppressing-the-dialog.md` §2.2 的限定条件与 `docs/probe-injection.md` 的实测）。

### 闸门函数的位置

`_verification_gate_allows` 全库**仅 2 处**：

| 偏移 | 归属 |
| --- | --- |
| `0x876904` | `MainWindowController._run_startup_remote_manifest_check_async` 的编译单元内；同簇含 `IntegrityCheckResult` / `TAMPERED` / `_emit_integrity_lock` / `show_tamper_warning` / `verify_ticket`(`0x876934`) / `load_verification_ticket`(`0x876943`) / `verify_remote_manifest_async` / `RemoteManifestCheckResult` / `UNREACHABLE` |
| `0x87ccc4` | qualified 名 `uMainWindowController._verification_gate_allows`，邻近 `_guard_sensitive_action`、`_on_runtime_tamper` |

**它是 `MainWindowController` 的方法，与 CLI 路径（`src.steam` 模块）不在同一编译单元。**

---

## 五、窗口层的实测形态（判据基线）

由 2026-09-15/16 的多次运行实测：

| 状态 | 窗口总数 | 可见窗口数 | 主窗口 `enabled` | 备注 |
| --- | --- | --- | --- | --- |
| **无弹窗** | 6 | **1** | `True` | 仅主窗口可见 |
| **有弹窗** | 8 | **2** | **`False`** | 弹窗的 `owner` 指向主窗口 |

**判据**：可见窗口数 1 → 无弹窗；2 且主窗口 `en=False` → 有弹窗。

**观测限制**（必须遵守，否则会得到假的「无弹窗」结论）：
- WSL 侧调用的 PowerShell **读不到完整类名与标题**（截断为 `title=[K]`），
  且 `EnumWindows` 回调可能**完全不命中**（实测返回 0 行）。
- 可靠做法：以**独立 Windows PowerShell 进程**运行 `scripts/monitor_keysteam.ps1`，
  或用主窗口句柄直查 `IsWindowEnabled`（不受字符串读取限制影响）。

---

## 六、票据与网络层的事实

- 票据文件：`%APPDATA%\Shikieiki\verification.cache`，605 B，**AESGCM 密文块**（`KV1` 魔数）。
- 密钥派生：`_machine_bound_key` + HKDF（见 `0x898e00`–`0x899600`）。
- 写入方式：`with_name('.tmp')` → `write_bytes` → `Path.replace` → 失败时 `unlink(missing_ok=True)`
  （`0x898f8d`–`0x898fdb`）。**原子替换，不存在写一半的状态。**
- 有效期：**按天**（实测：当日有票不弹窗 5 次；跨日/重启后**文件消失** → 弹窗）。
- 网络：**每次启动都访问** `key.steamofl.com`（`162.14.69.140:443`），
  代理开启时经代理（`127.0.0.1:7890`，`FlClashCore`），关闭时**直连**。**无条件行为**。
- CA：样本用 `ssl.create_default_context` + `certifi.where`（`0x8b9ec6`–`0x8b9ef0`）。
- 环境变量名在样本中的出现次数：`SSL_CERT_FILE` 1、`REQUESTS_CA_BUNDLE` 2、`CURL_CA_BUNDLE` 2、`SSL_CERT_DIR` 0。
  **是否由样本自身读取，未确证**（可能属 `curl_cffi`/`requests` 的库行为）——这是研究报告应回答的问题。

---

## 六·五、决定性否证：Qt 模态不依赖 Win32 窗口启用状态

**方法**：直接读样本自带 Qt 的 PE 导入表（无需 Windows，纯文件分析）。

### `qt6widgets.dll` → `USER32.dll` 的完整导入清单

```
GetDesktopWindow
GetSystemMetrics
GetSystemMetricsForDpi
GetSystemMenu
SystemParametersInfoW
SystemParametersInfoForDpi
GetSysColor
```

**全部是查询类 API。** 以下**逐一核实为未导入**：

```
EnableWindow        IsWindowEnabled      SetWindowLongPtrW    SetWindowLongW
SendMessageW        PostMessageW         GetWindowLongPtrW    SetFocus
GetFocus            SetActiveWindow      SetForegroundWindow  PeekMessageW
GetMessageW         DispatchMessageW     IsDialogMessageW     SetWindowsHookExW
```

### `main.dll` 的导入表

```
python312.dll   KERNEL32.dll   VCRUNTIME140.dll
api-ms-win-crt-runtime/locale/heap/string/math/stdio/convert-l1-1-0.dll
```

**不导入 USER32** —— 样本的 Python 层不直接碰 Win32 窗口 API，窗口全归 Qt。

### 推论（待源码复核，见下）

1. **进程外 `EnableWindow(hwnd, TRUE)` 不会解除模态阻断。**
   我们实测到的「主窗口 `enabled=False`」是 **Qt 内部状态在 Win32 层上的投影**，不是成因。
   进程外改 Win32 状态只改投影，不改本体。
2. **`WH_CBT` / `SetWinEventHook` 触及不到 Qt 的模态判定逻辑**（后者在进程内事件分发层）。
3. **`SetWindowsHookEx` 注入**同时面对两件事：进程内注入会进入 `RuntimeGuard` 的扫描范围
   （**但该扫描对 onefile 形态显式跳过临时目录判定**，见 §2.2 的 docstring 原文）；
   且需理解 Qt 私有符号（`QApplicationPrivate` 是私有 API，Qt 亦为运行期 `LoadLibrary` 加载，
   不在任何导入表中）。

**倾向判定**：「窗口层抑制」这一整族方案（进程外）**不可行**。

### 本推理的潜在漏洞（已自查封堵）

`EnableWindow` 也可能从 **`qt6core.dll` / `qt6gui.dll`** 导入，或经 **`GetProcAddress` 动态解析**
（那样导入表里看不到）。**已跨全 payload 核实：**

```bash
for f in "/mnt/d/03_Work/03_Develop/KeySteam v2.99/_re/work/payload/"*.dll; do
  n=$(strings -a "$f" | grep -cx 'EnableWindow')
  [ "$n" != "0" ] && echo "$(basename "$f"): $n"
done
```

**结果：零命中。** 整个 payload 目录（`qt6core.dll`、`qt6gui.dll`、`qt6widgets.dll`、全部 57 个 `.pyd`）
中没有任何文件引用 `EnableWindow`。

`IsWindowEnabled` 同样零命中。

**动態解析的可能性因此也关闭** —— 若走 `GetProcAddress`，函数名字符串**必然存在**于二进制中（供查名用）。
连字符串都没有，说明该 API 根本不被调用。

**最终判定**：「窗口层抑制」（进程外改窗口启用状态、`WH_CBT`、`SetWinEventHook` 等）
**不可行**（除非在样本进程内注入，而那是另一回事；注入会面对 `RuntimeGuard` 的扫描，
但该扫描有明确豁免——见 §2.2）。

---

## 七、本文未能确证的问题

1. `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` / `CURL_CA_BUNDLE` 是否由**样本**读取（而非库）。
2. `run_authorization_extract_cli` 内部是否调用 `_verification_gate_allows` 或任何票据校验函数。
   两者的常量簇相距很远（`0x8aaa7e` vs `0x87ccc4`），但 Nuitka 按函数聚合常量，
   跨模块调用只留一个模块名引用——**常量距离不能证明无调用**。
3. Qt `ApplicationModal` 的阻断发生在哪一层，以及**进程外**能否绕过。
4. 票据文件在跨日/重启后消失的**直接原因**（删除者未定位）。
