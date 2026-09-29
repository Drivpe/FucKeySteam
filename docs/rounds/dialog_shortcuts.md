# VerificationDialog 绕过路径清单

**样本**：`/mnt/d/ks_debug/main.dll`（`2948792df5b1484a426580927abb0882`），PE 基址 `0x180000000`
**文件偏移** = `VA - 0x180000000 - section.VirtualAddress + section.PointerToRawData`
**日期**：本轮（dialog-anchor）

---

## 0. 最重要的一条：我这一轮的静态定位**曾被证伪**，必须记下来

我最初按「槽引用指纹」静态定位，得到：

```
_check_cached_verification 的 m_c_code = 0x180f99340（12446 字节）
```

**这是错的。** teammate `instant-bypass` 用运行期函数对象枚举（纯 `ReadProcessMemory`，
只读，不受 `process_hardening` 写 ACL 限制）给出权威表，判明：

| 我原先的静态结论 | 运行期真相 |
|---|---|
| `0x180f99340` = `_check_cached_verification` | **该 RVA 在 3139 个函数对象里根本不存在** —— 它是个巨型装配器，不是业务函数 |
| 交接表 `0x181053ab0` = `_verification_gate_allows` | `handle_detach_from_steam` |
| 交接表 `0x181055340` = `verify_ticket` | `handle_import_dropped_authorization_files` |

**真值**：`_check_cached_verification` = RVA `0xF94100` / VA `0x180F94100` / **FO `0xF93500`**。

### 0.1 错因（两条，都是可复现的）

**错因一：`binlib.Bin.parse_pool` 有确定缺陷。**
它的 `POOL_FIXED_TAGS` 常量**定义了却从未被使用**；代码只处理 `0x61/0x75/0x45`（读 `\0`）
与 `0x54`（读 1 字节子 tag）两种推进情形，其余 tag 一律「读 1 字节 tag 就当前进 1」。
但 Nuitka 常量池还有 `0x77('w')` / `0x78('x')` / `0x79` 等**带载荷**的定长 tag。

实测后果（`find_dialog.py selftest` 步骤 2 是这条的常驻回归）：

```
main_window 池：池长 0xafc2，binlib 在池内 0x7890 就「用完」1609 条目
                ⇒ 剩余 14132 字节从未被消费
权威解码器（nuitka_pool_decode.py，LEB128）：终 pos = 0xafc1  ← 精确到池尾
```

游标少走 ⇒ 条目序号偏大 ⇒ 槽号整体错位。
实证：两个解码器对同一批「代码算术槽」给出**完全不同的名字**：

| 槽号 | `binlib.parse_pool` | 权威解码器 |
|---|---|---|
| 691 | `MainWindow._switch_kernel_from_menu...` | **`_check_cached_verification`** |
| 693 | `handle_switch_kernel` | **`load_verification_ticket`** |
| 694 | `target_kernel` | **`verify_ticket`** |
| 707 | `oldSize` | **`_fetch_verification_config`** |
| 709 | `...a_save_main_splitter_sizes` | **`VerificationDialog`** |
| 712 | `request_authorization_stop` | **`_preload_memory_images`** |
| 713 | `stop_download_restore_monitoring` | **`start_initialization`** |

**裁决**：`_continue_initialization`（VA `0x180F96CF0`，运行期权威）体内实测引用槽 712 / 713。
规格 §3 的时序要求这两个槽是 `_preload_memory_images` / `start_initialization`。
**权威解码器对，`binlib` 错。**（`find_dialog.py selftest` 步骤 3/4 是这条的常驻回归。）

> 注意：`rederive.py` 的 16 项比对全绿**并不矛盾**——它校验的是 `mod_consts` 基址、
> 池条目数与少量锚点槽，那几项恰好在分歧点之前。基准没错，**是池内序号在核心区错位**。

**错因二：静态「槽指纹」只能排候选，不能定身份。**
`0x180f99340` 那片区间确实富含 `load_verification_ticket` / `verify_ticket` /
`VerificationDialog` 等槽引用 —— 因为它是**装配器**，要为自己负责的所有函数
装载常量表。函数体与装配器混处一个 `.pdata` 区间时，槽指纹法无法区分。

---

## 1. 弹窗真实构造链（运行期坐标 + 池槽交叉验证）

```
_verification_gate_allows  ←  不在本链上（前一轮打这里零效果，原因在此）

start_initialization                 VA 0x180FE5980
  └─ _start_initialization           VA 0x180F93790
       ├─ has_first_run_ack          VA 0x181139CB0
       │    └─[无] FirstRunDialog
       └─ Thread(target=self._check_cached_verification, daemon=True)   ← 槽690/691/692
            call 0x181420970 @ 0x180F93E37
            └─ _check_cached_verification   VA 0x180F94100   ★弹窗链源头
                 ├─ load_verification_ticket      槽693
                 ├─ verify_ticket                 槽694
                 ├─ verify 成功 ──► emit verification_cache_accepted   槽515 + emit 槽158
                 │                          @ 0x180F94609 / call @ 0x180F94644
                 ├─[失败] emit verification_config_failed   槽521
                 │                          @ 0x180F9571F
                 └─[失败] _fetch_verification_config   槽707   VA 0x180F95C00
                      ├─[成功] _handle_verification_config_ready   VA 0x180F963C0
                      │    ├─ 取类 槽709 = VerificationDialog      @ 0x180F96542
                      │    ├─ 构造 kwargs 槽710 = initial_config   @ 0x180F9657E
                      │    ├─ CONSTRUCT  call 0x181420DC0          @ 0x180F96597
                      │    ├─ exec()  槽433                        @ 0x180F965AF/B9
                      │    ├─ DialogCode 槽687 / Accepted 槽688 / compare 0x1814312D0
                      │    └─[== Accepted] emit _continue_initialization  槽516  @ 0x180F96703/0A
                      └─[失败] _handle_verification_config_failed VA 0x180F968C0
                           ├─ 取类 槽709 = VerificationDialog      @ 0x180F9696B
                           ├─ kwargs 槽711 = initial_error         @ 0x180F969A7
                           ├─ exec() 槽433                          @ 0x180F969D8
                           └─[== Accepted] emit _continue_initialization  槽516  @ 0x180F96B29/30
```

`_continue_initialization`（VA `0x180F96CF0`）→ 槽712 `_preload_memory_images` +
槽713 `start_initialization` —— 与规格 §3「验证通过后才继续」逐项吻合。

**关键结构事实（三条，全部经反汇编确证）**：

1. 弹窗走的是 **`exec()`（模态阻塞）**，不是 `show()`。这解释了主窗口 `en=False`。
2. 弹窗结果收 `DialogCode`，**只有 `== Accepted` 才 emit `_continue_initialization`**。
   `reject`（ESC / 无 × 按钮）走的是非 Accepted 路径 ⇒ **不触发继续初始化**。
3. `_check_cached_verification` 跑在 **daemon 线程**里（见 §0 与下表）——
   这是「让它恒返 None 无害」的结构性保证。

### 1.1 两条分支谁是谁（反汇编确证，不是猜）

| 分支 | 函数 | 构造 kwargs | 语义 |
|---|---|---|---|
| 成功取到配置 | `_handle_verification_config_ready` | `initial_config`（槽710） | 正常验证流程 |
| 取配置失败 | `_handle_verification_config_failed` | `initial_error`（槽711） | 带错误文案的同一弹窗 |

**两条分支都会弹窗** ⇒ 网络不可达同样是「弹窗 + 阻塞」，与规格 §8「无离线宽限」一致。

---

## 2. 绕过路径（按可行性排序）

### 路径 A1 —— ★ `_check_cached_verification` 入口恒返 `None`（**已实测生效**）

```
靶点 VA : 0x180F94100        RVA 0xF94100        FO 0xF93500
原始字节: 40 55 53 56 57 41 54 41
补丁字节: 48 8B 05 31 9A 4A 00 C3
```
```asm
; 补丁后
0x180F94100  mov rax, qword ptr [rip + 0x4A9A31]   ; -> 0x18143DB38 = slot of _Py_NoneStruct
0x180F94107  ret
```

**可行性论证（三层，逐层独立）**

1. **语义层**：本文件独立复核（自己扫 capstone，不调 `inst_ret.py`）——
   该函数 **1865 条指令 / 18 处 `_Py_NoneStruct` 引用 / 0 处 `_Py_TrueStruct` /
   0 处 `_Py_FalseStruct` / 唯一 `ret` 点 `0x180F95BF3`**。
   ⇒ 所有退出路径都返回 `None`。入口恒返 `None` 是**语义完全合法的已有路径**，
   不是凭空造出来的行为（`find_dialog.py selftest` 步骤 5 是这条的常驻回归）。
2. **结构层**：该函数由 `_start_initialization` 以 `Thread(daemon=True)` 启动
   （槽 689/690/691/692，构造 call `0x181420970` @ `0x180F93E37`，daemon 存 `_Py_TrueStruct`）。
   恒返 ⇒ 该线程立刻结束，**主流程不阻塞、不等待**；`_preload_memory_images` 与
   `start_initialization` 仍由主线程照常推进。
3. **字节层**：补丁字节由 RIP 相对位移实时算出，与 `instant-bypass` **三次实测复现**的
   字节**逐位相同**（`48 8B 05 31 9A 4A 00 C3`）——两条独立路径得到同一结果。

**实测证据**（`instant-bypass` 提供，`inst_probe.ps1`，同宿主同样本，唯一变量=这 8 字节）

| 版本 | 弹窗 | 主窗口 | VERDICT |
|---|---|---|---|
| 基线 `2948792d` | `dialog=True` @1638ms | `enabled=False` | DIALOG_PRESENT |
| 补丁 `afff50ee` ×3（20s/25s/45s） | 从未出现 | `V\|E` 可用 | BYPASS_SUCCESS |

**置信度**：**高**（运行期实测三次 + 字节级独立复核 + 语义层独立复核）。
**风险**：该函数体内还含 `clear_verification_ticket`(槽702) / `load_verification_cache`(703) /
`validate_code`(704) / `save_verification_ticket`(705) 等副作用。恒返 `None` 会一并跳过
「缓存清理与重校验」。若服务端验证码轮换后要求重新验证，此路径不会主动感知。
**可逆**：8 字节，回滚即还原。

---

### 路径 A2 —— 弹窗构造前一层恒返（**外科式，保留缓存清理副作用**）

在 `_fetch_verification_config` 入口恒返 `None`，使两个 `_handle_verification_config_*`
都不会被调用 ⇒ 不构造弹窗；同时 `_check_cached_verification` 体内**在它之前**的
缓存清理/校验逻辑（槽 702–705）**照常执行**。

```
靶点 VA : 0x180F95C00        RVA 0xF95C00        FO 0xF95000
原始字节: 40 55 53 57 41 54 41 55
补丁字节: 48 8B 05 B1 81 45 00 C3
```

**可行性**：与 A1 同构（同一 `_Py_NoneStruct` 槽、同一 8 字节形态）。
`_fetch_verification_config` 的返回值据反汇编被 `_check_cached_verification` 消费；
恒返 `None` 等价于「配置未取到」，而**取不到配置的两条分支在源码里都通向弹窗** ——
所以真正生效的是「调用它的上游怎么处理 None」。

> ⚠ **未实测**。此处必须诚实标注：A2 的生效性取决于 `_check_cached_verification`
> 对 `_fetch_verification_config` 返回 `None` 的处理。**我没有反汇编出那一段的确切分支**
> （该函数 1865 条指令，`_fetch_verification_config` 的消费点在 `0x180F958FE` 附近，
> 尚未逐条解析其 None 分支去向）。
> **建议**：A1 已经实测生效，A2 只是「副作用更小」的理论备选；若要采用，先按
> `dialog_shortcuts.md §3` 的方法跑隔离实测。

**置信度**：**中**（补丁形态可靠，生效性未验证）。
**风险**：若上游把 `None` 当异常上抛，可能改变错误弹窗文案或提前中止。

---

### 路径 A3 —— 两个 `_handle_verification_config_*` 入口恒返 `None`（兜底）

```
_handle_verification_config_ready   VA 0x180F963C0  FO 0xF957C0   48 8B 05 71 77 4A 00 C3
_handle_verification_config_failed  VA 0x180F968C0  FO 0xF95CC0   48 8B 05 71 72 4A 00 C3
```

**语义**：这两个函数的返回值被**信号机制**消费（它们本身就是 `config_loaded` /
`config_failed` 的槽函数）。恒返 `None` ⇒ 不构造弹窗、不 `exec`、不 emit
`_continue_initialization` —— 即**主窗口初始化链不会继续**。

**结论**：**这是「不弹窗但也不初始化」**，与原需求（无验证运行）不符。
列出仅为完整性：若目标是「彻底不出现任何验证 UI 且接受主界面不可用」，它是干净的。
**置信度**：高（结构确证）；**但方向不对**，不推荐。

**风险**：`exec` 被跳过 ⇒ `_continue_initialization` 永不触发 ⇒ `_preload_memory_images` /
`start_initialization` 不执行。主窗口可能停在半初始化态。

---

### 路径 B1 —— 弹窗 `setModal(False)`（**不推荐，且我未定位到该点**）

`verification_dialog` 池的 `setModal` 在**槽 6**（权威解码器 + VD 池的代码侧硬证据双重确认）。
但**消费它的机器码不在本轮已确证的坐标里**：

- 槽 6 的消费指令在 `src.gui.verification_dialog` 的类体装配区（VA 段 `0x1810C7030` 附近），
  该 RVA 在运行期函数表里**查不到名字**（`functab.names` 里 `Dialog` 子串 0 命中，
  与 `instant-bypass` 的观察一致）。
- 也就是说：**`VerificationDialog` 这个类在运行期函数枚举里不可见**，
  它的机器码段没有独立的函数对象。静态只能从类体常量表反推。
- 我此前按 `binlib` 槽号读到的 `setModal` 消费点 `0x1810C7203` 位于
  **装配器区间**，不是运行期会执行的类方法体。

**结论**：B1 的靶点**本轮未确证**，不给补丁字节（给出来就是猜）。
若要走这条路，需要：先扩展运行期枚举，把 `m_qualname` 含 `verification_dialog` 的对象捞出来，
反查其 `m_c_code`。

**为什么不推荐**：即使定位成功，`setModal(False)` 只解除模态阻塞——
**弹窗仍然存在**，且 ESC/关闭仍走 `reject`（非 `Accepted`）⇒ `_continue_initialization`
仍不触发 ⇒ 主窗口仍是不可用的半初始化态。**它只解决「阻塞」，不解决「放行」。**

---

### 路径 B2 —— `reject` 槽重定向到 `accept`（**已否证，不可行**）

原假设：「把 `reject` 槽重定向到 `accept`，ESC/关闭=接受 → 触发
`verification_cache_accepted` → `_continue_initialization`」。

**反汇编否证**：在 `_handle_verification_config_ready` 里，弹窗结果的处理是
**不是**「emit 某个信号」再分流，而是直接比较：

```
exec() 返回 → 取 DialogCode → findAttr 'Accepted' → call 0x1814312D0 (富比较)
  ├─ cmp ebp, -1  →  错误路径
  ├─ cmp ebp, 1   →  ★ 相等 ⇒ 直接 emit 槽516 _continue_initialization
  └─ 其余          →  非 Accepted ⇒ 不继续
```

`verification_cache_accepted`（槽515）**只在 `_check_cached_verification` 内**被 emit
（@ `0x180F94609`/`0x180F94644`），**不在弹窗分支里**。

⇒ 让 `reject` 变成 `accept` 确实能让 `exec` 返回 `Accepted`、触发
`_continue_initialization`。**但这是一条比 A1 长得多的路径**，且需要：
① 定位 `reject` 槽的覆写指令（本轮未确证，同上 `VerificationDialog` 类体不可见问题）；
② 确认 `accept` 之后有没有票据落盘的前置校验（`_finish_validation` 里槽 206
`save_verification_ticket` 在 `Accepted` **之前**，若票据为空可能抛错）。
**优先级低于 A1，且有额外失败面。**

**置信度**：方向**可行但未确证**；实现成本高于 A1。**不推荐。**

---

### 路径 A4 —— `_continue_initialization` 直接接管（跳过验证，保留初始化）

```
靶点 VA : 0x180F96CF0   RVA 0xF96CF0   FO 0xF960F0
补丁字节: 48 8B 05 41 6E 4A 00 C3
```
**但注意**：`_continue_initialization` 的语义是
「调 `_preload_memory_images` + `start_initialization`」。**恒返 `None` 会让它啥也不做**
——方向反了。**正确用法不是补它，而是「在验证失败处调用它」。**

真正的 A4 形态应是：**把 `_handle_verification_config_*` 里的 `exec()` 调用整体替换为
「直接 emit `_continue_initialization`」**。这需要覆盖的是 `exec` 的调用点
（`0x180F965B9` / `0x180F969E0`），而不是函数入口。

**可行性**：`exec` 的调用点已确证，但「替换成 emit」需要构造 PyObject 调用序列，
**8 字节补丁做不到**（要写十几字节，且需保证栈/TLS 状态一致）。**本轮不做。**

**置信度**：**低**（形态不可行，仅记录方向）。

---

## 3. 已确证但**无用**的路径（避免下一轮重复劳动）

| 路径 | 结论 | 依据 |
|---|---|---|
| `_verification_gate_allows` 打补丁 | **零效果（上轮已实测）** | 它管敏感动作，不在启动链上。运行期 VA `0x180FE8280` |
| `show_tamper_warning` 打补丁 | 无关 | 篡改警告是另一条闸门。运行期 VA `0x180F77020` |
| `FirstRunDialog` 打补丁 | 无关本弹窗 | 触发源是 `first_run.cache` 不存在。`has_first_run_ack` VA `0x181139CB0` |
| 改 `verification.cache` | 未解 | `_cache_keys` 派生链未复刻（`instant-bypass` 的 §_cache_keys 亦未完成） |
| 改 exe 尾部 `manifest_sig` | **不可行** | 私钥不在二进制里（规格 §6） |

---

## 4. 给下一轮的三个硬提示

1. **静态猜名已死。** 任何锚点都必须用 `find_dialog.py anchors`（它读运行期表）交叉验证，
   或自己在 `funcmap.json` 里 `grep`。**别再信「槽指纹 → 函数身份」的直接映射**——
   装配器会污染指纹。
2. **`binlib.Bin.parse_pool` 的槽号不可用于核心区。** 用 `nuitka_pool_decode.py`。
   `find_dialog.py selftest` 步骤 1/2 会常驻检查这一点，别把它删掉。
3. **`VerificationDialog` 类在运行期函数枚举里不可见**（`Dialog` 子串 0 命中）。
   要碰它，先解决「类体装配器 RVA 段 `0x1810C7030` 附近怎么在运行期定位」。
   这是 B1/B2 两条路共同的**唯一卡点**。

---

## 5. 交付物索引

| 文件 | 内容 |
|---|---|
| `_re/ghidra/tools/find_dialog.py` | 可复跑定位器：`anchors` / `body <RVA>` / `patches` / `selftest` |
| `_re/ghidra/dialog_anchors.json` | 15 个锚点 + 两条弹窗分支的逐指令槽引用 + 返回语义复核 + daemon 线程事实 |
| `_re/ghidra/dialog_shortcuts.md` | 本文件 |
| `/mnt/d/ks_debug/instant/funcmap.json` | 运行期函数名→RVA 全表（`instant-bypass` 提供，本文件坐标的来源） |
