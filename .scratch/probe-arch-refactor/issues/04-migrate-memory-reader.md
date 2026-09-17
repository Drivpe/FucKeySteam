# 04 — 迁移 `rpm()`：7 个脚本改用库函数

**What to build:**

7 个脚本里的 `rpm()`（读目标进程内存）定义删掉，改为从 `probe_lib` 取用。

**范围：7 个脚本**（实测全部含 `def rpm(`）：

- hwbp 组：`hwbp16b.py`、`hwbp_ctrl.py`、`hwbp_data.py`（三份实现逐字同一）
- 另四份：`catch_regs.py`、`hit_heap.py`、`hit_heap2.py`、`probe_r12.py`

**这一批为什么零风险：** 实测 7 份实现功能完全等价——同样的 `ctypes.create_string_buffer(n)`、同样的 `k32.ReadProcessMemory(...)` 调用、同样的 `buf.raw[:got.value]` 返回。差异只是变量命名（`b`/`buf`、`g`/`got`）与换行位置。

**注意 `hwbp16.py` 不在范围内**：它的 `set_hwbp` 签名是复数（`addrs`），与其余实现不兼容，属另一条技术路线。但它是否也含 `rpm`——本票开工前需先确认。若含，**不含 `set_hwbp` 的部分可以进本票**，因为 `rpm` 本身没有两条路线的分歧。

> **⚠ 清单陷阱**：`grep -ln '^def rpm(' *.py` 会命中 **8** 个文件，其中**包含 `probe_lib.py`**——那是**库自身的实现**，不是待迁移的副本。**本票不得修改 `probe_lib.py`。** 准确目标是 **7 个脚本**。

**验收方式：** 与第 03 票相同——逐脚本运行、日志对拍。这些脚本的日志中「读到的字节数」应保持不变。

**运行环境**：跑样本需 Windows + 提权，机制见 `../ELEVATION-HOWTO.md`。执行器带提权闸，非提权时会拒绝——**不要绕过**。

- [ ] 7 个脚本的 `rpm()` 定义已删除，改为从 `probe_lib` 取用
- [ ] `hwbp16.py` 是否含 `rpm` 已确认；若含则一并迁移（仅 `rpm`，不涉 `set_hwbp`）
- [ ] 7 个脚本的日志输出与迁移前逐行一致
- [ ] 每个脚本独立提交或独立记录

**Blocked by:** 02（库中需先有 `rpm()`）
