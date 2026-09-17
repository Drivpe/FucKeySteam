# 提权运行说明

后续工单的验收需要跑样本（Windows 侧、需提权）。本文件说明如何让**非提权会话**触发提权探针。

## ✅ 已完成安装（2026-09-17）

任务 `KS_Elevated_Probe` **已注册并端到端验证通过**：

```
任务名:   KS_Elevated_Probe
状态:     Ready
运行身份: Hidriver
运行级别: Highest
动作:     ...\pwsh.exe
参数:     -NoProfile -NoLogo -NonInteractive -ExecutionPolicy Bypass -File "....\ks_elevated_run.ps1"
```

**端到端验证结果**（非提权会话触发、提权运行）：`_elev_run.log` 记录 `elevated=True`、退出码 0、耗时 40.15s；探针日志第 3 行 `priv=True`；`hwbp_ctrl` 命中 **423213** 次。**提权自动化成立。**

## 之后的用法（不再需要任何权限）

> **⚠ 关键：把三步放进同一条命令**
>
> 实测教训（2026-09-17，工单 08）：若在 `mv` 与触发之间隔一次 WSL→Windows 调用，
> 任务启动可能有**约 90 秒延迟**，期间另一个调用方会覆盖 `_elev_job.pending`，
> 导致你的运行被顶替。**一次实际发生过**（日志显示 `probe=mydbg3` 而非自己的探针）。
>
> **缓解方法**：把「写文件 + 重命名 + 触发」放进**同一条 `pwsh.exe -Command`**。
> 工单 08 用此法后，后续 5 次触发全部一次成功。

```powershell
# ✅ 推荐：一条命令完成，无窗口
pwsh.exe -NoProfile -Command @"
Set-Content -Path 'D:\03_Work\03_Develop\KeySteam v2.99\_re\ghidra\_elev_job_<你的id>.txt' -Value @('hwbp_ctrl','tag1') -Encoding ascii
Move-Item -Force 'D:\03_Work\03_Develop\KeySteam v2.99\_re\ghidra\_elev_job_<你的id>.txt' 'D:\03_Work\03_Develop\KeySteam v2.99\_re\ghidra\_elev_job.pending'
Remove-Item -Force -ErrorAction SilentlyContinue 'D:\03_Work\03_Develop\KeySteam v2.99\_re\ghidra\_elev_run.log'
Start-ScheduledTask -TaskName 'KS_Elevated_Probe'
"@
```

```bash
# ❌ 反面例子：三步分开发，中间有窗口——曾导致运行被顶替
printf 'zd_dlg\r\npre\r\n' > _elev_job_agent03.txt    # 在 WSL 里
mv _elev_job_agent03.txt _elev_job.pending            # 在 WSL 里
pwsh.exe -NoProfile -Command "Start-ScheduledTask ..." # 另一次调用
```

结果落在两个地方：

- `_elev_run.log` —— 执行器汇总（时间戳、退出码、耗时、残留进程警告）
- 探针自己的日志（如 `hwbpCtrl_q1.txt`）—— 照常由探针写

**读日志时必须核对 `RUN probe=` 行**，确认跑的是你自己的探针；不是就重跑。

## 原始的一次性安装步骤（已执行，留作记录）

**以管理员身份运行**：

```
右键 REGISTER_ELEVATED_TASK.ps1 → 以管理员身份运行
```

或在管理员身份的 PowerShell 7 里：

```powershell
pwsh -File "D:\03_Work\03_Develop\KeySteam v2.99\_re\ghidra\REGISTER_ELEVATED_TASK.ps1" -Probe hwbp_ctrl
```

脚本会自我验证：注册后回查任务、打印状态与运行级别，确认 `RunLevel=Highest` 才算成功。

**为什么必须手动做这一步**：任务注册本身需要管理员，而当时的会话令牌是非提升的（`Hidriver` 在 `Administrators` 组内，但 UAC 分离令牌下 `IsAdmin=False`）。这是先有鸡还是先有蛋——要建提权任务，得先提权。详见 `materials.md` §9 的实测记录。**注册之后，这一步不再需要重复。**

## 三个必须知道的约束

**其一：探针要求交互式桌面。** 任务以 `LogonType Interactive` 注册，只在**当前用户已登录**时可用。这是有意的——探针要能看见窗口才能观测弹窗，跑在无桌面的会话里观测不到。

**其二：非提权运行会产生误导性结果。** 非提权下样本会在约 2 秒后崩于 `0xc0000005`（空指针），日志看起来"跑了但没结果"。执行器因此带**提权闸**：非提权时立即退出（退出码 1），不做任何事。**不要绕过它。**

**其三：`_elev_run.log` 是共享的。** 多个并发运行会写同一个文件。触发前先清、跑完立刻读，并核对时间戳。

**其四：探针耗时差异极大，不要凭时间判断「挂住」。** 实测超时范围 **35 秒到 300 秒**（跨度近 9 倍）：

- 最短：`zd_data` 35s、`hwbp*` 40s
- 最长：`mydbg4` 300s、`mydbg2/3/5/6` 180–240s

`mydbg3.py` 实测耗时 **240.11 秒**、退出码 0——曾因此被误判为「挂住」。

**判断是否还在跑的可靠方法**（不要靠时间猜）：

```bash
# 任务状态：Running / Ready
pwsh.exe -NoProfile -Command "(Get-ScheduledTask -TaskName 'KS_Elevated_Probe').State"

# 日志：有 EXIT 行 = 已结束，无论耗时多久
cat _elev_run.log
```

**有 `EXIT` 行 = 已正常结束。** 若 State=Running 但 `kshost`/`python` 进程都不存在了，那才是真挂了。

## 执行器的既有检查

`ks_elevated_run.ps1` 在运行前会查 `Get-Process kshost,host,KeySteam`，发现残留进程时打警告并记进日志。这是本仓库的既有纪律（残留 host 会占住模态窗口，导致后续观测失真）。

## 为什么用 PowerShell 7 而不是 cmd

前一轮实测：cmd 版需要**纯 ASCII + CRLF**（该目录的既有约定），且 `schtasks /TR` 的**参数转义不可靠**——路径含空格时（本目录路径含 `KeySteam v2.99`）实测失败。pwsh 解决了全部三点：不吃行尾格式、原生 UTF-8、参数结构化传递。

脚本经 `Parser::ParseFile` 静态语法检查通过；执行器在非提权下正确拒绝并返回退出码 1。

## 与工单的关系

- **工单 03/04/05/06 的验收**（日志对拍）依赖这套机制 —— **已解锁**
- **工单 08**（分离零命中解释）同样依赖 —— **已解锁**
- **工单 01 已完成**，不需它
- **工单 02 已完成**，不需它
