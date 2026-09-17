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
| `01` 查证 Dr7 缺陷影响 | ✅ **已完成** | 结论推翻原前提、影响面为零；暴露新缺口 → 开 `08` |
| `02` probe_lib 补四个函数 | ✅ **已完成** | 提交 `bfce6b7`；866 断言全绿、已独立复现 |
| `03` 迁移 `L()`（35 份） | ✅ **已完成** | 提交 `9e1b134`；但引入 P0 缺陷 → 已修复 |
| — P0 修复：6 脚本 ImportError | ✅ **已修复** | 提交 `7f4a486`；AST 全检 + 真机验证 |
| `04` 迁移 `rpm()`（7 份） | **进行中** | 已跑 4 个未受损基线，正在跑 3 个修复后基线 |
| `05` 迁移 `set_hwbp()`（3 份） | ⏸ 待 `04` | 与 `04` 碰同批文件，须串行 |
| `06` 统一 `read_pystr()`（3 份） | ⏸ 待 `05` | **唯一含行为变更**；与 `05` 同批文件 |
| `07` contract 收尾 | ⏸ 待 `06` | 已补前置警告（见下） |
| `08` 分离零命中解释 | ✅ **已完成** | 提交 `d0a5778` / `ea63276` / `9375ce4`；H4 被排除 |
| `09` 修正设断点时机（**新开**） | ⏸ 待 `04`–`06` | `08` 的副产物；主线程断点被系统性漏掉 |

## 工单 03 引入的 P0 缺陷（已修复）

**症状**：6 个脚本 `NameError: name 'make_L' is not defined` —— `L = make_L(f)` 被放在 `from probe_lib import *` 之前，而 `make_L` 来自该库。

**受损**：`disc16` / `disc16b` / `hwbp16` / `hwbp16b` / `hwbp_ctrl` / `hwbp_data`

**为何静态检查漏掉**：`py_compile` 与 `ast.parse` **都通过**（语法合法，只是运行时 NameError）；而工单 03 的抽样选了 `mydbg3`/`zd_dlg`/`guard_multi`——**恰好都是 import 在前的正确顺序**，避开了全部 6 个坏例子。

**教训**：抽样验证若样本选择有偏差，会让系统性缺陷完全隐形。**抽样必选"边界"而非"典型"。**

**修复验证（两层）**：AST 顶层语句顺序检查全部 36 个脚本损坏 0；真机跑 `hwbp_ctrl`（`EXIT code=0`、日志 50746 字节）与 `hwbp16b`（447 字节、内容正常）——修复前均为 0 字节。

## 工单 07 的前置发现（开工前必读）

`CONTEXT_DEBUG_REGISTERS` **不是 `probe_lib` 的模块级符号**——它只是 `set_hwbp` 的参数默认值。实测 `from probe_lib import CONTEXT_DEBUG_REGISTERS` → `ImportError`。

而脚本**确实在用它**（`ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS`）。所以 `07` 的第一步不是删定义，而是**先在库里把该常量提升为模块级符号**。已写入工单 07 的前置警告与验收项。

## 机制改进（本轮，已提交 `f80261d`）

**作业文件写-写竞争已修复。** 实际发生过一次：工单 03 写入 `zd_dlg` 后触发，任务跑的是工单 08 的 `dr7_q1_watch`——前者基线被污染。

修法是**原子认领**，不是"一方独占"：调用方写 `_elev_job_<id>.txt` → 原子 `mv` 成 `_elev_job.pending` → 执行器**读后立刻删除**。重命名是原子的，故无覆盖窗口。

**ignore 规则已补强**：并发工作产生的临时文件（实测 `gmPreTmp.py` 是 `guard_multi.py` 的副本）不在原规则内，会被 `git add -A` 带进仓库。已加 `*Tmp.py` / `_elev_logs/` / `_elev_job*` 等，并双向验证。

## 已验证的机制事实（供后续工单参考）

**提权自动化成立**：非提权会话触发 → `elevated=True` → 探针 `priv=True` → `hwbp_ctrl` 命中 423213 次。

**超时差异巨大**：35–300 秒（`mydbg4` 300s、`mydbg2/3/5/6` 180–240s、`zd_data` 35s）。**判断是否结束看 `_elev_run.log` 有无 `EXIT` 行，不要靠时间猜。**

**旧日志不可轻信**：实测 `att2.txt` 是非提权产物（`priv=False`、`err=5`），是误导性证据。**基线必须自己跑，且确认 `priv=True`。**

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
