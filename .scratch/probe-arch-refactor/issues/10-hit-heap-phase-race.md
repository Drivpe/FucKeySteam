# 10 — `hit_heap.py` 的 phase 竞态：扫描会被永久跳过

**What to build:**

修掉 `hit_heap.py` 的一处既有逻辑错误：**在特定时序下，堆扫描被永久跳过，脚本静默退化为"什么都没扫"。**

## 缺陷

`hit_heap.py` 用 `state["phase"]` 控制两阶段流程。但 `phase` 的置位出现在**两个位置**，且**位置错误**：

**第 60–62 行**（`WaitForDebugEvent` 超时分支，即调试事件空闲时）：

```python
if not k32.WaitForDebugEvent(buf,3000):
    if k32.GetLastError()==121:
        if main_base and state["phase"]==0:
            state["phase"]=1                        # ← 置位
            L("searching heap copy @%.1f" % ...)    # ← 只打印，不扫描
        continue
```

**第 101–105 行**（事件循环内，真正的扫描）：

```python
if main_base and state["phase"]==0 and time.time()-t0>3.0:   # ← 要求 phase==0
    L("scan for heap copies @%.1f" % ...)
    found=[]
    ...
```

**错误机制**：任一分支先执行都会把 `phase` 置 1。若**超时分支先中**，它把 `phase` 置 1 却**不执行扫描**——于是第 101 行的扫描条件 `phase==0` **永远不再成立**，扫描被永久跳过。脚本此后若无其事地跑完 120 秒，日志里只有 `searching heap copy` 而**没有** `scan for heap copies`。

**触发条件**：样本在 `t>3.0s` 之前出现 ≥3 秒的调试事件空闲（`WaitForDebugEvent` 超时返回且 `GetLastError()==121`）。取决于调试事件密度，**是时序相关的，不是必现**。

## 实证

工单 04 的子代理在对拍时**实际撞到过**：迁移后首跑的 post 日志出现 `searching heap copy @5.7`，而**缺少**基线的 `scan for heap copies` 与 4 个堆副本地址。重跑同一份代码即恢复基线输出——证明是时序抖动而非代码变更。

对照 `hit_heap.txt`（既有日志）：`searching=0`、`scan=1`——那次未触发。

**修法方向（需判断）**：

- 超时分支**不应置位 `phase`**（它只是"空闲"，不是"已扫描"），或应改为独立的标志
- 或让超时分支**也执行扫描**（它本来就是"进程暂停时可做"的时机）
- 参照物：**`hit_heap2.py` 没有这个缺陷**——它的 `phase` 只在第 114 行（扫描完成后）置位。可对照其结构。

## 与工单 08 的关系

**无关。** 工单 04 的子代理怀疑二者同源，经核实**不成立**：

- `hit_heap.py` 走 **GUARD 页保护**路线（`STATUS_GUARD_PAGE_VIOLATION`），不使用硬件断点
- 工单 08 的问题在 `hwbp_data.py` 的**硬件写断点线程覆盖**

两者的共同点只是"机制没被触发"，成因不同。

## 边界

**本票不属于 `probe_lib` 收口范围。** 它是工单 04 的副产物，独立成立。

**依赖**：`hit_heap.py` 也被工单 04 触及（已提交 `0f94e0b`），故本票目前**无阻塞**。

## 验收

- [ ] 在 `t>3.0s` 前制造 ≥3 秒调试事件空闲的前提下，`scan for heap copies` **仍然执行**
- [ ] 两种时序（空闲先中 / 事件先中）**都能走到扫描**，各跑一次验证
- [ ] 修复后的输出与既有基线在规范化后一致（`hit_heap.txt` 有 `scan for heap copies` + 堆副本地址）
- [ ] `hit_heap2.py` 未受影响（它本无此缺陷，确认未被误改）
- [ ] 若选择"让超时分支也扫描"，需说明是否引入重复扫描

**Blocked by:** None — can start immediately.
