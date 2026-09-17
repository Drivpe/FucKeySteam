# 提权运行说明

后续工单的验收需要跑样本（Windows 侧、需提权）。本文件说明如何让**非提权会话**触发提权探针。

## 一次性安装（需要你手动做一次）

**以管理员身份运行**，任选其一：

```
右键 REGISTER_ELEVATED_TASK.ps1 → 以管理员身份运行
```

或在管理员身份的 PowerShell 7 里：

```powershell
pwsh -File "D:\03_Work\03_Develop\KeySteam v2.99\_re\ghidra\REGISTER_ELEVATED_TASK.ps1" -Probe hwbp_ctrl
```

脚本会自我验证：注册后回查任务、打印状态与运行级别，确认 `RunLevel=Highest` 才算成功。

**为什么必须手动**：任务注册本身需要管理员，而当前会话的令牌是非提升的（`Hidriver` 在 `Administrators` 组内，但 UAC 分离令牌下 `IsAdmin=False`）。这是先有鸡还是先有蛋——要建提权任务，得先提权。详见 `materials.md` §9 的实测记录。

## 之后的用法（不再需要任何权限）

```powershell
# 1. 指定本次要跑的探针（探针名不含扩展名，第二行是日志 tag）
Set-Content -Path "D:\03_Work\03_Develop\KeySteam v2.99\_re\ghidra\_elev_job.txt" `
            -Value @('hwbp_ctrl','q1') -Encoding ascii

# 2. 触发
Start-ScheduledTask -TaskName KS_Elevated_Probe
# 或
schtasks /Run /TN KS_Elevated_Probe
```

结果落在两个地方：

- `_elev_run.log` —— 执行器汇总（时间戳、退出码、耗时、残留进程警告）
- 探针自己的日志（如 `hwbpCtrl_q1.txt`）—— 照常由探针写

## 两个必须知道的约束

**其一：探针要求交互式桌面。** 任务以 `LogonType Interactive` 注册，只在**当前用户已登录**时可用。这是有意的——探针要能看见窗口才能观测弹窗，跑在无桌面的会话里观测不到。

**其二：非提权运行会产生误导性结果。** 非提权下样本会在约 2 秒后崩于 `0xc0000005`（空指针），日志看起来"跑了但没结果"。执行器因此带**提权闸**：非提权时立即退出（退出码 1），不做任何事。**不要绕过它。**

## 执行器的既有检查

`ks_elevated_run.ps1` 在运行前会查 `Get-Process kshost,host,KeySteam`，发现残留进程时打警告并记进日志。这是本仓库的既有纪律（残留 host 会占住模态窗口，导致后续观测失真）。

## 为什么用 PowerShell 7 而不是 cmd

前一轮实测：cmd 版需要**纯 ASCII + CRLF**（该目录的既有约定），且 `schtasks /TR` 的**参数转义不可靠**——路径含空格时（本目录路径含 `KeySteam v2.99`）实测失败。pwsh 解决了全部三点：不吃行尾格式、原生 UTF-8、参数结构化传递。

脚本经 `Parser::ParseFile` 静态语法检查通过；执行器在非提权下正确拒绝并返回退出码 1。

## 与工单的关系

- **工单 03/04/05/06 的验收**（日志对拍）依赖这套机制
- **工单 01** 不需要它（纯静态查证 + Linux 侧位运算推演）
- **工单 02** 不需要它（只改库、不跑样本）

即：**安装可以在 02 进行的同时做，但必须在 03–06 开始前完成。**
