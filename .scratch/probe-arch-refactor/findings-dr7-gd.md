# 01 — `Dr7` GD 位缺陷查证结论

**状态**：查证完成（静态 + Linux 侧位运算推演）。一项环境判据待 Windows 实测。
**对应工单**：`.scratch/probe-arch-refactor/issues/01-verify-dr7-defect-impact.md`
**证据基线**：`_re/ghidra/` @ `cb04c2e`（`hwbp_data.py` 与 `f16252b` 基线逐字节一致，见证据 E6）

---

## 结论（三句话）

1. **GD 位**（bit13）在本实现里**是一个恒为 0 的空问题，而不是一个"设错了值"的问题**。`hwbp_data.py` 在写入 `Dr7` 前无条件执行 `& ~0xFFFFFFFF`，该掩码覆盖 bit0–31 全部 32 位，**`GD` 在读入后被清成 0 才回写**。测得终值恒为 `0xd0001`，与上下文里的 `Dr7` 原值无关；GD 在终值中**必然为 0**。
2. **因此"数据断点设了但没生效"由 GD 造成的假说不可测**——GD 只在"传入 `GD=1` 然后被清给触发器"这条路径上起作用，本实现里根本没有这条路径。真原因要从**另外 4 条活解释**里找，其中一条已被日志直接证实（见下）。
3. **`hwbp_data.py` 的两次运行日志里命中数为 0，不是"命中数从别处来"，而是「本来就没有命中数」。** 工单预设的"若断点未生效而日志有命中，命中的是什么"这一分支**事实不成立**——`grep -c 'DW HIT'` 在两份日志上均为 **0**。

**工单核心问题「数据断点场景下 GD 位是否必要」的实测答案**：在本实现的上下文里**该问题是空的**——GD 位在编码路径上被结构性地清零，所以它从未参与、也无法解释任何观测。既有实验结论**不受此次查证的波及**（影响面见 §5）。

---

## 1. 支持证据

所有命令均以 `_re/ghidra/` 为工作目录。**不引用裸行号**——下面每处行号都由同一行的 `grep -n` 现场产出。

### E1 — GD 位在写入前被清（缺陷 2 的准确形态）

```
$ grep -n 'dr7 = ctx.Dr7 & ~0xFFFFFFFF' hwbp_data.py
94:    dr7 = ctx.Dr7 & ~0xFFFFFFFF
```

`0xFFFFFFFF` = bit0–31 全 1，`~` 后为 `0xFFFFFFFF00000000`。`GD = 1<<13 = 0x2000` 落在被清范围内 → **`dr7` 的 bit13 在该行之后恒为 0**，此后三行 `|= 0x1` / `|= 1<<16` / `|= 3<<18` 均不触及 bit13。

三份族 A 实现的同址语句：

```
$ grep -n '~0xFFFFFFFF' hwbp16b.py hwbp_ctrl.py hwbp_data.py hwbp16.py
hwbp16b.py:95:    ctx.Dr7 = (ctx.Dr7 & ~0xFFFFFFFF) | 0x1   # L0=1, RW0=00 (执行), LEN0=00
hwbp_ctrl.py:94:    dr7 = ctx.Dr7 & ~0xFFFFFFFF
hwbp_data.py:94:    dr7 = ctx.Dr7 & ~0xFFFFFFFF
hwbp16.py:61:    dr7 &= ~0xFFFFFFFF
```

四份实现**全部**执行该清零（`hwbp16.py` 通过循环重填槽 0–3 缓解，但仍清掉调用者原有的 RW/LEN）。**这是共性结构缺陷，不是 `hwbp_data.py` 独有。**

### E2 — 位运算推演：终值与入参无关，GD 恒为 0

直译三份实现的位运算（脚本内联，**不导入 `probe_lib.py`**，因为该模块在 Linux 侧 import 会因模块级 `ctypes.WinDLL` 失败）：

```python
def hwbp_data_dr7(prev):                      # hwbp_data.py:94-98 直译
    dr7 = prev & ~0xFFFFFFFF
    dr7 |= 0x1; dr7 |= (0x1 << 16); dr7 |= (0x3 << 18)
    return dr7
```

| 入参 `Dr7` | `hwbp_data` 终值 | GD 位 | L0 | RW0 | LEN0 |
| --- | --- | --- | --- | --- | --- |
| `0x0` | `0x00000000000d0001` | 0 | 1 | 01（写） | 11（4B） |
| `0x2000`（带 GD） | `0x00000000000d0001` | 0 | 1 | 01（写） | 11（4B） |
| `0xFFFFFFFFFFFFFFFF` | `0xffffffff000d0001` | 0 | 1 | 01（写） | 11（4B） |

**入参带不带 GD，输出逐位相同。** 这条推演同时说明：**"传 `GD=1` 而不是清除它"这条路径压根不存在**，因为清除发生在读取之后、任何 `|=` 之前。

### E3 — 两份 `hwbp_data` 日志命中行数 = 0

```
$ grep -c 'DW HIT' hwbpData_d1.txt hwbpData_wa.txt
hwbpData_d1.txt:0
hwbpData_wa.txt:0

$ wc -c hwbpData_d1.txt hwbpData_wa.txt
 327 hwbpData_d1.txt
 313 hwbpData_wa.txt
```

日志全文（327 / 313 字节，已通读）：

```
=== hwbp_data: 硬件写断点监测 mod_consts 页写入 (模块初始化) ===
probe_lib 导入成功
priv=True
CreateProcessW ok=True pid=25668
MAIN.DLL base=0x7ff8de8c0000 @0.021s

=== 汇总 ===
getattr+call 命中总数: 0
匹配目标属性名的命中: 0 (已记录 0 条)
```

**结论：`hwbp_data.py` 从未产出过任何命中。** 工单与 ADR 0002 设想的"C 场景"（断点未生效但日志有命中）**在这两份日志里不存在**。

### E4 — 正对照证明"断点机制本身可用，只是数据断点没响"

同一批次（2026-09-17 11:39，同一提权窗口）跑的阳性对照：

```
$ grep -c 'DW HIT' hwbpCtrl_p1.txt
400
$ tail -c 400 hwbpCtrl_p1.txt
getattr+call 命中总数: 400521
匹配目标属性名的命中: 400521 (已记录 400 条)
```

三份日志 + 三个运行器构成一个**完整的批次记录**：

| 文件 | 运行器（`grep -n 'hwbp' run16_round3.bat run16_round4.bat`） | 断点类型 | 结果 |
| --- | --- | --- | --- |
| `hwbpCtrl_p1.txt` | `run16_round3.bat` 步骤 [1/4] | 执行（`RW0=00`）@ `0x1422ec0` | **400521 命中**（`hwbpCtrl_p1.txt` 汇总段） |
| `hwbp16b_wb.txt` | `run16_round4.bat` 步骤 [B] | 执行（`RW0=00`）@ `0x1422ec0` | **474470 命中** |
| `hwbpData_d1.txt` | `run16_round3.bat` 步骤 [2/4] | 写（`RW0=01`）@ `0x1dd16a0` | **0 命中**（汇总段两行均为 0） |

**批次完整性是可证伪的，且成立**：`hwbpData_d1.txt` 与 `hwbpCtrl_p1.txt` **同为 `run16_round3.bat` 的步骤 [1/4] 与 [2/4]**（`grep -n 'hwbp' run16_round3.bat` 可见 `hwbp_ctrl.py p1` 在前、`hwbp_data.py d1` 在后）。批次的其它成员大量命中，说明**调试机制、提权、样本存活、事件循环全部正常**。因此 `hwbp_data` 的 0 命中**不是机制性失败**。

### E5 — `hwbp_data` 的 `dr7` 与正对照完全相同（除 RW/LEN），GD 不区分二者

| 实现 | 终值 | 与正对照的差异位 |
| --- | --- | --- |
| `hwbp_ctrl` / `hwbp16b` | `0x1` | 基准 |
| `hwbp_data` | `0xd0001` | bit16、bit18、bit19（RW0/LEN0） |
| GD 位 | 两者**均为 0** | 无差异 |

**GD 对执行断点（`RW0=00`）与数据断点（`RW0=01`）的影响在本实现里同为"不存在"**——两者都把它清成 0，而执行断点照样命中 40 万次。

### E6 — 代码与基线一致（防止"缺陷是后来引入的"这一替代解释）

```
$ git diff --stat HEAD -- hwbp_data.py hwbp_ctrl.py hwbp16b.py
（空）
```

`hwbp_data.py` 与 `f16252b` 逐字节一致。**缺陷存在于版本控制基线里，不是迁移引入。**

### E7 — 工单 02 的 `probe_lib.parse_dr7` 与三份原件逐位对拍通过

`probe_lib.py` 的纯计算段（常量子段 + `parse_dr7`，**切出后在 Linux 侧执行，不 import 整模块**）对 12 组入参 × 3 份实现 = 36 组对拍：

```
对拍样本 36 组，不一致 0 处
hwbp_data 终值(任意入参): 0xd0001 0xd0001 0xffffffff000d0001
GD 在 &~0xFFFFFFFF 之后必然为 0: True
```

且 `probe_lib.py` 已把 GD 参数化：

```
$ grep -n 'DR7_GD_BIT\|gd=None' probe_lib.py
198:DR7_GD_BIT = 1 << 13          # 缺陷 2 对应位：现存实现从未处理
222:              clear_all_slots=True, slot=0, gd=None):
```

**默认值 `gd=None`（不触碰 bit13）与现存行为逐位一致；而现存行为里 bit13 恒为 0**，故默认路径的实际语义是"GD=0、且不触碰调用者位"的复合体。这层复合语义在 `parse_dr7` 的 docstring 里**未被显式点出**——见 §6.2。

---

## 2. 被排除的替代解释（负结论的活解释清单）

"`hwbp_data.py` 的观测无效"这一负结论，其可能原因如下。**全部 6 条**都已检查：

| # | 活解释 | 判定 | 依据 |
| --- | --- | --- | --- |
| H1 | GD 位未置 1 导致 `Dr7` 写入被硬件丢弃，断点从未生效 | **不适用（空假设）** | 本实现 `Dr7` 终值里 GD 恒为 0（E1/E2）。该机制要求"传入 `GD=1` 后被清"，本实现无此路径。故 GD **既非充分也非必要**地参与了本次观测 |
| H2 | 断点有效，但 `0x1dd16a0` 在窗口内未被写（模块未初始化 / 走缓存路径） | **活** | 与 0 命中相容。**本条需 Windows 实测分离**（§7） |
| H3 | 数据断点对目标访问类型不触发（写断点不捕获读） | **活** | 仓库已自证：`probe_lib.py` 头注 "DR0-DR3 的数据断点对纯'读'不触发"。若 `mod_consts` 只被**读**，写断点必然 0 命中 |
| H4 | 4 字节 `LEN0` 与目标地址的 4 字节对齐不满足 → 该槽被静默禁用（x86 要求） | **活，且未被任何日志排除** | `WATCH_DATA[0] = 0x1dd16a0`，低 4 位 = `0x0`，**是按 16 字节对齐的**（`0x1dd16a0 % 16 == 0`）。故 H4 对**当前地址**不成立，但代码里没有任何对齐校验，**换地址即复发** |
| H5 | 调试器逻辑缺陷（如条件写反）使命中被漏记 | **已排除** | 同一份逐字复制的调试循环在 `hwbp_ctrl`/`hwbp16b` 里产出 40 万+ 命中；`hwbp_data` 与它们仅差 `~=` 的最后一行（`rip !=` vs `rip ==`，各自与其断点类型自洽）。逻辑可用 |
| H6 | 提权/环境失败，探针根本没跑起来 | **已排除** | 日志含 `priv=True`、`MAIN.DLL base=... @0.021s`、`CreateProcessW ok=True`；且**批次完整性**成立（E4） |

**H1 的排除方法与本仓库纪律的关系**：工单要求"负结论必须列出所有活解释"。H1 的排除**不依赖任何硬件行为证据**，只依赖对本实现代码的位运算推演——推演在 Linux 侧可复现（E2），**这是本次查证中唯一完全不依赖 Windows 的部分**。

---

## 3. 执行断点（`RW0=00`）是否同样受 GD 影响

**答：在本实现里"同样不受影响"，但理由与工单设想相反。**

工单问题 4 预设"GD 对执行断点与数据断点的影响可能不同"。就 **x86 语义**而言，该预设正确：GD=1 时 `DR0–DR3` 的**读**操作（`MOV r32, DRn`）触发 `#DB`，而 GD 的设立动机是"阻止调试器读取断点地址"。这**只涉及寄存器的读访问**，与断点的 RW/LEN 类型（执行/写/读写）无关。

**但在本实现里，该语义无处落地**：两份执行断点实现 `hwbp16b.py` / `hwbp_ctrl.py` 与 `hwbp_data.py` 一样执行 `& ~0xFFFFFFFF`，同样把 GD 清成 0（E1）。所以：

- **执行断点不因 GD 而失效**——因为它们的 GD 也是 0，而它们命中了 40 万次（E4）。
- **数据断点不因 GD 而失效**——同样理由，GD 是 0。
- **GD 在本实现族里没有区分能力**：它不解释任何一组观测的差异。

**因此 `hwbp_ctrl.py` / `hwbp16b.py` 不受"GD 缺陷"影响，但受影响的方式与 `hwbp_data.py` 相同——即都不受影响。** 工单问题 4 的答案是"**是同一影响（=无影响）**"，而非"影响不同"。

> **本节结论的一个限定**：以上是**"现实现下 GD 不区分"**的结论，非"GD 在 Windows 上无所谓"的结论。后者需实测（§7 Q3）。

---

## 4. 与既有 `_re/ghidra/dr7_forensics.md` 的关系（不静默改写）

`dr7_forensics.md` 对 GD 的表述（由 `grep -n 'GD' dr7_forensics.md` 定位）为：

> "四份实现都**没有**处理 GE/LE 位（bit8-9）与 GD 位（bit13，**读 Dr7 需置 1 才能让数据断点生效的 x86 细节**）……这是本组实现共同的空白区，签名不掩盖它，但也不修复它。"

**判定：该表述在本仓库语境里会产生一处误导，但不是事实错误。**

- **不错误**：它的前半句"没有处理 GD 位"正确，且已正确区分了 `global_enable`（G0–G3，bit1/3/5/7）与 GD。
- **误导之处**：括注"读 `Dr7` 需置 1 才能让数据断点生效"把 GD 描述成**数据断点生效的必要条件**。这直接派生了 ADR 0002 与工单 01 的"GD=0 会使 `Dr7` 写入不生效"这一表述。而实测表明：**GD 位在本实现里被 `& ~0xFFFFFFFF` 结构性地清成 0，"写入不生效"这一后果无法由 GD 解释**——真因在 H2/H3/H4 里。
- **处置**：按本仓库纪律（`docs/agents/domain.md` §"On correcting an issue"），**不静默改写**——本结论文件即追加说明；正文修订建议见 §8。

**注**：`dr7_forensics.md` **未被 `.gitignore` 排除、已纳入 git 跟踪**（`git ls-files | grep dr7_forensics` 有输出），可正常纳入修订。

---

## 5. 影响面清单

### 5.1 `hwbp_data.py` 的下游：**不受影响**（每条附依据）

| 文档 / 论断 | 是否受本次查证影响 | 依据 |
| --- | --- | --- |
| `docs/suppressing-the-dialog.md` | **不受影响** | 该文件**零处**引用 `hwbp_data` / `hwbp16b` / `hwbp_ctrl` / `Dr7`（`grep -n 'hwbp' docs/suppressing-the-dialog.md` 零命中）。其证据底座是**静态常量分析**与 **`EnumWindows` / `QApplication::notify` 路径分析**，非硬件断点 |
| `docs/suppressing-the-dialog-evidence.md` | **不受影响** | 同上，零处 `hwbp` 命中。其零命中排除清单是**常量池检索**口径，与调试寄存器无关 |
| `docs/probe-index.md` | **不受影响** | 同上，零处 `hwbp` 命中。其内容为三探针批次（宿主契约 / 磁盘状态 / 远程清单），不依赖 `hwbp_data` |
| 票据 `#16`–`#18` 中依赖 `hwbp_data` 观测的论断 | **不受影响（因不存在这样的论断）** | 见 5.2 |
| `_re/ghidra/README.md` 中 `mod_consts` 定位结论 | **不受影响** | 该结论由 `candidateA.py` / `modconsts.py` 的**静态推导**得出，`hwbp_data.py` 是"用写断点验证初始化时机"的**旁证**；旁证 0 命中在此**不构成反证**（H2/H3 活） |
| ADR 0002 的**决策**（保留缺陷、逐位等价） | **不受影响** | 决策理由是"可机械判定的安全网"，与缺陷影响面解耦。`parse_dr7` 逐位对拍已通过（E7） |

### 5.2 票据 `#16`–`#18`：**无法在本机核验，且不构成阻塞**

`#16`（含 10 条评论）、`#17`、`#18` **只存在于 GitHub**，无本地副本：

```
$ gh api repos/Drivpe/FucKeySteam
{"message": "Sorry. Your account was suspended", "status": 403}
```

`.scratch/probe-arch-refactor/SPEC-STATUS.md` 已登记该封禁。

**但从本地可得的 `#16` 原始材料反推，其结论与数据断点无关**：

- `#16` 的实验记录保存在 `_re/backup/round16-20260917/` 与 `run16_round3/4/5.bat`。
- `#16` 的**成功判据**写在运行器自身的提示里：`run16_round3.bat` 的 `echo   %GH%\hwbpCtrl_p1.txt    (control: must show hits)` —— **正对照是那个必须出命中的**，而它出了 400521 条。
- `#16` 的**实际产出结论**来自 `hwbp16b`（按属性名反查调用者，命中 `fromhex` × 30、caller `rva=0x10fd9cf`）与 `hwbp_ctrl`（正对照），**皆非 `hwbp_data`**。
- 因此 **`hwbp_data` 的 0 命中对 `#16` 而言是"一个辅助探针没有产出"，而非"一个已采纳的观测崩塌"**。

**影响面结论：无一条既有断言的证据链经过 `hwbp_data` 的命中数。** 该脚本在本批次中的角色是**辅助/旁证**，且其 0 命中**在批次记录里本就是显式结果**（`hwbpData_d1.txt` 的 `汇总` 段写明 0），**并未被任何人当成阳性证据使用**。

> **不过度断言**：`#16`–`#18` 的正文无法读取，故上述是"**从本地残留材料反推**"的结论。若 GitHub 恢复后发现某条评论确实引用了 `hwbpData_*.txt` 的命中数，应回到本文件补充——**这是唯一仍可能改变影响面结论的入口**。

### 5.3 一处**新发现的、独立的**观察（非本次查证范围，但由证据直接暴露）

`hwbpData_wa.txt`（2026-09-17 11:56）与其所属运行器时间不符：

- `run16_round4.bat`（文件 mtime 09-17 11:45）执行 `hwbp_data.py wa` 与 `hwbp16b.py wb`；
- 但 `hwbpData_wa.txt` 时间戳为 **11:56**，`hwbp16b_wb.txt` 为 **11:57**——**同批两项的 file mtime 相差 1 分钟**，而该脚本单次运行上限是 **40 秒**（`while time.time() - t0 < 40`）；
- 且 `hwbpData_wa.txt` 的**末行标题是"`-- 写入者频次 --`"**（`grep -n '写入者频次' hwbp_data.py` 第 208 行），而 `hwbpData_d1.txt` 的末行是旧版标题"`-- 属性名 x 调用者 频次 --`"——**两份日志出自不同版本的 `hwbp_data.py`**，尽管当前文件与基线逐字节一致（E6）。

**该差异说明 `hwbp_data.py` 的日志来自两代代码**，与"逐位等价对拍"所用的**当前版本**不是同一代。这不改变本次结论（两代都 0 命中），但**在后续任何"新旧日志对拍"里必须注意**——否则会重演 ADR 0002 修订所警告的"`read_pystr` 统一后历史日志不可逐行比对"。已登记漂移表（§9）。

---

## 6. 对本轮重构票的直接影响

### 6.1 工单 05（`set_hwbp` 参数化）：**无新增约束**

现有 `parse_dr7(..., gd=None)` 默认已与现存行为逐位一致，36 组对拍通过（E7）。

### 6.2 建议补一处 docstring（低成本、防未来误判）

`probe_lib.py` 里 `gd` 的默认值语义需要一句显式说明。当前 docstring 写"`None`（默认）= 不触碰 bit13，与现存实现逐位一致"，措辞正确；但读者容易误以为"现存实现在 bit13 上**保留**了上下文的值"。**实际是：现存实现先把 bit13 清成 0，`gd=None` 只是不做后续二次修改，故现存路径下 bit13 恒为 0。**

建议措辞（不改变任何行为）：

> `gd=None` 时 bit13 的最终值由 `clear_all_slots` 决定：`clear_all_slots=True`（默认、等价现存行为）下 `& ~0xFFFFFFFF` 已将 bit13 清 0，故**现存路径下 GD 恒为 0**；`gd=None` 仅表示"本函数不再二次触碰 bit13"。

### 6.3 工单 06（`read_pystr` 统一）：**结论不变**，另加一条记录

`hwbp_data.py` 的 0 命中**与 `read_pystr` 无关**——日志里连 `DW HIT` 行都没有，从未走到 `read_pystr` 调用点。故 ADR 0002 修订里"`read_pystr` 统一后 `hwbp_data` 的历史日志与新日志不再逐行可比"这一风险**对 `hwbp_data` 实际为空**（它没有可比的行）；**但对 `hwbp_ctrl` 成立**（它有 400→400521 的命中行与属性名统计）。

---

## 7. 仍需 Windows 实测才能定论的部分

> **2026-09-17 追加说明（工单 08 已完成，本节 Q1/Q2 已结案）**：
> 本节 Q1 与 Q2 已在 Windows 提权下执行完毕，结论见
> `.scratch/probe-arch-refactor/findings-hwbp-zero-hit.md`。摘要：
>
> - **Q1 答**：`0x1dd16a0` **确实被写过**（`@0.884s`，`00000000 → 301a60a4`，13 线程同时观测）。
>   §1 E3 的 H2 由此**排除**。
> - **Q2 答**：**存在写断点正对照了** —— 本目录首个。`dr7_q5_ab.py` 用同一循环取得 **2 次写断点命中**，
>   编码回读 `Dr0=目标VA, Dr7=0xd0001`。§2 表里的 **H4 由此排除**。
> - **本节的「最大缺口」已填补。H3 与 H4 已分离**：真因不是二者，而是**该脚本的断点线程覆盖范围
>   与写入者不重合**（写入者是主线程，而 `hwbp_data.py` 结构上只对 `main.dll` 加载后新建的线程设断点）。
>
> 本节正文保留原文不改（按 `docs/agents/domain.md` §"On correcting an issue" 的追加纪律）。
> 漂移表已登记两条：**H4 被否证**（写断点有效，首个正对照成立，0 命中真因是线程覆盖），
> 以及 **`WriteProcessMemory` 不能用作数据断点的激发源**（实测 6 次外部写全 0 命中）。
> Q3（GD 在本机 CPU 上的真实语义）与 Q4（`mod_consts` 是否只被读）仍为开放项，
> 但 Q4 的答案已由 Q1 间接给出：该地址**被写**，故「只被读」不成立。

已排除项之外，以下 4 问**必须**在 Windows + 提权下才能定论。**每问都给出最小实验，不需要新写探针**——`_re/ghidra/` 已有全部工具。

### Q1（最高优先）— `0x1dd16a0` 到底有没有被写过？

**这是唯一能分离 H2 与 H3/H4 的实验。**

改动最小化方案：在 `hwbp_data.py` 的 `set_hwbp` 之后、`WaitForDebugEvent` 循环之前（或循环本身上加一个 `else` 分支），对 `main_base + WATCH_DATA[0]` 做**周期性 `rpm` 读**并记录首末值，运行 40 秒。

- 若该 4 字节**从初值变为非初值** → 它**被写过**，而写断点没捕获 → **H4/机制问题**（`LEN0`/对齐/槽编码）。
- 若该 4 字节**全程未变** → `createModuleConstants()` **没有**写它（可能走了缓存路径/该模块未初始化） → **H2 成立，0 命中是正确结果**。

### Q2 — 换一个**已知会被写**的地址做正对照。

用样本自身会写的地址（例如某个必然被每帧更新的计数器/句柄字段，或直接在探针里对目标进程 `WriteProcessMemory` 写一次 `main_base + WATCH_DATA[0]`）验证**写断点本身能用**。

- 命中 → 写断点机制正常，Q1 的结论可采纳。
- 不命中 → **写断点编码确有缺陷**，H4 升级为主因，须重新审视 `LEN0 = 0b11` 与对齐约束。

**这一问是本次查证留下的最大缺口**：现有证据**无法排除"H4：写断点编码本身设不对"**，因为 `hwbp_data` 从未有过一次正命中。H3 与 H4 之间**必须**靠实测分离。

### Q3 — GD 位在本机 CPU/OS 上的真实语义。

本机 CPU 已查明为 **AMD Ryzen 7 7800X3D**（`grep -m1 'model name' /proc/cpuinfo`），宿主为 **Windows 10.0.26200.6584**（`cmd.exe /c ver`）；本会话运行在 **WSL2**（`uname -a` → `6.18.33.2-microsoft-standard-WSL2`）。

**已知的边界**：Ryzen 7000 是 `Zen 4` 微架构，其 `DR7.GD` 的实现细节（尤其"GD=1 时 `DRn` 读是否在**用户态**也触发 `#DB`、以及是否与虚拟化/SVM 交互"）**在手册之外存在实现差异**。要定论需：

- 在 Windows 原生（非 WSL）下，用 `GetThreadContext`/`SetThreadContext` 构造 `GD=1` 的最小程序，观察 (a) `SetThreadContext` 是否成功、(b) 随后 `GetThreadContext`/`DRn` 读是否 `#DB`、(c) 断点是否仍命中。
- **这恰是工单 01 要求的"用证据而非照搬手册"的那一步。**

**但**：**无论 Q3 结论如何，都不改变本文件 §1–§5 的结论**——因为本实现的 `GD` 恒为 0，Q3 的答案只影响"未来若采用 `gd=True` 修正路径，行为会怎样"，不影响任何既有观测。

### Q4 — `mod_consts` 是否只被读、不被写（H3 的直接检验）。

对目标页做**页保护断点**（`probe_lib.py` 的既有机制，能捕获读）而非数据断点，观察该页是否被访问、以何种方式。这能独立确认 H3。

---

## 8. 建议的正文修订（供逆向主线采纳，本文件不代为执行）

| 文件 | 位置 | 建议修订 |
| --- | --- | --- |
| `_re/ghidra/dr7_forensics.md` | GD 括注（`grep -n 'GD' dr7_forensics.md` 定位） | 把"读 Dr7 需置 1 才能让数据断点生效"改为："`GD`(bit13) 控制 `DRn` 的**读保护**；本组四份实现均通过 `& ~0xFFFFFFFF` 把 bit13 清 0，故 **`GD` 在本实现下恒为 0，无法解释任何观测差异**。" |
| `docs/adr/0002-...md` | §背景缺陷 2 / §未决 1 | 追加一行：缺陷 2 已查证，**对本实现族为空假设**（见 `.scratch/probe-arch-refactor/findings-dr7-gd.md`）。ADR 的**决策不变**（保留缺陷 + 逐位等价）。 |
| `_re/ghidra/probe_lib.py` | `parse_dr7` docstring 的 `gd` 条目 | 按 §6.2 补一句"现存路径下 GD 恒为 0"。 |

**修订纪律**：以上均为**追加说明 + 正文改到一致**，不做静默改写（`docs/agents/domain.md` §"On correcting an issue"）。

---

## 9. 漂移登记表条目（供 `docs/agents/domain.md` 追加）

**漂移登记表须追加以下三行**（`docs/agents/domain.md` 的表格为两列 `Claim` / `Status` / `Correct position` 之外另有 `Where it lived` 列，按其既有列序照抄）。因本文件不代为执行修订，正文以代码块交付，可直接粘贴。

```markdown
| Data breakpoints in `hwbp_data.py` may never have taken effect because the code never sets `GD` (bit13) | `docs/adr/0002-*.md` §背景缺陷 2 / §未决 1; issue `01` 问题段; `_re/ghidra/dr7_forensics.md` GD 括注 | **Corrected 2026-09-17** | `GD` is cleared to 0 before every write-back, in all four implementations: each does `dr7 &= ~0xFFFFFFFF`, and bit13 (`0x2000`) sits inside that mask. So `hwbp_data.py`'s `Dr7` is always `0xd0001` **whatever the incoming value** — `GD` is a *null* hypothesis here, not a wrong bit. The asserted consequence ("GD=0 makes the DR7 write ineffective") cannot be produced by this code. Why the write-breakpoint log shows **0 hits** is still open among three live explanations: (H2) the watched address was never written inside the 40 s window, (H3) the access was a *read* and hardware write breakpoints do not fire on reads, (H4) the encoding never armed. H3 and H4 are **not yet separated** — `hwbp_data.py` has never produced a single positive hit, so no positive control for write breakpoints exists. See `.scratch/probe-arch-refactor/findings-dr7-gd.md`. |
| `hwbp_data.py`'s historical logs carry a hit count whose provenance must be explained | issue `01` 问题 2 | **Disproved (premise false) 2026-09-17** | There is no hit count to explain. `grep -c 'DW HIT' hwbpData_d1.txt hwbpData_wa.txt` returns `0` and `0`; both logs are 327/313 bytes and end at `命中总数: 0`. The premise "if the breakpoint never armed yet the log shows hits" does not hold. |
| `hwbp_data.py`'s two logs come from one code generation | Implied by any old/new log comparison over this script | **Corrected 2026-09-17** | They come from two. `hwbpData_d1.txt`'s summary heading is `-- 属性名 x 调用者 频次 --`; `hwbpData_wa.txt`'s is `-- 写入者频次 --`, which matches the current file's `L("-- 写入者频次 --")`. Both show 0 hits so the finding is unaffected, but a future diff must not treat them as one generation. |
```

---

## 10. 证据索引（全部可复现）

工作目录 `_re/ghidra/`：

```
grep -n '~0xFFFFFFFF' hwbp16b.py hwbp_ctrl.py hwbp_data.py hwbp16.py
grep -n 'WATCH_DATA' hwbp_data.py hwbp_ctrl.py
grep -n 'DW HIT' hwbp_data.py
grep -c 'DW HIT' hwbpData_d1.txt hwbpData_wa.txt
grep -c 'DW HIT' hwbpCtrl_p1.txt
grep -rln 'DW HIT' .
grep -n 'hwbp' run16_round3.bat run16_round4.bat run16b_elevated.bat
grep -n 'set_hwbp(' *.py
grep -n '写入者频次\|属性名 x 调用者 频次' hwbp_data.py
git diff --stat HEAD -- hwbp_data.py hwbp_ctrl.py hwbp16b.py
git log --oneline -3
```

工作目录 `FucKeySteam/`：

```
grep -rn 'hwbp' docs/
gh api repos/Drivpe/FucKeySteam
grep -n 'DR7_GD_BIT\|gd=None' "../KeySteam v2.99/_re/ghidra/probe_lib.py"
```

位运算推演（Linux，纯计算，**不 import `probe_lib.py`**）见 §1 E2 与 §1 E7。
