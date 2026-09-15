## Parent

#8

## What to build

一个**可回滚的干净起点**：数据目录与 Steam 插件目录已被完整备份并留痕哈希，且当前不存在残留的宿主或样本进程。

这是本路线的第 0 步，独立成票的理由是它可以被单独验收——备份是否完整、能否回滚、环境是否干净，这三件事与后续任何观测结果无关。若这一步做错，后面两次启动的全部结论都失去意义，而且失败时无法区分「方案不成立」与「环境本来就脏」。

样本已知会 `terminate_all` 杀 Steam 进程并清理 `config/stplug-in/`（`.lua` / `.ks` 在清理范围内）。本路线不主动触发该行为，但启动样本本身就可能发生，所以备份必须先于任何启动。

## Acceptance criteria

- [ ] `%APPDATA%\Shikieiki\` 已整体复制到 `_re/backup/` 下的新目录，含 `verification.cache` 与 `first_run.cache`
- [ ] `config/stplug-in/` 已整体复制到同一备份目录下，`.lua` / `.ks` 文件数量与源目录一致
- [ ] 备份目录内每个文件的 sha256 已记录，且与源文件逐一核对通过
- [ ] 备份前 `verification.cache` 的存在状态与哈希已记录（它是后续判定「是否被改写」的基准）
- [ ] `Get-Process` 显示不存在残留的宿主进程，也不存在样本进程；若有则已终止并记录
- [ ] 备份目录路径与回滚命令已写入本轮运行记录

## Blocked by

- None — can start immediately.
