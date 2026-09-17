# 07 — 收尾：删除重复的常量定义与 API 设置重抄

**What to build:**

各脚本里重复的常量定义与 API 设置重抄删掉，全部改由 `probe_lib` 提供。

**具体三处重复（均为已确证的残留）：**

**其一：`EXCEPTION_SINGLE_STEP` 与 `CONTEXT_DEBUG_REGISTERS` 在 3 个 hwbp 脚本各自重复定义。** 而 `probe_lib.py` 早已定义 `EXCEPTION_SINGLE_STEP=0x80000004`。脚本侧的定义是多余的。

> ## ⚠ 本票前置：`CONTEXT_DEBUG_REGISTERS` 尚未由库导出（2026-09-17 实测）
>
> **开工前必须先确认这一条，否则会直接引入 `ImportError`。**
>
> 实测（Linux 侧裸 import 验证）：
>
> ```
> EXCEPTION_SINGLE_STEP      → 有（模块级，probe_lib.py 事件码段）
> CONTEXT_DEBUG_REGISTERS    → ❌ 无
> from probe_lib import CONTEXT_DEBUG_REGISTERS
>   → ImportError: cannot import name 'CONTEXT_DEBUG_REGISTERS' from 'probe_lib'
> ```
>
> **原因**：`CONTEXT_DEBUG_REGISTERS` 在库中**只是 `set_hwbp` 的参数默认值**（`def set_hwbp(..., CONTEXT_DEBUG_REGISTERS=0x00100010)`），**不是模块级常量**。脚本无法 `from probe_lib import` 它。
>
> 而脚本**确实在用它**：`ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS`（3 个 hwbp 脚本都有）。
>
> **因此本票的第一步不是删定义，而是先在 `probe_lib.py` 里把该常量提升为模块级符号**（与 `EXCEPTION_SINGLE_STEP` 同段）。这属于工单 02 的收尾补漏，**不是本票的范围外动作**——但不做它，本票无法完成。
>
> **验收时必须验证**：改动后 3 个 hwbp 脚本能在 Windows 侧正常 import 并运行（`python -c "import hwbp_ctrl"` 之类只能验语法，必须真跑）。

**其二：3 个 hwbp 脚本各自重抄了 `k32.CreateProcessW` / `ReadProcessMemory` / `VirtualQueryEx` 的 `argtypes` / `restype` 设置。** 而 `probe_lib.py` 中明文规定「统一在此定义一次，脚本不得再抄」。这批重抄会**绕开库的 restype 设置**，正是库里已记录的坑（`GetCurrentProcess` 的 restype 截断导致 `OpenProcessToken` 返回 `ERROR_INVALID_HANDLE(6)`）的同类风险面。

**其三：`LOG_DIR` 在多个脚本各写一遍**（值相同，变量名一致）。值相同的部分应内部化；但**日志路径本身仍由脚本指定**（见第 03 票），本票处理的是重复的字面路径。

**这一票是 contract 阶段**——只有当确认无调用方仍需要旧形式时才做。

- [ ] **`probe_lib.py` 已将 `CONTEXT_DEBUG_REGISTERS` 提升为模块级符号**（前置条件，见上）
- [ ] 3 个 hwbp 脚本中重复的 `EXCEPTION_SINGLE_STEP` / `CONTEXT_DEBUG_REGISTERS` 定义已删除
- [ ] 3 个 hwbp 脚本在 **Windows 侧真跑通过**（不是只做语法检查）——因为 `ImportError` 只有在 import 时才暴露
- [ ] 3 个 hwbp 脚本中重抄的 `argtypes` / `restype` 设置已删除，改用库中设置
- [ ] 重复的 `LOG_DIR` 字面路径已收口（值相同者内部化）
- [ ] 所有脚本重新运行一次，日志与本次收尾前逐行一致
- [ ] `probe_lib.py` 的说明与实际一致（「脚本不得再抄」这条规矩现在得到执行）
- [ ] 全目录 `grep -rn 'GetCurrentProcess()' *.py` 确认无脚本绕过 `current_process_handle()`

**Blocked by:** 03、04、05、06（须先确认所有调用方都已迁移，无脚本仍依赖旧形式）
