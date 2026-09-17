# Spec 状态登记（离线）

**用途**：`/to-spec` 的正常收尾动作是「publish 到 issue tracker + 打 `ready-for-agent` 标签」。
本仓库的 issue tracker 是 GitHub（`Drivpe/keysteam-unlock-spike`），**当前不可达**（原因见下），
故标签与发布状态在此离线登记。GitHub 恢复后应照此补打。

## 处置

| 项 | 状态 |
| --- | --- |
| Spec 文件 | `.scratch/probe-arch-refactor/spec.md`（已产出） |
| 工单 | `.scratch/probe-arch-refactor/issues/`（**7 票**，已产出，本地） |
| 目标标签 | **`ready-for-agent`** |
| 发布状态 | **未发布**（GitHub 不可达） |
| 待办 | GitHub 恢复后：建 issue、贴 spec 正文、打 `ready-for-agent`、按 `docs/agents/issue-tracker.md` 的 `gh api` 方式操作；7 票按依赖顺序建 issue 并用原生依赖关系连边 |
| 前置已完成 | `_re/ghidra/` 版本控制基线（`f16252b`，217 文件）+ 本地裸仓备份 |

## 工单依赖图

7 票已落 `.scratch/probe-arch-refactor/issues/`。序列是 **expand–contract**——`probe_lib` 的迁移是机械改造、爆炸半径大（35 个脚本），不适用垂直切片。

```
01 (独立·最先执行)     02 (expand) ─┬─→ 03  L()        35 份·零风险
                                   ├─→ 04  rpm()       7 份·零风险
                                   ├─→ 05  set_hwbp()  3 份·参数化
                                   │        └─→ 06  read_pystr() 3 份·⚠ 唯一行为变更
                                   └───────────────────────────→ 07 (contract)
```

**编号即取活顺序**（本仓库的 frontier 规则是「first in map order wins」）。

**Frontier（可立即开工）：** `01`、`02`。

**`01` 排在最前**——它无依赖，且查证 `Dr7` 的 GD 位缺陷是否使 `hwbp_data.py` 的断点从未生效。若成立，既有实验结论需重新审视，重构的前提可能要重估。它与重构完全独立，但应最先做。

**`06` 是唯一含行为变更的票**（统一 `read_pystr` 的两版），已与机械迁移隔离，须单独验收。

## 执行进度

| 票 | 状态 | 备注 |
| --- | --- | --- |
| `01` 查证 Dr7 缺陷影响 | ✅ **已完成** | 子代理 `1d8269a1`；结论推翻原前提、影响面为零；暴露新缺口 → 已开 `08` |
| `02` probe_lib 补四个函数 | ✅ **已完成** | 子代理 `8d8ee55c`；提交 `bfce6b7`（+307 行、零脚本改动）；866 断言全绿 |
| `03`–`06` | ⏸ **受阻** | 需跑样本做日志对拍 → **提权任务未注册** |
| `07` contract 收尾 | 待 `03`–`06` | — |
| `08` 分离零命中解释 | ⏸ **受阻** | 同样需 Windows 实测（Q1/Q2 两个最小实验） |

## 当前唯一阻塞：提权任务未注册

`03`–`06` 的验收是「日志与迁移前逐行对拍」，这需要**真实运行探针**（Windows + 提权）。`08` 的两个实验同样需要。

机制已就绪并验证，但**注册必须你做一次**（实测：非提升会话创建最高权限任务被 ACL 拒绝，UAC 在 Secure Desktop 上自动化点不到）：

```
右键 REGISTER_ELEVATED_TASK.ps1 → 以管理员身份运行
```

脚本自我验证（回查任务、确认 `RunLevel=Highest`），成功才输出 `[完成]`。用法见 `ELEVATION-HOWTO.md`。

**未注册前可以做的**：`03`–`06` 的**代码改造**部分（把各脚本的旧定义删掉、改为 import 库）——只是**验收对拍**做不了。但不建议在无对拍的情况下推进：那等于改了却不知道有没有改坏，而这几票的价值正是「可验证」。

## 本轮两票的结论摘要

**`01` 推翻了工单与 ADR 0002 的一条前提**：GD 位（bit13）被 `& ~0xFFFFFFFF` 掩码顺带抹掉（实测 `0x2000 & 0xFFFFFFFF = 0x2000`），所以它是**结构性空假设**，不是设错的值——「GD=0 使 DR7 写入不生效」这条因果链在本代码里造不出来。既有结论全部不受波及（三份 `docs/` 零处引用 hwbp）。**ADR 0002 的决策不变**，仅精化了缺陷 2 的表述（不是独立缺陷，而是缺陷 1 的后果）。

**但 `01` 暴露了一个真缺口 → `08`**：`hwbp_data.py` 的历史日志 **0 命中**（327/313 字节，汇总段写明 `命中总数: 0`），而它有三条未分离的活解释，其中「**写断点编码根本没设上**」不可排除——**该目录不存在写断点的正对照**。加重证据（本次核实）：三个 hwbp 脚本**都不记录设断点成功/失败**，`hwbp_ctrl`/`hwbp16b` 靠大量命中反证机制有效，`hwbp_data` 因 0 命中**没有任何反证**。

**`02` 交付**：`probe_lib.py` 167 → 471 行。纯计算段（`parse_dr7` / `parse_pystr_bytes` / `construct_dr7_words`）可在 Linux 侧**裸 import**（实测量：`_WINDOWS=False`、逐位对拍正确），系统调用段（`make_L` / `rpm` / `read_pystr` / `set_hwbp`）接受依赖注入。**零脚本被改**（`git diff --name-only cb04c2e HEAD -- '*.py'` 过滤后为 0）。对拍 866 断言全绿，**已独立复现**。

## 提权机制（已就绪，待你注册）

`03`–`06` 的日志对拍需要跑样本，而跑样本需提权。机制已实现并验证：

- `REGISTER_ELEVATED_TASK.ps1` —— 一次性注册（**需你手动以管理员运行**）
- `ks_elevated_run.ps1` —— 执行器，带提权闸，非提权时拒绝（退出码 1）
- 用法与约束见 `ELEVATION-HOWTO.md`

两脚本已提交（`cb04c2e`），经语法检查与行为验证。

**安装时机**：`02` 进行中即可安装，但必须在 `03` 开始前完成。

## 已完成的离线替代动作

**`_re/ghidra/` 版本控制基线**（spec 的第一个 User Story，通常不需要 tracker 即可执行）：

- 独立仓建在 `_re/ghidra/`，分支 `master`，初始提交 `f16252b`
- 217 文件 / 784K（源目录 935M，压缩到 0.08%）
- 备份：本地裸仓 `_re/backup/ghidra-repo-20260917.git`，已克隆验证（217 文件、字节一致）
- GitHub 恢复后可加 remote 同步；该仓**独立于** `keysteam-unlock-spike`，与其封禁状态无关

## 阻塞原因（2026-09-17 实测）

`gh api repos/Drivpe/keysteam-unlock-spike` 返回：

```
{"message": "Sorry. Your account was suspended", "status": "403"}
```

**账号级封禁**，非 token 过期。`gh auth status` 报的「token invalid」是症状。

**影响面**：本机有 4 个仓库指向该账号（`keysteam-unlock-spike`、`kingdee-kit-private`、
`kingdee-knowledge-kit`、`Lingya`）。其余三个不在本 spec 范围内。

**数据风险（重要）**：本地 clone 完整（36 个提交，`behind: 0`），**代码与文档无损失**。
但 **GitHub Issues 不在 git 里**——`#13` map、`#16` 及其 10 条评论、`#17`、`#18`
**只在 GitHub 上，本地无副本**。封禁期间读不到。`#15` 例外：`.scratch/run-20260916-102001/`
下有 4 份本地文档副本。

## 后续动作（GitHub 恢复后）

1. 建 issue，正文取自 `spec.md`，标题自拟（建议围绕「探针脚本重复收口至 probe_lib」）。
2. 打 `ready-for-agent` 标签（`docs/agents/triage-labels.md` 定义）。
3. 若与 `#13` map 的关系需要确立——按交接建议，架构重构应作**独立票**（与「改样本消弹窗」
   这个 Destination 无关，属工具链自身维护）。
4. 本文件可在发布后删除，或保留为「离线产出的先例」。
