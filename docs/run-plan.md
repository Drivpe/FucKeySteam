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

## 执行方式与路径前提（2026-09-15 实测确认）

**分工**：监控从 WSL 侧调起，宿主由人在 Windows 终端手动敲。

理由来自一次 WSL↔Windows 互操作实测：从 WSL 调起什么程序都可以（stdout/stderr 可重定向落盘、退出码透传、SIGINT/SIGTERM/SIGKILL 均能真实终止 Windows 进程、GUI 窗口在 Windows 桌面可见）。**但会弹模态窗口的程序会让调用方 bash 阻塞直到窗口关闭**（实测 `MessageBox` 令 bash 卡死 12 秒直至被 timeout 杀死，rc=124）。宿主正好属于这一类——它要么弹出 `倒卖可耻`、要么弹出 `VerificationDialog`，两者都需要人在场决定是否终止。所以宿主必须由人手动运行，以保留对那个窗口的控制权。

监控脚本相反：纯输出、无交互、可被 `timeout` 安全包裹，从 WSL 调起最省事。

**两处路径前提**（早先未写明，照抄命令会失败）：

- 仓库根 = `D:\03_Work\03_Develop\keysteam-unlock-spike`
- 样本工作区 = `D:\03_Work\03_Develop\KeySteam v2.99`

下述命令中 `host\host.exe` 是**相对路径**，隐含「已 cd 到仓库根」。`--dll` 指向的是**另一棵目录树**（样本工作区），必须给绝对路径。

**PowerShell 编码前提**：`monitor_keysteam.ps1` 含中文，**必须保存为 UTF-8 with BOM**。本机 PowerShell 5.1 的默认编码实测是 `gb2312`，会按 GBK 解码无 BOM 的 UTF-8 文件，导致中文注释被误解码后破坏引号配对、脚本无法解析。用编辑器改过该文件后务必确认 BOM 还在（`head -c 3 file | od -An -tx1` 应为 `ef bb bf`）。

---

## 紧循环观测（2026-09-15 新增，用于 `#7` 问题一）

### 先读这条：`timeout` 杀不掉宿主（实测踩坑）

**2026-09-15 实测事故**：用 `timeout 12 powershell.exe ... host.exe ...` 做开关验证，四条命令返回码都是 `0`、输出正常。但 `timeout` 只杀掉了 **PowerShell 调用方**，`host.exe` 本体存活了下来——**4 个宿主进程挂着 40 多分钟**，每个都带着一个 `KeySteam v2.99` 窗口。

这正是本文档 §「执行方式」里那条「宿主必须由人手动运行」的**同一原因**：宿主会弹模态窗口，任何外层超时机制都只能杀死调用方，杀不掉它。

**后果**（本次已核查，零破坏）：残留进程停在验证码弹窗（模态阻塞），未走到 `start_initialization`，所以样本 cleanup 未触发——插件目录 5 文件完好、数据目录 mtime 未变、主号目录无写入、原始样本哈希一致。**但这是运气，不是保证**：若残留进程越过了弹窗，它会杀 Steam、清插件目录。

**因此**：

- **不要用 `timeout` / `Start-Job` / 任何外层超时包裹宿主调用**，除非同时确认能终止 `host.exe`
- 监控脚本可以包（纯输出、无窗口）
- **每次运行前先查残留**：
  ```bash
  powershell.exe -NoProfile -Command "Get-Process host -ErrorAction SilentlyContinue | Select-Object Id,StartTime,MainWindowTitle"
  ```
  有输出就先 `Stop-Process -Force`，否则本次观测被污染

### 首次紧循环运行的判读（2026-09-15 12:26）

存档：`.scratch/run-20260915-122635/`（`findings.md` + 原始日志）

配置：全默认（`env:inject  third:dll path`），`-Seconds 60 -TightLoopMs -1`，实际 32 秒跑完 60 轮（约 533 ms/轮）。

```
12:26:49.239  进程出现: PID=28404 host
12:26:50.871  关键窗口: host 标题="KeySteam v2.99"                      （+1.63s）
12:26:51.427  [IP] 目标 IP 连接: Idle -> 162.14.69.140:443  TimeWait   （+2.19s）
```

**结论：分支 (a) 被排除——目标 IP `162.14.69.140:443` 确实被连接过。**

依据：监控从 `12:26:35` 起持续采样，若该连接早于 host 存在应更早被记；`TimeWait` 在 Windows 上存活约 120 秒（`TcpTimedWaitDelay` 默认），所以它在 `12:26:51` 被看到意味着建立于观测前不久，落在 host 存活期内。

**但 (b) 与 (c) 仍未区分**：日志记录的所有者是 `Idle`（PID 0）。这是 `TimeWait` 的已知行为——连接进入该状态后 `OwningProcess` 不再关联原进程。**无法据此断言是 `host` 建的连。**

### 本轮暴露的两个观测缺陷（已修）

**缺陷 1：弹窗被整个漏掉。**

用户确认验证码弹窗**出现过**并手动关闭，但日志无任何 `验证` 标题窗口。

根因：脚本用 `Get-Process | MainWindowTitle`，**每个进程只报一个主窗口**；验证码弹窗是同进程内的 Qt 模态对话框，不在其中。

对照上一轮 `EnumWindows` 采集的 `window-evidence.txt`，同一状态能同时抓到：

```
KeySteam 验证      Enabled=True    ← 模态弹窗
KeySteam v2.99     Enabled=False   ← 主窗口被禁用
```

**已修**：改用 `user32 EnumWindows`，日志新增 `类` 与 `启用` 字段。

**缺陷 2：`catch { }` 吞掉异常，伪装成「没有数据」。**

修复前窗口段整段抛异常却无提示（`窗口数=0`）。已改为记录 `WARN`。

**教训**：`catch {}` 让字段级错误伪装成「该现象不存在」。与本文档反复出现的错误同源——**缺失被当成了不存在**。

### 下一步（区分 b 与 c）

必须在连接**建立时**捕获，而非 `TimeWait` 残影：

1. 紧循环中记录连接建立事件（`Established` / `SynSent`）——那一刻 `OwningProcess` 仍有效
2. 目标 IP 检测与通用网络段**分离去重表**（当前共用 `$seenConns`，可能互相遮盖）
3. `pktmon` / ETW 抓连接建立（需提权）

### 目的

消除验证码弹窗触发链的三分支歧义——(a) 弹窗不需联网即可触发、(b) 联网发生了但短于采样间隔、(c) 联网走了别的进程。

### 为什么原来的采样率不够

**实测数据**（本机）：

```
Get-Process + Get-NetTCPConnection 一次完整采样 = 224 ms
```

原脚本用 `Start-Sleep -Milliseconds 500`，所以**每轮循环的真实周期 ≈ 724 ms**，而 `-Seconds` 的语义是**循环次数**、不是秒数（`for ($i = 0; $i -lt $Seconds; $i++)`）。

于是原 `-Seconds 600` 的实际时长 ≈ 434 秒，而样本从进程出现到弹窗只活 **2.09 秒**：

```
2.09 s / 0.724 s ≈ 2.9 个采样点
```

**这是对早先记录的更正**：此前的手续文档写「约 4 个采样点」，按实测周期应为 **≈ 3 个**，且其中只有 1 个可能落在弹窗之前。这个数字把「未捕捉到持续 ≥500ms 的外部连接」的归因能力进一步压低——**3 个采样点连一次稳态连接都不足以证实**。

### 三件对齐的判据

| 事件 | 前置观测 | 含义 |
| --- | --- | --- |
| **DNS 解析** | 运行前后 `Get-DnsClientCache` 差分 | 新增 `key.steamofl.com` 条目 ⇒ 本次运行发起过解析 |
| **TCP 连接** | 紧循环枚举到 `162.14.69.140` 的连接 | 出现 ⇒ 分支 (a) 排除 |
| **窗口时刻** | 紧循环枚举 `倒卖可耻` / `验证` 标题 | 出现时刻与上述事件的时间关系 |

`key.steamofl.com` 的当前解析值（实测）：**`162.14.69.140`**。

**为什么盯 IP 而不是域名**：`Get-NetTCPConnection` 只给 IP，不给主机名。因此判据是「连到该 IP」，无需依赖 DNS 时序。若该 IP 变化，重新解析：`Resolve-DnsName key.steamofl.com -QuickTimeout`。

**DNS 缓存没有查询时间戳**——字段只有 `Entry`/`Data`/`TTL`/`Status`。所以不能用「某个时刻缓存里有它」当判据，只能用**运行前快照 → 运行后快照的差集**。

### 分支判读表

| 观测结果 | 结论 | 后续 |
| --- | --- | --- |
| 连到 `162.14.69.140`，且早于弹窗 | 分支 (b) 或 (c)：弹窗需联网 | 需再区分进程归属 |
| 连到该 IP，但归属进程**不是** `host*` | 分支 (c)：走了别的进程 | 检查 `steamclient64.dll` 侧 |
| 无该 IP 连接，但 DNS 差集有该域名 | 解析了但未连接 | 倾向于 (a)，需看是否超时分支 |
| 无连接、无 DNS 差分 | 分支 (a)：弹窗不需联网 | 弹窗由本地状态触发，转查票据本地校验 |

### 脚本规格（`monitor_keysteam.ps1` 新增开关）

在现有 `param` 块内追加（**注释必须在 param 块之外**，否则破坏解析——已踩过）：

```powershell
[int]$TightLoopMs = 0,     # 0 = 沿用 Start-Sleep 500；>0 = 紧循环间隔（毫秒）
[string]$ResolveHost = "key.steamofl.com"   # 解析一次，用于取当前 IP
```

行为约定：

- `-TightLoopMs 0`（默认）⇒ **完全保持现有行为**，否则会污染已验证过的默认路径
- `-TightLoopMs -1` ⇒ 不 sleep，尽可能快（实测约 224 ms/轮）
- `-TightLoopMs N`（N>0）⇒ `Start-Sleep -Milliseconds N`

新增输出（沿用单一日志流 + 毫秒时间戳 + 事件前缀）：

```
[DNS] 解析 key.steamofl.com -> 162.14.69.140            ← 启动时一次
[DNS] 新增缓存条目: key.steamofl.com -> 162.14.69.140   ← 与运行前快照的差集
[IP]  目标 IP 连接: host -> 162.14.69.140:443  state=SynSent  ← 紧循环命中即报
```

现有前缀（`进程出现` / `网络连接` / `命名管道` / `!!! 关键窗口` / `插件被删除` / `!!! 主号目录…`）**不变**——它们已被既有判读逻辑依赖。

`W()` 函数已输出 `HH:mm:ss.fff`（毫秒），无需改动——**这是三件对齐能成立的前提**。

### 时长

**紧循环 60 秒足够**。理由：弹窗在 2.09 秒内出现，紧循环下 60 秒 ≈ 268 个采样点，相对原方案的 3 个是 90 倍密度，且日志不会撑爆磁盘（每轮最多几行，且有 `$seen*` 去重）。

**不要用 600**：紧循环跑满 434 秒会生成极大日志，且样本早已进入弹窗态、无新信息。

### 失败处置（每类失败的预设动作）

| 失败 | 判据 | 预设动作 |
| --- | --- | --- |
| `倒卖可耻` 窗口出现 | 日志含 `!!! 关键窗口` 且标题匹配 | **立即终止**（唯一按钮是「退出程序」，已无观测价值）。照旧 |
| 主号目录被写 | 日志含 `!!! 主号目录` | **立即终止**，恢复主号目录，记录时刻 |
| 插件目录被清 | 日志含 `插件被删除` | **不算失败**——这是样本 cleanup 的正常行为，记录时刻即可（它相对验证链的早晚有判读价值） |
| 脚本自身崩溃 | `monitor-stdout.txt` 有异常、日志无 `=== 监控结束 ===` | 保留现场，改用 `-TightLoopMs 0` 降级重跑 |
| 日志撑爆磁盘 | 日志 > 200 MB | 终止，缩短时长重跑 |
| 宿主持不返回 | `run_code` 正常路径不返回（`Py_Exit` 终结进程） | **不算失败**——这是预期状态，见「中止条件」 |
| 超时 | 60 秒紧循环结束而样本仍在 | 终止，关闭弹窗 |

**双条件中止仍然有效**：`倒卖可耻` 出现 / 超时上限。

### 一键恢复

`config/stplug-in/` 与数据目录在每次运行后都可能被改。恢复命令（幂等，可重复执行）：

```bash
cd /mnt/d/03_Work/03_Develop/keysteam-unlock-spike

# (a) 插件目录：从最新备份恢复，核对 5 个文件
BK=$(ls -d .scratch/stplug-in-backup-* | tail -1)
cp -a "$BK/." "/mnt/d/02_Games/01_Steam/Steam/config/stplug-in/"
ls -la "/mnt/d/02_Games/01_Steam/Steam/config/stplug-in"   # 期望 5 个文件

# (b) 数据目录：从 baseline 副本恢复，逐个核对 md5
cp _re/backup/Shikieiki_orig/{verification.cache,first_run.cache,shiki.json,shiki.kodo} \
   /mnt/c/Users/Hidriver/AppData/Roaming/Shikieiki/
md5sum /mnt/c/Users/Hidriver/AppData/Roaming/Shikieiki/*.cache \
       /mnt/c/Users/Hidriver/AppData/Roaming/Shikieiki/*.json \
       /mnt/c/Users/Hidriver/AppData/Roaming/Shikieiki/*.kodo
# 对照 _re/backup/BASELINE.txt
```

**恢复后必须核对**：`BASELINE.txt` 记有原始 md5。不一致说明恢复没成功，不要在此状态下跑下一次。

### 验证 envp 那条支线的读数限制（**已知，先写清楚**）

`#7` 的遗留疑问是「`NUITKA_ONEFILE_DIRECTORY` 注入是否生效」可当第三证据。本轮静态核实：

- 该变量**确实存在于 `main.dll`**（命中 1 次），但与 `compiled_module`、`__nuitka_binary_dir` 同属 **Nuitka C 运行时字符串池**（`0x181d1b910`，`.data` 区），**不是样本 Python 层代码的消费点**
- 样本真正读的是 **`NUITKA_ONEFILE_TEMP`**，消费点在 `src.utils.resources` 的 `candidate_resource_dirs`（"Return candidate directories that may contain bundled resources."）

**读数限制（关键）**：宿主 stdout/stderr **只含 `host.c` 自己的诊断行**。样本层的资源解析痕迹**不会出现在那里**。因此这一轮「跑一次看日志」**看不到该变量的消费读数**。

**要拿到读数，只有两条路**：
1. 观察资源**查找失败**的外部后果（异常 / 降级 / 窗口行为异常）——但按模块边界严格重判，`src.utils.resources` 段内 `write_text`/`write_bytes`/`mkdir`/`unlink` **全部零命中**，它只组装内存候选列表
2. 候选 C（`.pyd` 侧信道），代价是引入可检测面

**结论：第三证据这条路当前不产生读数。** 本轮运行会顺手验证这一点（若 60 秒紧循环日志里没有任何资源解析痕迹，即证实其不可观测），但不为它单开一次运行。

---

## 每次运行前（两次都一样）

```bash
# 0. 确认监控脚本 BOM 完好、语法可用
head -c 3 "/mnt/d/03_Work/03_Develop/KeySteam v2.99/_re/monitor_keysteam.ps1" | od -An -tx1   # 期望 ef bb bf
powershell.exe -NoProfile -Command "\$e=\$null;[System.Management.Automation.Language.Parser]::ParseFile('D:\03_Work\03_Develop\KeySteam v2.99\_re\monitor_keysteam.ps1',[ref]\$null,[ref]\$e)|Out-Null;if(\$e.Count -eq 0){'SYNTAX OK'}"

# 1. 重编宿主（不要相信仓库里的 host.exe —— 曾出现过与源码不同步的旧件）
cd "/mnt/d/03_Work/03_Develop/keysteam-unlock-spike" && bash host/build.sh

# 2. 恢复插件目录（样本会清理它；两次运行前都做，保证初始状态一致）
TS=$(date +%Y%m%d-%H%M%S)
DEST=".scratch/run-$TS"
mkdir -p "$DEST"
cp -a .scratch/stplug-in-backup-*/.. "$DEST/" 2>/dev/null || true
cp -a "/mnt/d/02_Games/01_Steam/Steam/config/stplug-in/." "$DEST/stplug-in-initial-snapshot/"
ls -la "$DEST/stplug-in-initial-snapshot"   # 期望 5 个文件

# 3. 记录起始时间（事后核对主号目录是否被写要用）
date '+%Y-%m-%d %H:%M:%S' | tee "$DEST/start-time.txt"

# 4. 确认 Steam 状态（每次运行前都手动退 Steam、重启、登录小号 drivpe114514）
reg.exe query "HKCU\Software\Valve\Steam\ActiveProcess" /v ActiveUser
# 期望：ActiveUser 非 0x0（登录后由 steam.exe 写入）。若仍是 0x0，
# 样本会走「Steam 当前没有已登录用户」分支，本次运行的账号路径不可用于判读。
```

**第 4 步不能跳过**：两次运行之间若 Steam 登录状态不同，第 2 次就多一个未受控变量，而本方案的整个判读逻辑建立在「两次只差缓存这一个变量」之上。

---

## 第 1 次运行：保留缓存

### 步骤

1. **先启动监控**（顺序不可颠倒；弹窗是模态的，失败态只能退出，先看再跑才拿得到数据）。日志直接写进本次运行的存档目录：
   ```bash
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File \
     "D:\03_Work\03_Develop\KeySteam v2.99\_re\monitor_keysteam.ps1" \
     -Seconds 600 -LogDir "D:\03_Work\03_Develop\keysteam-unlock-spike\.scratch\run-<TS>" \
     > "/mnt/d/03_Work/03_Develop/keysteam-unlock-spike/.scratch/run-<TS>/monitor-stdout.txt" 2>&1 &
   ```
   监控记录：观察名单内的进程、命名管道、样本相关网络连接、关键窗口标题、数据目录变化、**插件目录变化（含删除）**、**主号目录写入**。

2. **在监控运行期间**，在 Windows 终端手动启动宿主：
   ```
   cd /d D:\03_Work\03_Develop\keysteam-unlock-spike
   host\host.exe --dll "D:\03_Work\03_Develop\KeySteam v2.99\_re\work\payload\main.dll"
   ```
   把 stdout 与 stderr 记入 `.scratch\run-<TS>\host-stdout.txt`（在 Windows 终端用 `2> file.txt` 或复制粘贴全量输出）。

3. 记录退出码。**注意**：正常路径下宿主不返回（见下），所以「没有退出码」是预期状态。

4. 若出现 `倒卖可耻` 窗口：**立即终止**，记录窗口出现的时刻（监控日志里有时间戳），然后关闭窗口（唯一按钮是「退出程序」）。

### 本次要观测的

| 观测项 | 判读 |
|---|---|
| `[host] dll = ...` / `payload = ...` | 路径推导是否符合预期 |
| `[host] switches = env:...  third:...` | 两个开关的独立状态；`third:NULL (control run)` 仅 `--null-3rd` 时出现 |
| `[host] argc = N` 与逐条 `argv[i]` | argv 构造；**`argv[0]` 必须以 `.py` 结尾**，这是本方案的载荷 |
| `[host] run_code @ 0x...` | 非 NULL ⇒ `GetProcAddress` 成功，「已知阻碍 1」被证伪 |
| `keysteam-runtime-guard` 进程 | 出现/不出现 |
| `\\.\pipe\keysteam_guard_` | 出现/不出现 |
| 出站连接 | 清单（监控已按进程过滤，只记观察名单内的） |
| **标题 `倒卖可耻` 的窗口** | **出现 ⇒ 完整性链被触发**。但**不立即判失败**——见下方「为什么不再把出现等同于失败」 |
| `VerificationDialog`（无 × 的弹窗） | 记录，但**只作环境状态**——见下方归因限制 |
| `config/stplug-in/` 目录变化 | 样本的清理逻辑是否触发（会删 `*.lua`/`*.ks`）。**记录删除发生的时刻**，它相对验证链早晚有判读价值 |
| `userdata/1398488476/` 是否被写 | 主号保护的实际验证（预期：不写）。若出现 `!!! 主号目录…` 行，立即终止 |

### 为什么不再把 `倒卖可耻` 出现等同于失败（2026-09-15 修正）

早先的判据是「出现 ⇒ argv 方案失败」。这**压掉了一条可能性**：该窗口只能确定「完整性问题被检测到」，不能确定是哪条检测链触发。`domain.md` 已记载 `main.dll` 的完整性走的是**远程清单分支加进程模块扫描**，不止一条路——argv 方案可能已生效，却触发了另一条检测。

因此本次运行要记录的**不只是窗口有无，还有它出现的时刻与前后事件序列**（进程出现、管道创建、日志写入的先后）。这样「哪条链触发」才有机会从猜测变成证据。成本几乎为零，而它能区分两种后果完全不同的情形。

### 一个**不可达**的观测项（2026-09-15 修正）

早先本表把 `[host] run_code returned N` 列为判据，写着「出现 ⇒ 调用完成，第二个已知阻碍被证伪」。**这一项在正常路径下永远不出现。**

证据（Nuitka 上游源码）：

```
MainProgram.c:2402   return Nuitka_Main(argc, argv);        ← run_code 无条件转发
MainProgram.c:2325   EXECUTE_MAIN_MODULE(...)               ← 用户代码在此执行
MainProgram.c:2355   Py_Exit(exit_code)                     ← 进程在此终止
```

`run_code` 正常路径**不返回**——`Py_Exit` 直接终结整个进程。所以 `host.c` 末尾的 `return status`（重导：`grep -n 'return status' host/host.c`）与那行 `[host] run_code returned N` 只在**异常路径**可见。看到它，说明出事了，不是说明成功了。

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

1. **先恢复被第 1 次运行改变的一切**，让两次之间只剩缓存这一个变量：

   ```bash
   # (a) 恢复插件目录（第 1 次运行很可能已清空它）
   cp -a .scratch/stplug-in-backup-*/.. "/mnt/d/02_Games/01_Steam/Steam/config/stplug-in/"
   ls -la "/mnt/d/02_Games/01_Steam/Steam/config/stplug-in"   # 期望 5 个文件

   # (b) 手动退 Steam → 重启 → 登录小号 drivpe114514（在 Windows 侧操作，不在 bash 里）
   #     然后确认 ActiveUser 已非 0
   reg.exe query "HKCU\Software\Valve\Steam\ActiveProcess" /v ActiveUser
   ```

2. 备份并移走缓存（备份已在 `_re/backup/Shikieiki_orig/`，此步可逆）：
   ```bash
   mv /mnt/c/Users/Hidriver/AppData/Roaming/Shikieiki/verification.cache \
      /tmp/verification.cache.removed-$(date +%s)
   ```

3. 重复第 1 次运行的监控与启动步骤（含监控脚本的 `-LogDir` 指向本次的 `.scratch/run-<TS2>/`）。

4. 观测同一张表。

### 本次的判读

票据缺失是**已知且预期**的状态：

- `VerificationDialog` 必然出现——**这是预期行为，不是失败**。
- `倒卖可耻` 若仍不出现 ⇒ 完整性链被跳过的**正向证据**（本次已排除票据链的干扰）。
- `verification.cache` 是否被**新建**：若程序在验证未通过时不写缓存，则该文件应保持缺失；若被创建，说明程序在无票据状态下也落了盘，需要记录。

**本次的判读仍受两条限制**（与第 1 次相同）：

- `倒卖可耻` 出现时，记录**时刻与事件序列**，不要直接判「argv 方案失败」——见第 1 次运行章节的说明。
- 宿主侧看不到后缀判定的任何中间态，只能靠最终弹窗反推。

---

## 变量对照表（两次运行的差异）

**判读逻辑的前提：两次之间只有 `verification.cache` 一个变量不同。** 任何其他差异都会污染归因。因此每次运行前都要把下列状态恢复一致（见「每次运行前」一节）。

| 变量 | 第 1 次 | 第 2 次 | 必须一致的？ |
|---|---|---|---|
| `verification.cache` | 存在（2026-09-13 20:26，605 B） | 移除 | **否——这是要变的变量** |
| `first_run.cache` | 存在（2026-09-12 13:49，63 B） | 不变（首运行弹窗应不出现，这是范围边界） | 是 |
| Steam 登录状态 | 手动启动并登录小号 `drivpe114514` | **同样手动启动并登录小号** | **是（2026-09-15 追加）** |
| `config/stplug-in/` 内容 | 5 个脚本（跑前从备份恢复） | **跑前同样从备份恢复** | **是（2026-09-15 追加）** |
| `--no-envp` / `--null-3rd` | 都不用（env 注入，第三参数传路径） | 都不用 | 是 |

后两项是 2026-09-15 追加的一致性要求，各有依据：

- **Steam 登录状态**：样本的账号解析读 `HKCU\Software\Valve\Steam\ActiveProcess\ActiveUser`（实测当前 `0x0`）。这个值由 `steam.exe` 登录后写入；Steam 不在运行或未登录时它可能保持 `0x0`，样本会走「Steam 当前没有已登录用户」分支并弹窗。若两次运行的 Steam 状态不同，第 2 次就多一个未受控变量。
- **`config/stplug-in/` 内容**：该目录的内容影响样本初始化路径（脚本对应 appid 的入库状态）。第 1 次跑完后样本可能已清空该目录；若第 2 次带着空目录跑，两次初始状态就不一致。成本是一行 `cp -a`。

两处「追加」的实测依据：第 1 次运行后样本会 `terminate_all` 杀 Steam 并清理插件目录（静态确证），所以这两项**必然**被第 1 次运行改变，不主动恢复就一定会出现第二个变量。

两次都传 `main.dll` 的绝对路径作为第三参数。

### 开关已拆分（2026-09-15 修复，`#7` 问题三）

**旧形态（已废弃）**：两个变量绑在同一个标志上。

```c
const wchar_t *third = use_envp ? dll_path : NULL;
...
if (use_envp) { SetEnvironmentVariableW(...); ... }
```

`--no-envp` **同时**关掉第三参数与两个环境变量注入，跑出来是**复合差异**而非单变量对照。这也阻塞了 `#4` 评论提出的「第三证据」（观测 `NUITKA_ONEFILE_DIRECTORY` 注入是否生效）——要观测 env 注入就必须跑 `use_envp=1` 那一路，而那一路上第三参数也同时被传了。

**现形态**：两个独立开关。

```c
int inject_env = 1;   /* default: set the two NUITKA_* variables */
int pass_third = 1;   /* default: third argument = absolute dll path */
...
const wchar_t *third = pass_third ? dll_path : NULL;
```

| 开关 | 作用 |
| --- | --- |
| `--no-envp` | **仅**跳过 `NUITKA_ONEFILE_DIRECTORY` / `NUITKA_ORIGINAL_ARGV0` 注入 |
| `--null-3rd` | **仅**把第三参数从 `main.dll` 路径变为 `NULL` |

四种组合已实测（重导：`grep -n 'inject_env\|pass_third' host/host.c`）：

| 命令行 | banner | `run_code` 的第三参数 |
| --- | --- | --- |
| 无 | `env:inject  third:dll path` | 完整路径 |
| `--no-envp` | `env:skip  third:dll path` | 完整路径 ← 不再连带置 NULL |
| `--null-3rd` | `env:inject  third:NULL (control run)` | `NULL` |
| 两者 | `env:skip  third:NULL (control run)` | `NULL` |

现在可以做真正的单变量对照：先跑基线，再**只**加一个开关。

**仍未解决的前置疑问**：`NUITKA_ONEFILE_DIRECTORY` 在 Nuitka 的 `MainProgram.c` 中**完全不出现**（只在 `OnefileBootstrap.c` 语境使用）。本宿主**不是** onefile bootstrap，而是直接加载 dll。所以该环境变量对本样本**可能根本没有消费点**——若真如此，观测它得不到读数。**开关已就绪，但在跑之前应先确证样本是否真的读取该变量**，否则只是把「跑不动」换成了「跑了没读数」。


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

## 运行历史与已验证项（2026-09-15 更新）

`host.exe` **已运行过两次**（首次失败、修复后成功）。证据存档：`.scratch/run1-err87-20260915-103403/`（错误 87）、`.scratch/run-20260915-104640/`（成功）。

| 项 | 状态 |
|---|---|
| `LoadLibraryExW` 是否真的成功 | **已验证**（修复全限定路径后）。首次失败 = 错误码 **87**，成因见 `#7` / 交接文档 §2.1 |
| `GetProcAddress` 是否真的返回非 NULL | **已验证**——`run_code @ 00007FFDF89FB380`。「已知阻碍 1」未复现 |
| 第三参数（`main.dll` 路径）是否被正确消费 | **已验证**——模块列表显示 `python312.dll` 等从 payload 目录解析 |
| 三个环境变量/参数开关的独立性 | **已验证**——四种组合实测见「开关已拆分」一节 |
| `pyinit_core_reconfigure: failed to read thread state` | **未复现**——「已知阻碍 2」 |
| `argv[0]` 的 `.py` 后缀是否真的触发源码运行分支 | **仍未确证**，且**结构性不可观测**（见 `docs/integrity-runtime-observability.md` §5）。只能靠最终弹窗反推，而归因能力弱 |
| 验证码弹窗是否消失 | **未消失**——`#1` 的原始目标**仍未达成** |

宿主自身的错误路径：`2`（用法/内存）与 `3`（`LoadLibraryExW` 失败）**已实测触发**；`4`（`GetProcAddress` 失败）**未触发**。

**注意**：`run_code` 正常路径不返回（`Py_Exit` 终结进程），所以「程序跑起来了但宿主没退出」不是挂起，是正常。判读见「中止条件」。

