# 运行方案（ticket #3 的实测部分）

**状态**：前置条件已满足，可执行。本文是执行清单，不是执行结果。

---

## 前置条件

**必须全部满足才开跑：**

- [x] 第三参数的真实语义已核实：**它不是环境块**，是 `main.dll` 的绝对路径宽字符串。`host.c` 已按此重写并重新编译通过。
      （早先按环境数组实现的版本已废弃——那个错误不会崩溃，只会静默产出垃圾路径。）
- [x] **本机状态已实测记录**，取代原先「隔离环境」的空勾选框。本机**不是**隔离环境——它已经在运行同类工具（见下）。实测事实：
      - 当前登录 `drivpe114514`（account_id `702986969`，userdata 816 K，小号）
      - 主号 `zdk84214`（account_id `1398488476`，userdata 9.4 M）处于 `AutoLogin=0` 离线态
      - 三账号 `RememberPassword=1`，`ssfn*` 令牌文件 **0 个**
      - `HKCU\...\ActiveProcess\ActiveUser = 0x0`（无效值）
      - `loginusers.vdf` **无 `MostRecent` 字段**（三账号均无）
      - 还原点/卷影副本状态**读不到**（非管理员），按「未知」计
- [x] `host/host.exe` 已构建。**注意：仓库中曾存在一个与源码不同步的旧 `host.exe`**（见「构建同步」一节）。
- [x] 监控脚本已就位：`_re/monitor_keysteam.ps1`。

---

## 构建同步（2026-09-15 实测发现）

仓库里曾同时存在两个不同内容的 `host.exe`：

```
旧件  8c135a8b1502d0406dff76acfffaa1ee
新编  9ce252186e248f7e4af4e379a510ee1d
```

两者同为 63,980 B，但内容不同——旧件是 `2813b28`（第三参数修正）**之前**编译的。它不会崩溃，只会按「第三参数 = 环境块」的错误语义静默产出垃圾路径，然后被误判为「argv 方案不成立」。

**因此：每次运行前必须重编，不要相信仓库里的 `host.exe`。**

```bash
bash host/build.sh
```

产物不入库（`.gitignore`），库里只有源码。**不要**把 `host.exe` 提交进 git——否则「源码改了忘了重编」时仓库里两个状态都合法，无法判断谁对。这正是上面那次事故的成因。

---

## 本机不是隔离环境：这意味着什么

`AGENTS.md` 与本文件原先都按「样本投放到干净环境」写。实测表明实际情境是**在一台已经在使用同类工具的机器上调试其中一版**：

```
D:\02_Games\01_Steam\Steam\KeySteamTool.dll     6,619,136 B   2025-09-13
D:\02_Games\01_Steam\Steam\cloud_redirect.dll   1,726,976 B   2025-09-12
D:\02_Games\01_Steam\Steam\cloud_redirect.log     289,397 B   2025-09-15   ← 今天有写入
D:\02_Games\01_Steam\Steam\config\stplug-in\     5 个脚本
D:\02_Games\01_Steam\Steam\steam.exe.old         与在用 steam.exe 哈希不同
```

`steam.exe` 与 `steam.exe.old` 哈希、日期全不同，当前跑的是被替换过的版本。**回滚 `.old` 会同时让 `keysteamtool/` 下那三个 64 位十六进制命名的 `.toml` pattern 文件哈希失配**，即连带废掉现有工具功能。回滚不是干净的安全网。

完整资产清单与主号保护依据见 `AGENTS.md`。

---

## 样本自身的破坏性行为（静态确证）

样本在 `main.dll` 里带清理逻辑，会**杀掉 Steam 进程并清理插件目录**——这是写明的行为，不是可能的副作用：

```
0x8b2c95  terminate_all                              （SteamProcessManager）
0x8acc31  即将关闭 Steam 相关进程喵~
0x8acb79  清理会干扰初始化的旧插件文件
0x8ad337  .ks      0x8ad33f  .lua      0x8ad345  .ks
```

现有 `config/stplug-in/*.lua` 与 `*.ks` 在清理范围内。**跑之前先备份该目录。**

---

## 数据目录备份状态（已核实，2026-09-15）

| 文件 | 备份 md5 | 活动副本 md5 | 一致 |
|---|---|---|---|
| `verification.cache` | `25eadfb9d06713ffe4473dc1b221dabc` | 同 | ✅ |
| `first_run.cache` | `cb98ebeca1c7c1b4302b96b93ce982e9` | 同 | ✅ |
| `shiki.json` | `7a996f1a3629cacfa937f7153c21d2eb` | 同 | ✅ |
| `shiki.kodo` | `959dc636b94c7df7d8f0b21dd617d20d` | 同 | ✅ |

备份位置：`_re/backup/Shikieiki_orig/`（含 `shiki/` 子目录）

**恢复命令**：
```bash
cp _re/backup/Shikieiki_orig/{verification.cache,first_run.cache,shiki.json,shiki.kodo} \
   /mnt/c/Users/Hidriver/AppData/Roaming/Shikieiki/
```


---

## 为什么两次运行的顺序是「有缓存优先」

「两种都跑」的顺序不是任意的：

1. **先跑保留缓存的那次**。它对磁盘状态无破坏性——若票据有效，程序正常走完；若无效，程序自己改写缓存，而这**正是要观测的**。这一次回答「票据恰好有效」这个替代解释是否成立。
2. **后跑移除缓存的那次**。移除是破坏性的，放最后，以便随时中止。这一次让票据状态变为**已知缺失**，消除归因歧义。

反过来（先移除缓存）会毁掉第一次运行的机会——第一次运行的状态无法再复现。

---

## 第 1 次运行：保留缓存

### 步骤

1. **先启动监控**（顺序不可颠倒；弹窗是模态的，失败态只能退出，先看再跑才拿得到数据）：
   ```
   powershell -ExecutionPolicy Bypass -File monitor_keysteam.ps1 -Seconds 120
   ```
   监控会记录：进程、命名管道、网络连接、窗口标题、数据目录变化。

2. **在监控运行期间**，另开终端启动宿主：
   ```
   host\host.exe --dll "D:\03_Work\03_Develop\KeySteam v2.99\_re\work\payload\main.dll"
   ```

3. 记录宿主的 stdout 与 stderr（`[host]` 前缀行）与退出码。

### 本次要观测的

| 观测项 | 判读 |
|---|---|
| `[host] dll = ...` / `payload = ...` | 路径推导是否符合预期 |
| `[host] 3rd arg = main.dll path` | 第三参数模式；`NULL (control run)` 仅 `--no-envp` 时出现 |
| `[host] argc = N` 与逐条 `argv[i]` | argv 构造；**`argv[0]` 必须以 `.py` 结尾**，这是本方案的载荷 |
| `[host] run_code @ 0x...` | 非 NULL ⇒ `GetProcAddress` 成功，「已知阻碍 1」被证伪 |
| `keysteam-runtime-guard` 进程 | 出现/不出现 |
| `\\.\pipe\keysteam_guard_` | 出现/不出现 |
| 出站连接 | 清单 |
| **标题 `倒卖可耻` 的窗口** | **出现 ⇒ 完整性链判定 TAMPERED，argv 方案失败**。不出现 ⇒ 完整性链被跳过 |
| `VerificationDialog`（无 × 的弹窗） | 记录，但**只作环境状态**——见下方归因限制 |
| `config/stplug-in/` 目录变化 | 样本的清理逻辑是否触发（会删 `*.lua`/`*.ks`） |
| `userdata/1398488476/` 是否被写 | 主号保护的实际验证（预期：不写） |

### 一个**不可达**的观测项（2026-09-15 修正）

早先本表把 `[host] run_code returned N` 列为判据，写着「出现 ⇒ 调用完成，第二个已知阻碍被证伪」。**这一项在正常路径下永远不出现。**

证据（Nuitka 上游源码）：

```
MainProgram.c:2402   return Nuitka_Main(argc, argv);        ← run_code 无条件转发
MainProgram.c:2325   EXECUTE_MAIN_MODULE(...)               ← 用户代码在此执行
MainProgram.c:2355   Py_Exit(exit_code)                     ← 进程在此终止
```

`run_code` 正常路径**不返回**——`Py_Exit` 直接终结整个进程。所以 `host.c` 末尾的 `return status`（`host.c:438`）与那行 `[host] run_code returned N` 只在**异常路径**可见。看到它，说明出事了，不是说明成功了。

Nuitka 上游源码自己对这件事有明示（`MainProgram.c:2357`，紧接 `Py_Exit(exit_code)` 之后）：

```
// The "Py_Exit()" calls is not supposed to return.
```

即这不是从调用链推出来的结论，是上游写明的契约。

**不要**把「`run_code returned` 尚未出现」当作「还没跑完」的信号——那是一个永恒状态，直到进程死掉。

### 归因限制（重要）

`VerificationDialog` 有两条独立触发链，叠加在同一现象上：

- 完整性链：`IntegrityState == TAMPERED` → 篡改警告（标题 `倒卖可耻`）
- 票据链：票据缺失/失效/轮换/网络失败 → `VerificationDialog`

因此**「弹窗未出现」不能证明 argv 方案生效**——还需排除「票据恰好有效」这个替代解释。

**具备归因能力的判据是 `倒卖可耻` 窗口是否出现**，不是验证码弹窗。

关于票据有效性的两种说法（`#3` 评论一度断言「两天前的缓存不可能仍然新鲜」，`#4` 评论在 23 秒后**明确撤回**该断言）：

- 已确认：票面含 `expires_at`，票据失败会触发弹窗。
- **未知**：`expires_at` 的具体时长。「每日轮换」指服务端码版本（`published_at`），与票面时长不是同一件事。

**所以不能断言「当前票据已过期」。能断言的是：票据有效性未知，这是本次观测的一个未受控变量。** 下游一切判读取 `#4` 的保守版本。

### 宿主的内部态**不可观测**（2026-09-15 修正）

`host.c` 曾经的两处注释把「`.py` 后缀关闭完整性自检」说成 Nuitka 的运行机制。**归因错了层。** 实测：

```
grep -rn 'pyw\|\.py"' OnefileBootstrap.c MainProgram.c HelpersFilesystemPaths.c  → 零匹配
```

Nuitka 的 C 运行时**没有**任何后缀分支。该判定位于**样本自己打包进 `main.dll` 的编译后 Python 代码**里（常量元组 `P\x02u.py\0u.pyw\0`，VA `0x01cd04d0`；见 `docs/host-contract.md:143-151`）。

**推论：宿主侧看不到任何中间态。** 不存在「`[host] integrity skipped`」这样一行——它无法存在。判定是否生效，只能靠最终弹窗反推。


---

## 第 2 次运行：移除缓存，票据状态已知

### 步骤

1. 备份并移走缓存（备份已在 `_re/backup/Shikieiki_orig/`，此步可逆）：
   ```bash
   mv /mnt/c/Users/Hidriver/AppData/Roaming/Shikieiki/verification.cache \
      /tmp/verification.cache.removed-$(date +%s)
   ```
2. 重复第 1 次运行的监控与启动步骤。
3. 观测同一张表。

### 本次的判读

票据缺失是**已知且预期**的状态：

- `VerificationDialog` 必然出现——**这是预期行为，不是失败**。
- `倒卖可耻` 若仍不出现 ⇒ 完整性链被跳过的**正向证据**（本次已排除票据链的干扰）。
- `verification.cache` 是否被**新建**：若程序在验证未通过时不写缓存，则该文件应保持缺失；若被创建，说明程序在无票据状态下也落了盘，需要记录。

---

## 变量对照表（两次运行的差异）

| 变量 | 第 1 次 | 第 2 次 |
|---|---|---|
| `verification.cache` | 存在（2026-09-13 20:26，605 B） | 移除 |
| `first_run.cache` | 存在（2026-09-12 13:49，63 B） | 不变（首运行弹窗应不出现，这是范围边界） |
| `--no-envp` | 不用（传 `main.dll` 路径） | 不用 |

两次都传 `main.dll` 的绝对路径作为第三参数。

### `--no-envp` 的真实语义（与 `#4` 的一条归因假设冲突）

`--no-envp` **不是**一个单纯的「第三参数对照组」。看 `host.c:426`：

```c
const wchar_t *third = use_envp ? dll_path : NULL;
```

而 `use_envp` 同时还包着 `host.c:394` 那段 `SetEnvironmentVariableW`（`NUITKA_ONEFILE_DIRECTORY` 与 `NUITKA_ORIGINAL_ARGV0`）。所以这个开关**同时关掉两件事**：

1. 第三参数从 `main.dll` 路径变为 `NULL`；
2. 两个环境变量都不设置。

`#4` 的评论提出「观测 `NUITKA_ONEFILE_DIRECTORY` 注入是否生效」可作为独立于两条弹窗链的**第三证据**。在 `host.c` 当前形态下，**这个实验做不出来**——要观测 env 注入结果就必须跑 `use_envp=1` 那一路，而那一路上第三参数也同时被传了，两个变量绑死在一起。

更根本的疑问在静态分析里：`NUITKA_ONEFILE_DIRECTORY` 在 Nuitka 的 `MainProgram.c` 中**完全不出现**（只在 `OnefileBootstrap.c` 语境使用）。而本宿主**不是** onefile bootstrap，是直接加载 dll。所以这个环境变量对本样本**可能根本没有消费点**——若真如此，`#4` 那条归因逻辑与「`.py` 后缀」犯的是同一个错层错误。

**结论：本条留作已知限制，不在本轮修复。** 要让它可用，需在 `host.c` 增加独立开关（第三参数与 env 分开控制）并重新构建；但在此之前应先确证样本是否真的读取该变量，否则观测了也没有读数。

`--no-envp` 的 NULL 变体留到两次都跑通后再做——它是**对照组**，价值在于回答「第三参数传 NULL 时行为如何不同」，而不是回答「argv 方案是否成立」。在没有基线的情况下跑对照组没有判读意义。


---

## 中止条件

**双条件制**（2026-09-15 修正）。原判据「宿主进程挂起超过 120 秒且无输出」会**误杀正常运行**：因为 `run_code` 正常路径不返回（见上），宿主打完最后一行 `[host] calling run_code(...)` 之后就**再无任何输出**，且这是预期状态。若按「120 秒无输出即终止」执行，会在程序正常运行时把它当成挂起杀掉。

改为两条并列，任一满足即终止：

| 条件 | 动作 | 说明 |
|---|---|---|
| **出现标题 `倒卖可耻` 的窗口** | **立即终止** | 这是不可关闭的对话框，唯一按钮是「退出程序」，已无观测价值。也是 argv 方案失败的判据。 |
| **超时上限 600 秒**（无论有无输出） | 终止 | 兜底。覆盖「联网阻塞」等无输出但未崩溃的情形。 |

超时可调，但**不要低于 300 秒**——样本会联网（`_fetch_verification_config()`），网络等待期无输出属正常。

另外两类情况也应终止并记录：

- 出现意料之外的进程创建或外连目标。
- `config/stplug-in/` 被清理（说明样本的 cleanup 逻辑已触发，超出本票观测范围）。

---

## 跑之前必须做的一件事：备份插件目录

样本会**杀掉 Steam 进程并清理 `config/stplug-in/`**（静态确证，见前文「样本自身的破坏性行为」）。当前该目录有 5 个脚本：

```
1943950.lua    308 B   09-12 13:55
2060160.ks     461 B   09-12 13:55
2161700.lua    676 B   2025-08-01
246420.lua     257 B   2025-08-07
3934270.lua    393 B   09-12 13:56
```

```bash
# 跑之前
cp -a "/mnt/d/02_Games/01_Steam/Steam/config/stplug-in" \
      "/mnt/d/03_Work/03_Develop/keysteam-unlock-spike/.scratch/stplug-in-backup-$(date +%Y%m%d-%H%M%S)"
```

跑完对照恢复。这是本轮唯一**预期会丢失**的东西。

### 一个需要提前决定的边界：初始化成功后怎么办

本方案要观测的是「完整性链是否被跳过」，而**不是**让程序完成初始化。但这两件事连续发生——验证链通过后，`start_initialization` 会继续，程序随即开始操作 Steam 目录。

也就是说：**如果 argv 方案生效，最可能的结果不是「什么都不发生」，而是「程序真的跑起来了」**，随后它会杀 Steam、清插件、读写 Steam 目录。

`#3` 的问题只是「宿主能否加载并调用」，**观测到 `[host] run_code @ 0x...` 出现即已足够回答本票的问题**。

| 处置 | 说明 |
|---|---|
| **观测到 `run_code @` 出现 + `倒卖可耻` 未出现，即可判定并通过窗口终止** | 最保守。两个条件都拿到，本票问题已答完。 |
| 让它跑完 | 会杀 Steam、清插件、读写 Steam 目录。仅在明确要观测完整初始化链时选择。 |

建议取前者。若在第 2 次运行（票据已知缺失）中弹窗按预期出现、且没有 `倒卖可耻`，那么**不必等到程序自然结束**就可以判定完整性链被跳过——因为那时 `run_code` 不会返回，等下去只是让样本拿到更多控制权。


---

## 事后必做

1. 恢复数据目录（若第 2 次运行移除了缓存）：
   ```bash
   cp _re/backup/Shikieiki_orig/verification.cache \
      /mnt/c/Users/Hidriver/AppData/Roaming/Shikieiki/
   ```
2. 恢复 `config/stplug-in/`（见「跑之前必须做的一件事」）。
3. 核对原始样本未被改动：
   ```
   01560c951afd1ce35350ea86a58c1989  KeySteam.exe
   2948792df5b1484a426580927abb0882  main.dll
   ```
4. 核对主号目录未被写入（主号保护的实测验证）：
   ```bash
   find "/mnt/d/02_Games/01_Steam/Steam/userdata/1398488476" -newermt "<开跑时间>" -ls
   # 预期：无输出
   ```
5. 保留宿主 stdout/stderr 与监控日志，两者成对存档。

---

## 一次都没跑过的东西（诚实标注）

`host.exe` 自构建以来**从未运行**。以下仍属未验证（静态分析能回答的已标注）：

| 项 | 状态 |
|---|---|
| `LoadLibraryExW` 是否真的成功 | **未验证**——需实测 |
| `GetProcAddress` 是否真的返回非 NULL | **未验证**——需实测；这是「已知阻碍 1」 |
| 第三参数（`main.dll` 路径）是否被正确消费 | **未验证**（消费点 `setDllFilename` 仅存指针，已静态确证；但传参是否正确到达需实测） |
| `argv[0]` 的 `.py` 后缀是否真的触发源码运行分支 | **未验证**，且**结构性不可观测**——判定在样本 Python 层，宿主侧无中间态。只能靠最终弹窗反推。 |
| 两个「已知阻碍」在原生宿主下是否消失 | **未验证**——需实测 |
| `pyinit_core_reconfigure: failed to read thread state` | **未验证**——「已知阻碍 2」 |

宿主自身的错误路径（返回码 2/3/4）也未经触发。

**注意**：`run_code` 正常路径不返回（`Py_Exit` 终结进程），所以「程序跑起来了但宿主没退出」不是挂起，是正常。判读见「中止条件」。

