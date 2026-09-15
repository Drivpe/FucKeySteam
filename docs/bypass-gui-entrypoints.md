# 绕过 GUI 的非图形入口：静态确证报告

**日期**：2026-09-15（第 5 轮）
**证据源**：`/tmp/ks/rdata.bin`（`main.dll` 的 `.rdata` 整节，9,504,256 B）
**坐标**：本文所有 `0x8...` 均为 **rdata.bin 节内偏移**，非 VA、非文件偏移。重导命令见每节末尾。

---

## 结论摘要

交接文档假设「要绕过 GUI 必须自己造宿主、注入或手工调 `PyImport`」。**这个假设不成立。**
样本自身在 `src/gui/__init__.py` 里就实现了 **argv 分发**，其中一条分支专门用于「无 GUI 提取授权」。

```
src/gui/__init__.py 的 __main__ 分发
  --extract-authorization  → src.steam.authorization_workflow_service.run_authorization_extract_cli
  --watchdog               → src.security.runtime_guard.run_watchdog_cli
  （默认）                  → run_gui
```

`run_authorization_extract_cli` 不实例化 `MainWindow`，因此不进入 `_start_initialization` →
`_check_cached_verification` → `_fetch_verification_config` → `VerificationDialog` 这条链。
弹窗链的**入口本身**被规避，而不是被绕过。

---

## 1. 分发点的逐 token 证据

转储 `0x861e60`–`0x8621e0` 得到如下序列（相邻 token 即同一编译单元内的常量池顺序）：

| 偏移 | token |
| --- | --- |
| `0x861f25` | `src.gui` |
| `0x861f34` | `argv` |
| `0x861f3a` | `--extract-authorization` |
| `0x861f53` | `src.steam.authorization_workflow_service` |
| `0x861f7f` | `run_authorization_extract_cli` |
| `0x861fc0` | `--watchdog` |
| `0x861fce` | `src.security.runtime_guard` |
| `0x861fec` | `run_watchdog_cli` |
| `0x862010` | `app` |
| `0x862017` | `run` |
| `0x8620da` | `list[str] \| None` |
| `0x8620ec` | `int` |
| `0x8620f1` | `src\gui\__init__.py` |
| `0x862106` | `<module src.gui>` |
| `0x86211a` | `argv` |
| `0x862120` | `run_authorization_extract_cli` |
| `0x86213f` | `run_watchdog_cli` |
| `0x862151` | `run_gui` |

关键点：`<module src.gui>` 与 `src\gui\__init__.py` 同时出现，且 `0x8620da`/`0x8620ec` 的
`list[str] | None` → `int` 是**函数返回注解对**（`main(argv: list[str] | None) -> int`）。
这是模块级 `__main__` 守卫的标准 Nuitka 编码形态。

重导：

```bash
cd /tmp/ks && python3 dump.py 0x861e60 0x862200
```

## 2. `AuthorizationWorkflowService` 的接缝（交接问题一与问题三）

qualified 名清单共 **92 条**（`grep -ao 'uAuthorizationWorkflowService\.[A-Za-z_]*'`），
其中**仅 6 条为公开名**，其余全部 `_` 前缀：

```
__init__  run  export_authorization_file  import_authorization_file
import_authorization_file_for_embedded_app  resolve_game_install_dir
clear_ticket_authorization_registry  find_ubisoft_token_ini_files
get_ubisoft_last_login_account  is_unreal_engine_install_dir
remove_ubisoft_token_ini_files  write_app_ticket_registry
```

**构造签名**（`0x860ff1`）：

```
['self', 'parent', 'default_mode', 'app_id', 'normalized_mode', '__class__']
```

`parent` 是 `QDialog` 的 parent 约定，`default_mode` 的默认值即 `AUTH_MODE_AUTO`
（`0x860d10` 给出 `AUTH_MODE_AUTO` / `AUTH_MODE_GBE` / `AUTH_MODE_SWITCH` 三个常量）。
**注意**：`parent` 可传 `None` —— 但此处 `parent` 属于**对话框类**，不是 `AuthorizationWorkflowService`。
`0x860c7b` 的 Qt 导入清单（`QButtonGroup`/`QDialog`/`QRadioButton`…）与 `0x860d68` 的
`apply_style`/`build_theme_qss` 表明这一编译单元是 **GUI 对话框**，不是服务本体。

**服务本体的入口在 `0x861f7d` 之后、`0x86d910` 之前**，且 CLI 分支
（`run_authorization_extract_cli`）自身**不导入 Qt**。这是「GUI 依赖可剥离」的直接证据：
样本作者已经剥过一次，剥离结果就是这条 CLI 路径。

CLI 参数集（`0x8a546b`–`0x8a549d`）：

```
--app-ticket    --encrypted-ticket    --steam-id
```

错误路径 `Unknown flag: `（`0x8a6c12`，注意尾部有空格，说明是 `f"Unknown flag: {flag}"`）。
内部落到 `_extract_authorization_payload_direct`（`0x8a6c22`）。

## 3. 与验证链的耦合程度（交接问题二）

`src.steam.authorization_workflow_service` 与 `verify_ticket` 在 `.rdata` 中的
**相对位置距离**：服务模块名在 `0x8a55xx` 区，`verify_ticket` 首现在 `0x85bbc4`，
二者相距约 **0x2A0000（2.6 MB）**。而 `verify_ticket` 的**全部 6 处命中**集中在
`0x85bbc4` 与 `0x87c154` 两个簇。

`0x871880` / `0x87c154` 两簇的伴随符号：

```
0x871880  verify_ticket
0x8718b2  clear_verification_ticket, load_verification_cache,
          load_verification_ticket, save_verification_ticket
0x87c12f  RuntimeGuard
0x87c154  verify_ticket
0x87c186  load_verification_ticket
```

`0x874f87` 是唯一的**调用点形态**：

```
['self', 'cached_ticket', 'config', 'current_published_at',
 'cached_code', 'valid', 'ticket', 'exc']
```

这组局部变量（`cached_ticket` + `config` + `current_published_at` + `cached_code` + `valid`）
是 `_check_cached_verification` 的**方法体**，属 `MainWindow`（qualified 名 187 条），
**不在** `authorization_workflow_service` 的引用范围内。

**判定**：CLI 提取路径与票据校验链**无静态共现证据**。沿用同一错误模式
（把邻接读成归属）会把结论写反，所以此处只陈述实测：`verify_ticket` 的 6 处命中
没有一处落在服务模块的常量簇内。**该判定仍属「未被证伪」，不是「已证实解耦」** ——
见 §5 的残余风险。

## 4. 服务端票据的真实结构（超出交接文档的新事实）

`0x85bfd7` 一条 token 完整展开了 `verification_crypto` 的契约：

```
plaintext, ticket, compressed, protected_payload, flags,
issued_at, request_id,
ephemeral_private, ephemeral_public, server_public, shared_secret,
key_material, salt, aead_key, nonce, ciphertext_length,
header, aad, ciphertext
```

`ephemeral_private` / `ephemeral_public` / `server_public` / `shared_secret` 四件套
是**每条票据一次性的 X25519 ECDH**（临时密钥对 + 服务端公钥 + 派生共享密钥），
而非交接文档 2.2 节所记的「Ed25519 验签 + 机器绑定加密」两件套。

这**加强**而非削弱了阻断结论：一次性 ECDH 没有本地伪造路径。
同时它给出一条正面线索 —— CLI 的 `--encrypted-ticket` 参数是**把密文票交给样本，
由样本内部的 `_machine_bound_key` 解封装**，因此 CLI 路径需要的是
**合法的密文票**，不是伪造的。这对本路线的定位很重要：它能让**已持有合法票据**的
场景免弹窗运行，但不构成票据生成路径。**不要把这两件事混为一谈。**

## 5. 残余风险与未确认项

1. **`run_authorization_extract_cli` 是否在内部调用 `_verification_gate_allows`** ——
   未取得代码级证据。这是决定本路线成败的**唯一**变量，且无法从 `.rdata` 常量邻接证明。
   需要 `.text` 侧的调用图。
2. **`--extract-authorization` 是不是对外接口** —— 它出现在 `src/gui/__init__.py` 的
   `__main__` 分发里，但 `KeySteam.exe` 是 **onefile**，onefile 入口的 `sys.argv` 会
   被 bootstrap 处理。`--extract-authorization` 能否经由 `KeySteam.exe --extract-authorization`
   抵达，取决于 onefile 的参数透传行为，**未验证**。
3. **`run` 是哪一个类的 `run`** —— `0x862015` 的 `run` 与 `0x862017` 的 `run` 相邻且
   处于同一分发函数内，但它可能属于 `AuthorizationWorkflowService.run`（92 条 qualified 名
   中有 `run`），也可能属于其他服务。qualified 名清单只能证明「存在名为 run 的方法」，
   不能证明 `0x862015` 处引用的是它。

## 6. 建议的下一个动作

**不要**直接构造宿主去跑 `--extract-authorization`（第 2 条未验证，且 onefile 参数透传
有独立风险）。先做一件成本极低、信息量极大的事：

用 `/mnt/d/03_Work/03_Develop/KeySteam v2.99/_re/work/payload/` 下的**解包目录**
验证 argv 分发是否在非 onefile 形态下可达 —— 该目录直接指向 `main.dll`，
绕过 onefile bootstrap。若 `main.dll` 侧的 `NUITKA_PACKAGE_src` 探测
（`0x862030` / `0x86205a` 的 `\not_existing` 分支）成立，则 argv 分发可在解包形态下生效。

重导命令：

```bash
cd /tmp/ks && python3 dump.py 0x860b00 0x862200      # 分发点与对话框
cd /tmp/ks && python3 dump.py 0x8a5200 0x8a5600      # CLI 参数解析
grep -ao 'uAuthorizationWorkflowService\.[A-Za-z_]*' rdata.bin | sort -u | wc -l   # 92
grep -aco 'verify_ticket' rdata.bin                  # 6
```
