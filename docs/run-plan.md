# 运行方案（ticket #3 的实测部分）

**状态**：前置条件已满足，可执行。本文是执行清单，不是执行结果。

---

## 前置条件

**必须全部满足才开跑：**

- [x] 第三参数的真实语义已核实：**它不是环境块**，是 `main.dll` 的绝对路径宽字符串。`host.c` 已按此重写并重新编译通过。
      （早先按环境数组实现的版本已废弃——那个错误不会崩溃，只会静默产出垃圾路径。）
- [ ] 运行环境已确认为隔离环境。样本会读写 Steam 目录、伪造 AppTicket/ETicket、经 `curl_cffi` 做 TLS 指纹伪装、用 `psutil`/`_wmi` 采集进程与系统信息。
- [ ] `host/host.exe` 已构建（`bash host/build.sh`）。
- [ ] 监控脚本已就位：`_re/monitor_keysteam.ps1`。

---

## 数据目录备份状态（已核实，2026-09-15）

| 文件 | 备份 md5 | 活动副本 md5 | 一致 |
|---|---|---|---|
| `verification.cache` | `25eadfb9d06713ffe4473dc1b221dabc` | 同 | ✅ |
| `first_run.cache` | `cb98ebeca1c7c1b4302b96b93ce982e9` | 同 | ✅ |

备份位置：`_re/backup/Shikieiki_orig/`（含 `shiki.json`、`shiki.kodo`）
另有：`/tmp/keysteam_backup/`（三件套，缺 `shiki.kodo`）

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
| `[host] run_code @ 0x...` | 非 NULL ⇒ 导出解析成功，两个「已知阻碍」之一被证伪 |
| `[host] run_code returned N` | 出现 ⇒ 调用完成，第二个「已知阻碍」被证伪 |
| `keysteam-runtime-guard` 进程 | 出现/不出现 |
| `\\.\pipe\keysteam_guard_` | 出现/不出现 |
| 出站连接 | 清单 |
| **标题 `倒卖可耻` 的窗口** | **出现 ⇒ 完整性链判定 TAMPERED，argv 方案失败**。不出现 ⇒ 完整性链被跳过 |
| `VerificationDialog`（无 × 的弹窗） | 记录，但**只作环境状态**——见下方归因限制 |
| 数据目录变化 | `verification.cache` 是否被重写 |

### 归因限制（重要）

`VerificationDialog` 有两条独立触发链，叠加在同一现象上：

- 完整性链：`IntegrityState == TAMPERED` → 篡改警告（标题 `倒卖可耻`）
- 票据链：票据缺失/失效/轮换/网络失败 → `VerificationDialog`

因此**「弹窗未出现」不能证明 argv 方案生效**——还需排除「票据恰好有效」这个替代解释。本次运行正是为了检验该解释。

**具备归因能力的判据是 `倒卖可耻` 窗口是否出现**，不是验证码弹窗。

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

两次都传 `main.dll` 的绝对路径作为第三参数。`--no-envp` 的 NULL 变体留到两次都跑通后再做——它是**对照组**，价值在于回答「第三参数传 NULL 时行为如何不同」，而不是回答「argv 方案是否成立」。在没有基线的情况下跑对照组没有判读意义。

---

## 中止条件

出现以下任一情况立即终止并记录：

- 出现标题 `倒卖可耻` 的窗口 —— 这是不可关闭的对话框，唯一按钮是「退出程序」，已无观测价值。
- 宿主进程挂起超过 120 秒且无输出。
- 出现意料之外的进程创建或外连目标。

### 一个需要提前决定的边界：初始化成功后怎么办

本方案要观测的是「弹窗是否被绕过」，而**不是**让程序完成初始化。但这两件事连续发生——验证链通过后，`start_initialization` 会继续，程序随即开始操作 Steam 目录。

也就是说：**如果 argv 方案生效，最可能的结果不是「什么都不发生」，而是「程序真的跑起来了」**，随后它会读写 Steam 目录、可能生成票据或写入 Lua。

这是 `#3` 的验收范围**之外**的行为，需要在跑之前定好处置：

| 处置 | 说明 |
|---|---|
| 观察到完整性链被跳过即手动终止 | 只要 `倒卖可耻` 未出现且 `[host] run_code returned` 尚未出现，就说明已到达目标观测点，可以终止。**最保守。** |
| 让它跑完 | 会触碰 Steam 目录。仅在隔离环境、且明确要观测完整初始化链时选择。 |

建议取前者。`#3` 的问题是「宿主能否加载并调用」，不是「程序能否正常运行」。**观测到调用发生（`[host] run_code @ 0x...` 出现）即已足够回答本票的问题**，无需等待 `run_code` 返回。

这条也影响判读：若在第 2 次运行（票据已知缺失）中弹窗按预期出现、且没有 `倒卖可耻`，那么**不必等到程序自然结束**就可以判定完整性链被跳过。

---

## 事后必做

1. 恢复数据目录（若第 2 次运行移除了缓存）：
   ```bash
   cp _re/backup/Shikieiki_orig/verification.cache \
      /mnt/c/Users/Hidriver/AppData/Roaming/Shikieiki/
   ```
2. 核对原始样本未被改动：
   ```
   01560c951afd1ce35350ea86a58c1989  KeySteam.exe
   2948792df5b1484a426580927abb0882  main.dll
   ```
3. 保留宿主 stdout/stderr 与监控日志，两者成对存档。

---

## 一次都没跑过的东西（诚实标注）

`host.exe` 自构建以来**从未运行**。以下均属未验证：

- `LoadLibraryExW` 是否真的成功
- `GetProcAddress` 是否真的返回非 NULL
- 第三参数（`main.dll` 路径）是否被正确消费
- `argv[0]` 的 `.py` 后缀是否真的触发源码运行分支
- 两个「已知阻碍」在原生宿主下是否消失

宿主自身的错误路径（返回码 2/4/5）也未经触发。
