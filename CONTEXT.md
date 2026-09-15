# CONTEXT — 术语表

本仓库的领域词汇表。**只收术语，不收实现细节、不收方案、不收进度。**
实现证据放 `docs/`，决策放 `docs/adr/`，纠错放 `docs/agents/domain.md` 的 drift 表。

术语按「容易互相混淆的组」聚拢，而不是按字母序 —— 混淆是这张表要解决的实际问题。

---

## 验证体系

**验证码 / `verification_code`**
号商发放的每日凭据，用户手工输入。它**不是票据**，是票据的**上游**。提交后由服务端换发一张票据。
→ 不要与「票据」「AppTicket」混用。三者分属三个不同的发放方。

**票据 / ticket / KV1**
`key.steamofl.com` 签发的凭据，缓存于 `%APPDATA%\Shikieiki\verification.cache`。
结构为 `KV1` 魔数 + `purpose` + `code_hash` + `published_at` + `expires_at` + `signature`，
并以**每条票据一次性的 X25519 ECDH** 封装（`ephemeral_private` / `ephemeral_public` /
`server_public` / `shared_secret`）。
→ 关键性质：它是**签过名的密文块**，不是可编辑的配置。改一个字节即不可解。

**AppTicket / 加密 AppTicket**
由**本机 Steam 客户端**经 `steam_api64.dll` 的 `RequestEncryptedAppTicket` 取得。
发放方是 Valve，不是号商。
→ 这是 CLA `--encrypted-ticket` 参数所要求的入参，与「票据 / KV1」**完全无关**。
两者不可互换 —— 这是本项目最容易犯的错误。

**验签 / `verify_ticket`**
对票据签名的密码学校验。属 `src.security.ticket`。

**票据校验链 / verification chain**
`_start_initialization` → `_check_cached_verification` → （失败）`_fetch_verification_config`
→ `_handle_verification_config_ready` / `_failed` → `VerificationDialog`。
→ 与「完整性自检」是两条独立的链，不要混称。

**缓存命中 / cache hit**
`load_verification_ticket` + `verify_ticket` 均通过，启动流程直接进入 `_continue_initialization`，
**不联网、不弹窗**。
→ 这是本项目的目标状态。达成它**不需要破解任何密码学**，只需要一张有效票据。

---

## 完整性体系

**完整性自检 / `IntegrityService`**
样本对自身文件与运行环境的检查。**验签只是它的一个分支**，两者不等价。

**篡改警告 / `TamperWarningDialog` / 「倒卖可耻」**
完整性自检判定为篡改时出现的对话框，标题为「倒卖可耻」。
→ 与「验证码弹窗」是**不同的对话框、不同的触发条件、不同的处置**。混淆会导致整个任务被误读。

**验证码弹窗 / `VerificationDialog`**
票据校验链失败时出现的模态对话框。
→ 俗称的「验证弹窗」。它**不是**「倒卖可耻」。

**闸门 / `_verification_gate_allows`**
决定某次操作是否放行的判定点。闸门**会咨询**完整性状态，但闸门与完整性自检不是同一机制。

**本地 trailer**
`KeySteam.exe` 尾部 274 字节的 `KEYSTEAMTR1` 签名块。**只覆盖 exe，不覆盖 `main.dll`。**

**远程清单 / `version.json`**
`main.dll` 的完整性凭据。`main.dll` 走这条链，**不是**走本地 trailer。
→ 改 `main.dll` 会不会被发现，取决于这条链，不取决于 trailer。

**看门狗 / watchdog / `_spawn_watchdog`**
`RuntimeGuard` 启动的伴随子进程，负责心跳与终止。
→ `_frozen_runtime_supported` 是**实例属性不是方法**；`_spawn_watchdog` 的语义是**无条件启动**。

---

## 运行形态

**宿主 / host**
本项目自写的加载器，用于把 `main.dll` 装入进程并调用其导出 `run_code`。
→ 宿主是**我们的**工具，不是样本的一部分。

**payload**
`KeySteam.exe` 内嵌的 onefile 内容，以 **RCDATA 资源**嵌在 `.rdata`（头在文件偏移 `0x235b0`，
`KAY` + zstd 魔数）。**不在文件尾部。**
→ 不要与「本地 trailer」混淆：尾部那 274 字节是签名，不是 payload。

**DLL 模式 / `_NUITKA_ONEFILE_DLL_MODE`**
本样本的 onefile 形态：bootstrap 直接 `LoadLibraryExW(main.dll)` 后调用
`run_code(argc, argv, dll_filename)`，**argv 指针直传，无命令行重建**。
→ 与 exec 模式相对；exec 模式才重写 `argv[0]`。本样本不走 exec。

**非图形入口 / CLI 分支**
`src/gui/__init__.py` 的 `__main__` 分发：`--extract-authorization` /
`--watchdog` / 默认 `run_gui`。
→ 样本**自带**的能力，不是我们造出来的。它不实例化 `MainWindow`。

---

## 内核与授权

**内核 / kernel / `KernelSpec`**
`src.steam.kernel_service` 的 `dataclass`，字段含 `uses_ticket_authorization`、
`runtime_files`、`residual_files`、`steam_cfg_content`。三个实例：`KERNEL_OST`、`KERNEL_MMC`、`KERNEL_NONE`。
→ 自称「内核」但不是操作系统内核。`KERNEL_NONE.uses_ticket_authorization=false`
意为「不做运行时替换」，**不意为「免票产出授权」**。

**授权模式 / `authorization_mode`**
`normalize_authorization_mode` 归一化的取值：`AUTH_MODE_AUTO` / `GBE` / `SWITCH` /
`DETACHED` / `UBISOFT`。
→ 它是**切换哪个内核与流程**的开关，不是「绕过什么」的开关。

**授权产物 / authorization output**
`AuthorizationOutputBuilder.build_output_structure` 产出的目录与文件
（含 `.ks` / `.lua` / `configs.app.ini` 等）。
→ 与「票据」不同：产物是**入库结果**，票据是**准入凭据**。

**号商 / 商家**
发放验证码、提供离线账号的第三方。样本的弹窗文案直接指向它
（「请向商家发起退款」）。验证码是它的**商业守卫**，不只是技术校验。

---

## 使用规则

1. 本文件**只定义词**。任何「怎么做」都属于 `docs/` 或 `docs/adr/`。
2. 术语冲突时，以本文件为准；本文件错则改本文件，并在 `docs/agents/domain.md`
   的 drift 表登记一条纠错。
3. 新增术语前先查：已有术语是否只是换个说法。重复造词比缺词更糟。
