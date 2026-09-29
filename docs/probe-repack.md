# 探针批次：改样本重打包的可行性验证（2026-09-16）

**探针目录**：`D:\03_Work\03_Develop\KeySteam v2.99\_re\probe\`
**基准样本**：`KeySteam.exe`（30,885,138 B），sha256 `8f6dc31084888c64a7e442a91eeb51118dce051649a53076fa7412fc343d803a`
**约束遵守**：原样本全程只读，实验结束复核哈希未变。

---

## 结论先行

**改样本重打包能否消除弹窗：未能确证「端到端消除」，但确证了一条远比它更轻的路径，且确证了两个既有结论为假。**

拆开说：

| 问题 | 判定 |
| --- | --- |
| 改 `main.dll` 重打包整个 onefile | **技术上完全可行**（解包链路实测闭合），但**代价最高**，且不便确证 |
| 换公钥 + 自签票据 | **不自洽**——签名只是一道关卡，本地无法满足其余关卡（含机器绑定） |
| **替换 payload 目录里的 `main.dll`** | **实测无效**——`NUITKA_ONEFILE_DIRECTORY` 被忽略，样本始终从自身嵌入 payload 解包 |
| **外部宿主 `LoadLibraryExW` + `run_code`** | **确证可行**——这是最轻路径，且推翻了两个「已知阻碍」 |

**最轻路径 = 外部宿主（`_re/…/host/host.exe`），不修改 `KeySteam.exe` 一个字节。**

> **确证等级统一标注（2026-09-16 审查后补）**
>
> 上表四条判定的确证等级**并不相同**，`probe-index.md` 的汇总表也需按此读：
>
> | 判定 | 等级 |
> | --- | --- |
> | 替换 payload 目录 `main.dll` **无效** | **直接观测**（实测 `NUITKA_ONEFILE_DIRECTORY` 被忽略、样本仍新建 `onefile_*`） |
> | 两个「已知阻碍」为假 | **直接观测**（导出表实测 `NumberOfFunctions=1`；两轮对照均进 `Nuitka_Main`） |
> | 外部宿主**能加载并调用 `run_code`、驱动 GUI** | **直接观测**（`run_code @ 00007FF92333B380`、窗口与模块路径均经证据链确认） |
> | 外部宿主**能消除弹窗** | **未确证** —— 本次加载的 DLL 只加了无害标记，**验证逻辑原封未动**；且 `RuntimeGuard.start()` 的控制流绑定亦未确证 |
> | 解包链路闭合 | **直接观测**（117 条目、`main.dll` 逐字节一致） |
> | 「改 `main.dll` 可行」 | **多层推断** —— 解包可信，但**压缩端无途径**（`7z a -tzstd` 返回 `E_NOTIMPL`），故「重打包」这一步从未真正走通 |
>
> **读法**：「外部宿主」这条路的**能力**已确证，「它能解决弹窗」这个**效果**未确证。
> 两者的差别是本轮最容易误读之处。

---

## 子问题 1：改 `main.dll` 的可行性与后果

### 1.1 解包实证（完全闭合）

`.rdata` 节内偏移 `0x3b0`（文件偏移 `0x235b0`）处的首字节序列：

```
000235b0: 4b 41 59 28 b5 2f fd 00 88 14 76 02 fa 60 f2 93  KAY(./....v..`..
```

结构判定（逐字节实测，非推断）：

| 偏移 | 内容 |
| --- | --- |
| `0x235b0` | `KAY`（3 B 自有前缀） |
| `0x235b3` | zstd 魔数 `28 B5 2F FD` |
| `0x235b7` | `FHD = 0x00` → `fcs_flag=0`、`single_segment=0`、无校验和、无字典 ID |
| `0x235b8` | `Window_Descriptor = 0x88` → windowSize = 128 MiB |
| `0x235b9` | 首块头起（首块 `type=2`、`bsize=20162`） |

**帧头不含 Frame_Content_Size**，故压缩流长度须靠帧自然结束判定。逐块遍历测得结束于文件偏移 `0x9feafb`，压缩流长 **10,335,560 B**。

解压工具：`zstandard` 模块在本环境**不可用**（`ModuleNotFoundError`，且 `pip` 受 PEP 668 限制）；系统 `7z` 为 **7-Zip 26.00**，原生支持 zstd 解压（`zstd zst tzst`）。

**实测解压命令（可重放）**：

```bash
python3 - <<'PY'
d=open('/mnt/d/03_Work/03_Develop/KeySteam-v2.99/KeySteam.exe','rb').read()
open('/tmp/ks2/s_full.zst','wb').write(d[0x235b3:])   # 从 magic 到文件末
PY
7z x -so /tmp/ks2/s_full.zst > /tmp/ks2/payload.bin
# 7z 退出码 2（尾部有多余数据），但 stdout 是完整正确的 payload
sha256sum /tmp/ks2/payload.bin
```

实测输出 **108,502,413 B**，sha256 `52731314a9246f7badc748038aad0a8126b54c05a1ba72fe88c50c8bb2d12538`。

### 1.2 与 `_re/work/payload/` 的一致性（确证）

解压产物是 **Nuitka onefile 归档**，条目格式为 `UTF-16LE 名字 + \0\0 + u64 长度 + 数据`。逐条解析得 **117 条**，与 `_re/work/payload/` 文件数（117）一致，归档零残余字节（`end == archive size == 0x6779d8d`）。

首条即 `main.dll`，偏移 `0x0`，长度 31,088,128 B。提取后比对：

```
/tmp/ks2/main_from_archive.dll   cc869941663ed46bc8973bc18415d2cabd6e6fe7127a7d692fda450cdc405265
_re/work/payload/main.dll        cc869941663ed46bc8973bc18415d2cabd6e6fe7127a7d692fda450cdc405265
cmp → IDENTICAL
```

**结论：解包链路与 payload 一致性均已确证，无编造。**

### 1.3 重打包的代价（含未确证项）

**已确证的代价**：

1. **zstd 重压缩在本环境不可用。** 实测 `7z a -tzstd` 返回 `System ERROR: E_NOTIMPL : Not implemented`——7-Zip 26.00 的 zstd 是**只读解码器**。必须另找压缩途径（Windows 侧 Python `zstandard`、`zstd.exe`、或纯 Python 实现），否则链路断在压缩端。
2. **RCDATA 资源重写 + PE 大小字段修正是必须的**：payload 嵌在 `.rdata`（rawptr `0x23200`）内，压缩流长度变化会连带改动 `.reloc` 之后的全部布局，需重算节表、`SizeOfImage`、以及 trailer 的 `body_size`。
3. **本地 trailer 签名必然失效。** 实测文件尾 274 字节为明文 JSON：

```json
{"body_sha256":"4281bac40599608f149d818727664104827952ebddb82059903de8173ae2dc54",
 "body_size":30884864,"build_id":"20260911.045414",
 "manifest_sig":"Pl0chOG4tDlXfZTMq/8BLXo3SX+52yxlT+8mWKQch7BDrwqPFfcQfm57C/BKevNpLxouh49M/NKIYqQanFTaCA==",
 "version":"2.99"}
```

随后是 `KEYSTEAMTR1`（`b"KEYSTEAMTR1"`，rdata 节内偏移 `0x1cce5f0`）+ 填充至 274 B。

**关键判定（代码级依据）**：`hash_file_prefix_sha256` 的唯一调用点在 `_verify_local_signature`（rdata 节内偏移 `0x1cceeec`），**哈希对象是 `_current_executable_path()` 解析出的 `KeySteam.exe`**，而非 `main.dll`。`_re/signature_facts.md` 第 7.3 节已实测：`main.dll` 尾部 64 B 全 `00`，**不含 trailer**。

因此：
- 改 `main.dll` 但**不动** `KeySteam.exe` → `body_sha256` **不失配**，本地 trailer 分支**不触发**。
- 改 `KeySteam.exe`（重打包必然如此）→ `body_sha256` **失配** → 本地验签失败。

**「倒卖可耻」的触发需同时满足三个条件**（`_re/integrity_runtime_observability.md` 第 5.2 节，代码级依据）：

1. `_integrity_runtime_supported()` 为 True（**未**走源码运行分支）
2. 本地 Ed25519 验签失败
3. 远程清单回查判定 TAMPERED（`RemoteManifestState` 非 `UNREACHABLE`/`INVALID`）

**未确证**：改 `KeySteam.exe` 后「倒卖可耻」**是否实际弹出**，本次**未实测**。原因：重打包链路卡在 zstd 压缩端（见上），无法产出可运行的完整改包。**不做推断，不写成结论。**

---

## 子问题 2：「换公钥 + 自签」这条链是否自洽

### 2.1 票据结构（实测）

备份票据 `_re/backup/round5-20260915-valid-ticket/verification.cache`（605 B）逐字节解析：

```
KSTK (4 B 魔数) | nonce (12 B: 01c57556ce8ac037bc8888e8) | AESGCM 密文 (589 B, 含 16 B tag)
```

`_TICKET_MAGIC = KSTK`（rdata 节内偏移 `0x899222`）；`first_run.cache` 对应 `KSFR`（`0x899229`）。

### 2.2 票据字段与加密链（rdata 常量簇解码）

`TicketInfo` dataclass 字段（rdata 节内偏移 `0x898aa6`–`0x898ad3`）：

```
purpose / code_hash / published_at / issued_at / expires_at
```

加密与验签链（`src.security.ticket` 模块簇，rdata `0x89851c`–`0x898b00`）：

| 项 | 值 | 节内偏移 |
| --- | --- | --- |
| 票据前缀 | `kst~` | `0x8989bd` |
| `_TICKET_AAD` | `keysteam-ticket-v1` | `0x8989c3` |
| purpose 取值 | `daily` / `sponsor` | `0x8989dd` / `0x8989e4` |
| 对称算法 | `ChaCha20Poly1305` | `0x8985ba` |
| 密钥来源 | `verification_crypto_key`（sha256 派生） | `0x898599` |
| 非对称验签 | `verify_mapping_signature` + `manifest_sig` | `0x898621` / `0x898613` |
| 时间容差 | `_SERVER_SKEW_TOLERANCE_SECONDS` | `0x8986e0` |

### 2.3 除签名外还有几道关卡

`_check_cached_verification`（rdata 节内偏移 `0x86e48d`）的完整调用链，**由常量簇顺序直接读出**：

```
load_verification_ticket          ← ① 读盘 + AEAD 解密（机器绑定密钥）
  → verify_ticket                 ← ② 结构解析 + manifest_sig 验签 + 时间窗
      → published_at  vs  current_published_at   ← ③ 服务端新鲜度比对
  → VerificationService.fetch_config            ← ④ 网络回查服务端配置
      → 失败/无票 → VerificationDialog（「KeySteam 验证」）
  → clear_verification_ticket  /  save_verification_ticket
```

**关卡清单与本地可满足性**：

| # | 关卡 | 代码位置 | 纯本地可否满足 |
| --- | --- | --- | --- |
| ① | AEAD 解密：`AESGCM`，key = `sha256("KeySteam verification cache v1\|" + machine_id)` | `0x898e98`–`0x898eb8`、`0x898f18` | **可**（`machine_id` 本地可读） |
| ② | `manifest_sig` Ed25519 验签 | `0x898613`/`0x898621` | **可**（换公钥即可，但需同时改 `main.dll`） |
| ③ | `published_at` 与 `current_published_at` 比对 | `0x86e53a`/`0x86e54a` | **否**——`current_published_at` 来自 ④ 的服务端响应 |
| ④ | `VerificationService.fetch_config` 网络回查 | `0x86e4e9`/`0x86e4fe` | **否**（`https://key.steamofl.com/api/verification`，rdata `averification_crypto_key` 簇内） |
| ③′ | `_SERVER_SKEW_TOLERANCE_SECONDS` 时间窗 | `0x8986e0` | 可放宽，但需改代码 |

**判定：这条链不自洽。**

换公钥能过 ②，但过不了 ③/④：本地自签的票据**无法提供一个比服务端更新的 `published_at`**——服务端值由 `fetch_config` 返回，本地无从得知也无法伪造。任务描述的「`expected_published_at` 需与服务端比对」**在代码中得到证实**。

**能纯本地满足的只有 ①**（`machine_id` 可读）；② 需要改 `main.dll` 换公钥，即回到子问题 1 的重打包代价；③/④ 本地无解。

---

## 子问题 3：更轻的落点（重点）

### 3.1 替换 payload 目录里的 `main.dll`——**实测无效**

样本为 onefile DLL 模式，bootstrap 会从 `%TEMP%` 下的 `onefile_<pid>_<seq>_<rand>` 目录 `LoadLibraryExW` 该目录的 `main.dll`。该目录**带随机后缀、每次启动重新生成**。

**实验设计**：复制 payload 到 `_re/probe/payload_mod/`，在 `main.dll` 的 `.rdata` 零填充区（节内偏移 `0xd12b65`，659 B 零串）写入标记 `PROBE_LCS_REPACK_MARKER_v1\0`，令其哈希从 `cc869941…` 变为 `1d5a4169e0d3c3f24d51117218d7b5cc66db34c1017e0d781c8cf6ff612db440`。然后设 `NUITKA_ONEFILE_DIRECTORY` 指向该目录并启动。

**实测结果**：

```
NUITKA_ONEFILE_DIRECTORY = D:\...\_re\probe\payload_mod
payload main.dll exists = True
→ 样本仍新建 onefile_5940_203596_I8QL2v5RxVI（117 文件）
→ 该目录 main.dll sha256 = cc869941663ed46b…   ← 原始值！
→ 标记串 "PROBE_LCS" 命中数 = 0
```

**判定：`NUITKA_ONEFILE_DIRECTORY` 被样本忽略，payload 始终从 `KeySteam.exe` 自身嵌入的 RCDATA 解出。** 静态替换 payload 目录**不生效**。

**机制解释**：该环境变量的真正语义是「宿主可执行文件所在目录」（`OnefileBootstrap` 的 `stripBaseFilename(binary_filename)`），**不是**「从这里读 payload」。宿主侧 `host/README.md` 已记录此点。

### 3.2 外部宿主——**确证可行（推荐路径）**

**实测命令（可重放）**：

```powershell
$probeDir='D:\03_Work\03_Develop\KeySteam v2.99\_re\probe\payload_mod'
$env:NUITKA_ONEFILE_DIRECTORY=$probeDir
& 'D:\03_Work\03_Develop\FucKeySteam\host\host.exe' --dll "$probeDir\main.dll"
```

**实测输出**（宿主 stderr，逐字）：

```
[host] dll      = D:\03_Work\03_Develop\KeySteam v2.99\_re\probe\payload_mod\main.dll
[host] payload  = D:\03_Work\03_Develop\KeySteam v2.99\_re\probe\payload_mod
[host] switches = env:inject  third:dll path
[host] run_code @ 00007FF92333B380
[host] argc     = 1
[host]   argv[0] = D:\...\payload_mod\KeySteam.py
[host]   NUITKA_ONEFILE_DIRECTORY=D:\03_Work\03_Develop\FucKeySteam\host
[host]   NUITKA_ORIGINAL_ARGV0=D:\...\payload_mod\KeySteam.py
[host] calling run_code(argc=1, argv=00000269A5789E70, dll=D:\...\payload_mod\main.dll)
```

**进程与窗口状态**：

```
PID=14412  alive
windows: [KeySteam 验证] [KeySteam v2.99]
模块加载：D:\...\_re\probe\payload_mod\main.dll   ← 我们的改动版本
主窗口标题 hex：004B 0065 0079 0053 0074 0065 0061 006D 0020 0076 0032 002E 0039 0039 → "KeySteam v2.99"
弹窗标题 hex：  004B 0065 0079 0053 0074 0065 0061 006D 0020 9A8C 8BC1 → "KeySteam 验证"
```

**GUI 完整启动、窗口稳定、进程 `Responding=True`、工作集 132.6 MB、11 线程。**

### 3.3 两个「已知阻碍」的实测结论——**二者均不成立**

**阻碍一：`GetProcAddress("run_code")` 返回 0 —— 证伪**

- 导出表实测（`objdump -p`）：`main.dll` 有且仅有 **1 个导出**，`run_code`，**RVA = `0x143b380`**，ImageBase `0x180000000`。
- 宿主实测打印 `run_code @ 00007FF92333B380`。以 `0x7FF923200000` 为基址：`0x7FF923200000 + 0x143b380 = 0x7FF92333B380` **精确吻合**。
- 若 `GetProcAddress` 返回 NULL，宿主会以退出码 4 终止（`host.c:372`）。实测**未退出**，且全程控制台无 `FATAL: GetProcAddress` 行。

**阻碍二：`pyinit_core_reconfigure` 失败 —— 未复现**

- 宿主两轮对照实验（`env:inject` 与 `env:skip`）均正常进入 `Nuitka_Main`，无任何 `pyinit` 相关错误。
- **关键**：`host/README.md` 明确记载——`run_code` 调用 `Nuitka_Main`，后者以 `Py_Exit` 终止整个进程，**正常路径宿主永不返回**。实测进程长时间存活，正是该路径被走通的正面证据。

**`run_code` 真实签名（反汇编确证）**：

```asm
18143b380: sub  $0x28,%rsp
18143b384: mov  %ecx,%eax            ; argc
18143b386: test %r8,%r8              ; 第 3 参判 NULL（后被证实为 dll_filename，非 envp）
18143b389: je   0x18143b393
18143b38b: mov  %r8,%rcx
18143b38e: call 0x1814135e0          ; = setDllFilename（写入 _pseudo_dll_filename）
18143b393: mov  %eax,%ecx
18143b395: call 0x18143a430          ; Nuitka_Main(argc, argv)
```

**原判：「第 3 参是 `envp` 而非 `dll_filename`」—— 该判断错误，见下方推翻说明。**

> ### ⚠️ 以上结论**已被主会话推翻**（2026-09-16）——第 3 参**就是** `dll_filename`
>
> 本节的推断依据是「`test r8,r8` 判 NULL 后传递」，认为 `envp` 是可选参数而 `dll_filename` 不必判 NULL。
> **这个推理有个未验证的跳跃**：没有追进被调用者的内部。追进去后结论反转。
>
> **`run_code` 的完整反汇编**（`RVA 0x143b380` → 文件偏移 `0x143a780`）：
>
> ```
> 0143a780  48 83 ec 28            sub  rsp, 28h
> 0143a784  8b c1                  mov  eax, ecx      ; argc
> 0143a786  4d 85 c0               test r8, r8        ; 第 3 参判 NULL
> 0143a789  74 08                  jz   short +8
> 0143a78b  49 8b c8               mov  rcx, r8       ; 第 3 参 → rcx
> 0143a78e  e8 4d 82 fd ff         call 0x1814135e0
> 0143a793  8b c8                  mov  ecx, eax
> 0143a795  e8 96 f0 ff ff         call 0x18143a430   ; Nuitka_Main
> ```
>
> **被调用者 `0x1814135e0` 的完整函数体**（文件偏移 `0x14129e0`）：
>
> ```
> 014129e0  48 89 0d c9 74 9d 00   mov  [rip+0x9d74c9], rcx
> 014129e7  c3                     ret
> ```
>
> **这是一个「把参数写入全局变量后返回」的单指令函数**，即 `setDllFilename`。
> 它写入的全局变量就是 `_pseudo_dll_filename`——与 `docs/host-contract.md` 记录的
> `48 89 0d c9 74 9d 00    mov [rip+0x9d74c9],rcx   ; _pseudo_dll_filename = rcx`
> **字节级一致，连位移量 `0x9d74c9` 都相同**。
>
> **`dll_filename` 同样需要判 NULL** —— `host-contract.md` §2 引的 Nuitka 源码就是
> `if (dll_filename != NULL) { setDllFilename(dll_filename); }`。
> 所以「判 NULL 后传递」这个指令模式**不能**用来区分 `envp` 与 `dll_filename`，
> 本节据此下的判断无效。
>
> **正确签名：`int run_code(int argc, wchar_t **argv, const wchar_t *dll_filename)`**
> —— 与 `docs/host-contract.md` §2、`CONTEXT.md` 的记载一致，**原记录本来就是对的**。
> 调用方应传 `main.dll` 的绝对路径。
>
> **与 `envp` 无关**：环境变量注入走的是进程自身的环境块（宿主调 `run_code` 前用
> `SetEnvironmentVariableW` 设置），不是通过 `run_code` 的参数传递。
>
> **本条错误已登记进 `docs/agents/domain.md` 的 drift 表。**

### 3.4 代价评估

宿主路径的代价是**全部路径中最低的**：

- 不修改 `KeySteam.exe`（基准哈希保持 `8f6dc310…`）
- 不修改 payload（可另复制一份 `main.dll` 供宿主直接加载，`_re/probe/payload_mod/main.dll` 即为此形态）
- 无需解包/重压缩/重写 RCDATA/修 PE 字段
- 宿主 `host.exe` 已构建完成（PE32+ x86-64，约 64 KB）

**唯一前置条件**：宿主与 payload 目录需并存；`main.dll` 的静态依赖（`python312.dll`、`vcruntime140.dll`、`msvcp140*.dll`、`api-ms-win-crt-*`）必须能从 payload 目录解析——`AddDllDirectory` + `LoadLibraryExW(…, 0xD00)` 已处理。

**幂等性**：宿主每次运行**重新加载我们指定的 `main.dll`**，不受随机 `onefile_*` 目录影响。这是它能绕开子问题 3.1 那个失败实验的根本原因。

---

## 子问题 4：签名与完整性检查的实际强度

### 4.1 各检查的触发条件（代码级依据）

| 检查 | 触发条件 | 本次实验是否触发 |
| --- | --- | --- |
| 本地 trailer 签名 | `body_sha256` 对 `KeySteam.exe` 前 `body_size` 字节 | **否**——未改 `KeySteam.exe` |
| 远程清单 `version.json` | `verify_remote_manifest_async`，回查 GitHub/jsDelivr | 未确证（依赖网络可达性） |
| `RuntimeGuard` 模块扫描 | `_scan_self_and_raise` → `psutil.memory_maps()` 按 4 类规则分类 | **未确证**——实测无 `--watchdog` 子进程，但**子进程缺席不能证明扫描未触发**（见下方注） |

### 4.1.1 ⚠️ 「无看门狗子进程」是负观测，不能单独证明任何分支

上表最后一行曾被写成「**否** —— 实测无 `--watchdog` 子进程」，
**该推理不成立**：子进程缺席**至少有两个活解释**——

1. 走通了 `.py` 降级路径，故未启动看门狗；
2. 看门狗 **spawn 失败**（样本自身定义了 `_watchdog_failed` / `_restart_watchdog`
   与「降级为仅自检模式」的状态）。

**一个负观测若有两个活解释，就不能归属给其中任一个。**

这与本仓库 drift 表已登记的一条**逐字同构**（`_frozen_runtime_supported` 那条：
「一个缺失的看门狗进程不能证明 `.py` 后缀分支被走到」）。**同一错误在本轮第二次出现。**

**因此该项的正确状态是「未确证」**，而不是「否」。
判定 `.py` 降级路径是否被走通，**唯一有效证据是最终的弹窗行为**
（`host.c` 的注释亦如此指明：「there is no intermediate state the host can inspect
... The only evidence is the final dialog behaviour」）。

### 4.2 `_integrity_runtime_supported()` 的降级链（确证）

rdata 节内偏移 `0x89352f`–`0x893571` 的常量簇，**顺序即逻辑**：

```
argv → resolve → _entry_path → suffix → strip → casefold → '.py' / '.pyw'
    → _running_from_python_source
```

`argv[0]` 以 `.py`/`.pyw` 结尾（大小写无关）→ 判定为「源码运行」→ 完整性校验返回 `DISABLED`，**跳过 Ed25519 比对**。

**同构证据**：`RuntimeGuard` 内含同一组常量（rdata 节内偏移 `0x8965f9`–`0x896617`：`argv`/`resolve`/`suffix`/`.py`/`.pyw`），与 `IntegrityService` **完全同构**。

**实测印证**：宿主默认传 `argv[0] = …\KeySteam.py`。实测结果——

- 出现窗口：`KeySteam v2.99` + `KeySteam 验证`
- **未出现**「倒卖可耻」`TamperWarningDialog`
- **无** `--watchdog` 子进程（`Win32_Process` 查询父 PID 下仅有 `conhost.exe`）
- **无**本进程新建的 `keysteam_guard_*` 管道

这几项**主动行为的缺失**，与 `.py` 降级路径被走通**一致**——
但**仅为一致，不构成确证**（见 §4.1.1：负观测有多个活解释，
且 `RuntimeGuard.start()` 的控制流绑定本身未确证）。
**判定该分支是否真的被走通，唯一有效证据是最终的弹窗行为。**

### 4.3 「不弹窗」作为判据的强度（诚实标注）

`_re/integrity_runtime_observability.md` 第 5.2 节已指出：「不弹窗」是**否定证据**，无法区分三种情况（走了 DISABLED 分支 / 签名意外验通过 / 远程回查走 UNREACHABLE）。

**本次实验比该判据强的地方**在于观测了**主动行为的缺失**（无看门狗子进程、无新管道、无 `TamperWarningDialog`），而非仅仅「没弹窗」。

**未确证项**：

1. `RuntimeGuard.start()` 是否**真的**以 `_frozen_runtime_supported()` 为提前返回条件——常量表只证明该判定函数存在且与 `.py/.pyw` 同构，**未证明控制流绑定**。需反汇编 `RuntimeGuard.start` 才能定论。
2. `_classify_module` 的 `strict` / `temp_rule` 默认值——无字面量锚点，**未取得代码级证据**。
3. `integrity_clean_reason` / `INTEGRITY_LOCKED_MESSAGE` 的字面文本——属 `obfuscated_strings` 表 XOR 编码，密钥运行期派生，**未解出**。

### 4.4 重放命令

```bash
# ① 节转储
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
        open('/tmp/ks2/'+name.strip('.')+'.bin','wb').write(d[rawptr:rawptr+rawsize])
        print(name, rawsize, 'VA=%x'%vaddr)
PY

# ② payload 解包 + 一致性校验
python3 -c "
d=open('/mnt/d/03_Work/03_Develop/KeySteam-v2.99/KeySteam.exe','rb').read()
open('/tmp/ks2/s_full.zst','wb').write(d[0x235b3:])"
7z x -so /tmp/ks2/s_full.zst > /tmp/ks2/payload.bin
sha256sum /tmp/ks2/payload.bin   # 52731314a9246f7badc748038aad0a8126b54c05a1ba72fe88c50c8bb2d12538

# ③ 导出表
objdump -p "/mnt/d/03_Work/03_Develop/KeySteam-v2.99/_re/bin/main.dll" | sed -n '/The Export Tables/,/^$/p'

# ④ run_code 签名
objdump -d --start-address=0x18143b380 --stop-address=0x18143b3a0 \
  "/mnt/d/03_Work/03_Develop/KeySteam-v2.99/_re/bin/main.dll"

# ⑤ 宿主加载（Windows 侧）
# powershell.exe -File <USERPROFILE>\AppData\Local\Temp\tamper_check.ps1
```

---

## 最轻路径

**外部宿主加载 `main.dll`——不动 `KeySteam.exe` 一个字节。**

`_re/probe/payload_mod/main.dll`（标记版）+ `FucKeySteam/host/host.exe`，实测能完整驱动 GUI、稳定运行、加载指定 DLL。

它比重打包 onefile 轻的原因：

1. 绕开 zstd 压缩端不可用的死结
2. 绕开 RCDATA 重写与 PE 字段修正
3. 天然规避本地 trailer 签名失配（`body_sha256` 只覆盖 `KeySteam.exe`）
4. 每次运行**确定性**地加载我们指定的 DLL，不受随机 `onefile_*` 目录干扰

**适用前提**：`.py` 后缀的 `argv[0]` 使完整性校验降级为 `DISABLED`（已实测印证，但 `RuntimeGuard.start()` 的控制流绑定**未确证**）。

---

## 未确证

以下各项**未取得实证**，不得当作结论引用：

1. **改 `KeySteam.exe` 后「倒卖可耻」是否实际弹出**——重打包链路卡在 zstd 压缩端（`7z` 返回 `E_NOTIMPL`），未产出可运行改包，**未实测**。
2. **`RuntimeGuard.start()` 是否以 `_frozen_runtime_supported()` 为提前返回条件**——常量同构已知，控制流绑定未知。
3. **`_classify_module` 的 `strict` / `temp_rule` 默认值**——无字面量锚点。
4. **远程清单回查在本次实验中的实际结果**——`RemoteManifestState` 取值（`REACHABLE`/`UNREACHABLE`/`INVALID`）未观测。
5. **`integrity_clean_reason` / `INTEGRITY_LOCKED_MESSAGE` 字面文本**——XOR 编码未解出。
6. **宿主路径下的弹窗消除**——本次实测中弹窗**照样出现**（因为加载的 DLL 只加了无害标记，未改验证逻辑）。宿主提供的是**承载能力**，消除弹窗仍需配合对 `main.dll` 的改动。**「宿主 + 改过的 DLL」这一组合的端到端效果未实测。**

---

## 附：环境与产物

**探针副本路径**：

| 产物 | 路径 | 说明 |
| --- | --- | --- |
| 样本副本 | `_re/probe/exe/KeySteam_probe.exe` | sha256 `8f6dc310…`（与原样本一致） |
| 改过的 payload | `_re/probe/payload_mod/main.dll` | sha256 `1d5a4169e0d3c3f…`（含标记） |
| 窗口截图 | `_re/probe/shots/host_window.png` | 1931×823 |
| 观测脚本 | `_re/probe/run_probe_env.ps1` | 环境变量路径实验 |

**原样本状态**：未修改，哈希 `8f6dc31084888c64a7e442a91eeb51118dce051649a53076fa7412fc343d803a` 全程保持。

**进程与管道**：实验结束已确认无 `KeySteam` / `host` 残留进程。管道 `keysteam_guard_aea5a276168c742f` 存在，经核验是**先前强杀样本时泄漏的孤儿管道**（句柄未释放），**非**本次宿主创建——实验中的宿主模式下无 `--watchdog` 子进程。

**数据目录**：`userdata/<main-id>` 零文件（未被写入）。实验期间 `verification.cache`（605 B，`b044406c…`）出现在数据目录，经比对与 `_re/backup/round5-20260915-valid-ticket/verification.cache` **字节相同**——系并发实验恢复，**非本次实验写入**（本探针全程使用独立 payload 副本，未触发样本的票面读写路径）。

**遗留物**：`%TEMP%` 下有多批 `onefile_*` 目录（117 文件/个），来自被强杀的样本进程——正常退出时样本会自行清理。
