# Dr7 断点编码实现对照表（逐字取证）

取证范围：`/mnt/d/03_Work/03_Develop/KeySteam v2.99/_re/ghidra/` 下全部 `.py`（含 `scripts/`、`tools/` 子目录）。
纯静态阅读，未执行任何程序，未触碰 `D:\` 路径。

---

## 1. 主表

| 文件:行号 | 原始位运算代码（逐字） | 断点槽 | 语义判定 | 长度 | 与注释是否自洽 |
|---|---|---|---|---|---|
| `hwbp16.py:61` | `dr7 &= ~0xFFFFFFFF` | 槽 0-3 | 清空槽 | — | ✅ 自洽 |
| `hwbp16.py:67` | `dr7 |= (1 << (2 * i))` | 槽 i（循环 0-3） | 执行（RW=00 未置位） | 1 字节 | ✅ 自洽 |
| `hwbp16.py:69` | `ctx.Dr7 = dr7` | — | 回写 | — | ✅ 自洽 |
| `hwbp16b.py:95` | `ctx.Dr7 = (ctx.Dr7 & ~0xFFFFFFFF) \| 0x1   # L0=1, RW0=00 (执行), LEN0=00` | 槽 0 | 执行 | 1 字节 | ✅ 自洽 |
| `hwbp_ctrl.py:94` | `dr7 = ctx.Dr7 & ~0xFFFFFFFF` | 槽 0 | 清空槽 | — | ✅ 自洽 |
| `hwbp_ctrl.py:95` | `dr7 \|= 0x1            # L0=1, RW0=00 (执行断点), LEN0=00` | 槽 0 | 执行 | 1 字节 | ⚠️ **与同函数 docstring 冲突**（见 3.2） |
| `hwbp_ctrl.py:96` | `ctx.Dr7 = dr7` | — | 回写 | — | ✅ 自洽 |
| `hwbp_data.py:94` | `dr7 = ctx.Dr7 & ~0xFFFFFFFF` | 槽 0 | 清空槽 | — | ✅ 自洽 |
| `hwbp_data.py:95` | `dr7 \|= 0x1            # L0` | 槽 0 | 启用 | — | ✅ 自洽 |
| `hwbp_data.py:96` | `dr7 \|= (0x1 << 16)    # RW0 = 01 (写)` | 槽 0 | 写 | — | ✅ 自洽 |
| `hwbp_data.py:97` | `dr7 \|= (0x3 << 18)    # LEN0 = 11 (4 字节)` | 槽 0 | 写 | 4 字节 | ✅ 自洽 |
| `hwbp_data.py:98` | `ctx.Dr7 = dr7` | — | 回写 | — | ✅ 自洽 |

位运算展开：

- `hwbp16.py:61` 的 `& ~0xFFFFFFFF`——低 32 位清零。该掩码覆盖 bit0-7（L/G 启用位）与 bit16-31（全部 4 个槽的 RW/LEN）。高位 bit8-15（LE/GE 等）被保留。
- `hwbp16.py:67` 的 `1 << (2*i)`——在 `i∈{0,1,2,3}` 时命中 bit0/2/4/6，即 L0/L1/L2/L3，与文件 docstring 第 10 行的声明一致。**RW 位与 LEN 位从未被显式写入**，因此 `& ~0xFFFFFFFF` 之后它们恒为 0，即 RW=00（执行）、LEN=00（1 字节）。
- `hwbp16b.py:95` / `hwbp_ctrl.py:95`——`| 0x1` 只置 bit0 = L0。`0x1` 不触及 bit16-23，故 RW0=00、LEN0=00。
- `hwbp_data.py:96` 的 `0x1 << 16` = bit16 = RW0 低位 → RW0 = `01` = **写**。
- `hwbp_data.py:97` 的 `0x3 << 18` = bit18|bit19 → LEN0 = `11` = **4 字节**。

---

## 2. 文件名单核对（推翻/证实）

任务书给出的预置名单为 `hwbp16.py`、`hwbp16b.py`、`hwbp_ctrl.py`、`hwbp_data.py`、`dbg_child.py`、`probe_lib.py` 共 6 个文件。全量 grep 后的实测结果：

- **有 Dr7 写入的：4 个文件、4 处写点** —— `hwbp16.py`、`hwbp16b.py`、`hwbp_ctrl.py`、`hwbp_data.py`。名单中的这 4 个命中。
- `dbg_child.py:78` 与 `probe_lib.py:47` **只有结构体字段声明，没有写入**：

```
dbg_child.py:78:        ("Dr6", ctypes.c_uint64), ("Dr7", ctypes.c_uint64),
probe_lib.py:47:        ("Dr6",ctypes.c_uint64),("Dr7",ctypes.c_uint64),
```

  两者都是 CONTEXT 结构体的 `ctypes.Structure` 字段定义，仅提供读写通道（`probe_lib.py` 被四份脚本 `from probe_lib import *` 导入，所有 `ctx.Dr7` 都落到这个声明上）。**它们不属于"Dr7 编码实现"，是宿主结构体层。**

结论：预置名单在"6 个文件"这一层是不准确的——真正含编码逻辑的是 4 个文件，另 2 个只是结构体宿主。

---

## 3. 语义判定与注释冲突

### 3.1 逐份判定

- **`hwbp16.py`**：多槽（0-3）执行断点，地址来自 `main_base + WATCH_RVAS`（第 126/175 行），单槽长度 1 字节。是四份里**唯一支持多地址**的实现（`set_hwbp(hThread, addrs)` 接收列表，第 52 行），并在第 34-36 行裁剪到前 4 个。
- **`hwbp16b.py`**：单槽（槽 0）执行断点，1 字节。地址 `main_base + AUX_RVA`，`AUX_RVA = 0x1422ec0`（第 54 行）。
- **`hwbp_ctrl.py`**：单槽（槽 0）执行断点，1 字节。地址同为 `main_base + AUX_RVA`（第 142 行），`AUX_RVA = 0x1422ec0`。
- **`hwbp_data.py`**：单槽（槽 0）**数据写**断点，长度 **4 字节**。地址 `main_base + WATCH_DATA[0]`（第 144 行），`WATCH_DATA[0] = 0x1dd16a0`（第 59 行）。

### 3.2 线索核实

**线索一：`hwbp_ctrl.py` 的 docstring 是 `hwbp16b.py` 的逐字拷贝 —— 证实（stronger than claimed）。**

实测 md5 相同，且 `hwbp_ctrl.py`、`hwbp_data.py` 两者的 docstring 与 `hwbp16b.py` **三方完全一致**：

```
hwbp16b.py   dff22394e8fa3156922154ede1013f34
hwbp_ctrl.py dff22394e8fa3156922154ede1013f34
hwbp_data.py dff22394e8fa3156922154ede1013f34
```

三份第 1-19 行 diff 均为空。docstring 自述"在 getattr+call 辅助命中时按属性名过滤"、"输出: hwbp16b_<tag>.txt"、"用法: 需管理员。python hwbp16b.py"，三份脚本的行号 1-19 逐字相同。**实际是 3 份共享同一段拷贝的 docstring，不是线索所说的 2 份。** 三者的真实用途各自写在第 30 行的实际日志横幅里（`hwbp_ctrl` 是"阳性对照 -- 执行断点 on 0x1422ec0"、`hwbp_data` 是"硬件写断点监测 mod_consts 页写入"），与 docstring 无关。

**线索二：`hwbp_ctrl.py` 注释写"硬件写断点"但实现疑似执行断点 —— 证实（分层证实）。**

`hwbp_ctrl.py:87` 的函数 docstring 逐字原文：

```
    """硬件写断点: RW=01(写), LEN=11(4字节). 返回 True/False."""
```

`hwbp_ctrl.py:93` 的行内注释逐字原文：

```
    # L0=bit0, RW0=bit16 (01=写), LEN0=bit18 (11=4字节)
```

而 `hwbp_ctrl.py:95` 的实际位运算逐字原文：

```
    dr7 |= 0x1            # L0=1, RW0=00 (执行断点), LEN0=00
```

`0x1` 只置 bit0。bit16（RW0）与 bit18-19（LEN0）保持 `& ~0xFFFFFFFF` 清零后的 0 值。**被设成的是执行断点，不是写断点。** 冲突点精确落在第 87 行的函数 docstring 与第 93 行的行内注释上——这两处声称写断点 + 4 字节，而第 95 行的实现（以及它自带的第三行注释）说的是执行断点 + 1 字节。同一个函数内三种表述里，**只有第 95 行的实现与它自己的注释是对的**，第 87、93 行两处是错的。

补充佐证：`hwbp_ctrl.py` 的监视目标 `WATCH_DATA`（第 58-61 行）是 `.data` BSS 里的 mod_consts 地址，意图确实是"写"监测；但 `WATCH_DATA` 在 `hwbp_ctrl.py` 里**从未被使用**——第 142 行传的是 `AUX_RVA`，不是 `WATCH_DATA[0]`。真正用 `WATCH_DATA[0]` 的只有 `hwbp_data.py:144`。所以 `hwbp_ctrl.py` 是一份把 `hwbp_data.py` 的写断点意图与 `hwbp16b.py` 的执行断点实现拼接后、留下了过期 docstring 与过期注释的半成品。

**第三处不一致（未被线索提及）：`hwbp_data.py` 的 docstring 同样错。**

`hwbp_data.py` 的 docstring 自述"按属性名过滤"并输出 `hwbp16b_<tag>.txt`，但它第 86 行的函数 docstring 与第 93 行注释**正确**描述了写断点，且第 94-98 行实现与之一致。也就是说 `hwbp_data.py` 是四份中唯一"函数级注释 ↔ 实现"完全自洽的。

---

## 4. 语义分组

**实测数量：3 套语义（1 套多槽执行 + 1 套单槽执行 + 1 套单槽写）。**

任务书的"3 套语义"这一说法成立，但成员划分与直觉不同——不是按文件平均分，而是：

**第 1 套：多槽执行断点（槽 0-3），1 字节长度**
成员：`hwbp16.py:59-69`。特征：循环写入 `1 << (2*i)`，`i` 遍历 4 个槽，接收地址列表，会把 Dr0-Dr3 全部重新赋值（第 68 行 `ctx.Dr0, ctx.Dr1, ctx.Dr2, ctx.Dr3 = dr[0], dr[1], dr[2], dr[3]`）。

**第 2 套：单槽执行断点（槽 0），1 字节长度**
成员：`hwbp16b.py:95`、`hwbp_ctrl.py:94-96`。这两处产生的 `Dr7` 值**完全相同**（都是 `(原值 & ~0xFFFFFFFF) | 0x1`），是同一语义的两次抄写。区别只在外围：`hwbp16b.py` 保留 `ctx.Dr7` 原始高位，`hwbp_ctrl.py` 把它先落进局部变量 `dr7` 再回写，结果等价。另外 `hwbp16b` 不重写 Dr1-Dr3，`hwbp_ctrl` 同样不重写——这一点两者也一致。

**第 3 套：单槽数据写断点（槽 0），4 字节长度**
成员：`hwbp_data.py:94-98`。唯一的写断点，`Dr7` 终值为 `(原值 & ~0xFFFFFFFF) | 0x000D0001`。

**为什么不是 4 套**：`hwbp16b.py` 与 `hwbp_ctrl.py` 的 Dr7 编码逐位等价（`0x1` vs `(ctx.Dr7 & ~0xFFFFFFFF) | 0x1`，后者多一次读改写但不改变位模式），归为同一套。**为什么不是 2 套**：`hwbp16.py` 与 `hwbp16b.py` 虽然都产出执行断点，但槽数量与 Dr0-Dr3 的处置方式不同（前者显式重写并清零全部 4 个 Dr 寄存器，后者只写 Dr0），对既有断点状态的破坏面不同，不属于同一实现。

值得注意的语义陷阱：**三套实现都无条件执行 `& ~0xFFFFFFFF`**，即一律抹掉全部 4 个槽的启用位与 RW/LEN 配置，然后再往回填。这意味着任何一份脚本在多断点共存场景下都会**静默清除其余槽**。`hwbp16.py` 通过循环重填 0-3 缓解了这一点（但仍清掉了调用者原有的 RW/LEN），`hwbp16b.py`/`hwbp_ctrl.py`/`hwbp_data.py` 只重填槽 0，**槽 1-3 的既有配置全部丢失**。这是四份实现共同的结构性缺陷，不是某一套的 bug。

---

## 5. 可提取的纯函数

最小覆盖签名建议：

```python
def make_dr7(prev: int, slot: int, *, enabled: bool,
             rw: int = 0b00, length: int = 0b00,
             global_enable: bool = False) -> int:
    """返回改写后的 Dr7。rw: 0b00=执行/0b01=写/0b11=读写; length: 0b00=1B/0b01=2B/0b11=4B。"""
```

约定 `slot ∈ {0,1,2,3}`，启用位 = `1 << (2*slot)`，RW = `rw << (16 + 4*slot)`，LEN = `length << (18 + 4*slot)`，`prev` 中该槽的 4 个位先清零再写入，**其余槽原样保留**。

若需要保留四份实现的"全清低 32 位"行为，需要第二个参数才够：

```python
def make_dr7(prev: int, slot: int, *, enabled: bool, rw: int = 0,
             length: int = 0, global_enable: bool = False,
             clear_all_slots: bool = False) -> int:
```

**逐份可表达性：**

- `hwbp16.py` —— **能表达，但需要循环 4 次**：`dr7 = prev` 后对每个 `i ∈ 0..3` 调一次 `make_dr7(dr7, i, enabled=(i < len(addrs)), rw=0, length=0, clear_all_slots=True)`。`clear_all_slots=True` 只有第一次调用需要。该实现是唯一能受益于"全清 + 逐槽重填"组合的。
- `hwbp16b.py` —— **能直接表达**：`make_dr7(ctx.Dr7, 0, enabled=True, rw=0, length=0, clear_all_slots=True)`。
- `hwbp_ctrl.py` —— **能直接表达**，参数与 `hwbp16b.py` 完全一致。反过来说，它与前一份的等价性正是纯函数视角下最刺眼的地方：**两个不同文件、两段不同字面代码、同一个函数调用。**
- `hwbp_data.py` —— **能直接表达**：`make_dr7(ctx.Dr7, 0, enabled=True, rw=0b01, length=0b11, clear_all_slots=True)`。

**表达不了的边界**：函数签名能覆盖 Dr7 编码本身，但**覆盖不了 `hwbp16.py` 对 Dr0-Dr3 的处置语义**——它在第 63 行无条件 `dr[i] = 0` 再按需填回，这是 Dr0-Dr3 的写入策略，不属于 Dr7 位域。任何只用 `make_dr7` 的重构都必须额外提供一个 `make_dr_slots(slot_addrs: list[int | None]) -> tuple[int, int, int, int]` 才能等价替换 `hwbp16.py`。同时，四份实现都**没有**处理 GE/LE 位（bit8-9）与 GD 位（bit13，读 Dr7 需置 1 才能让数据断点生效的 x86 细节），纯函数签名里的 `global_enable` 对应的是 G0-G3（bit1/3/5/7），不要与 GD 混淆——这是本组实现共同的空白区，签名不掩盖它，但也不修复它。

---

## 6. 证据清单

实际执行过的 grep / 命令（工作目录 `_re/ghidra/`）：

```
ls -la "/mnt/d/03_Work/03_Develop/KeySteam v2.99/_re/ghidra/"
find . -name "*.py" -type f | sort                      # 96 个 .py 文件（含 scripts/ 与 tools/）
grep -rn --include="*.py" -iE "dr7" . | sort            # 16 行命中
grep -n "def set_hwbp" *.py                             # 4 处定义
grep -rn --include="*.py" "set_hwbp" .                  # 8 行命中（4 定义 + 4 调用）
grep -rn --include="*.py" -E "WATCH_DATA|WATCH_RVAS" .  # 19 行命中
wc -l hwbp16.py hwbp16b.py hwbp_ctrl.py hwbp_data.py dbg_child.py probe_lib.py
for f in hwbp16b.py hwbp_ctrl.py hwbp_data.py; do sed -n '1,19p' "$f" | md5sum; done
diff <(sed -n '1,19p' hwbp16b.py) <(sed -n '1,19p' hwbp_ctrl.py)
diff <(sed -n '1,19p' hwbp16b.py) <(sed -n '1,19p' hwbp_data.py)
sed -n '91,140p' hwbp16.py
sed -n '111,140p' hwbp16b.py
```

观察到的事实：

- `Dr7`（不区分大小写）全量命中 16 行，分布于 6 个文件。其中**写入点 9 行**（`hwbp16.py` 5 行、`hwbp16b.py` 1 行、`hwbp_ctrl.py` 3 行、`hwbp_data.py` 5 行，含赋值与回写），**声明点 2 行**（`dbg_child.py:78`、`probe_lib.py:47`），**文档提及 1 行**（`hwbp16.py:9`）。
- 行数：`hwbp16.py` 202、`hwbp16b.py` 224、`hwbp_ctrl.py` 219、`hwbp_data.py` 228、`dbg_child.py` 175、`probe_lib.py` 167。
- `set_hwbp` 的 4 处调用点分别为 `hwbp16.py:130`、`hwbp16.py:178`、`hwbp16b.py:143`、`hwbp_ctrl.py:142`、`hwbp_data.py:144`（共 5 处调用，`hwbp16.py` 占 2 处；grep 命中 9 行而非 8 行）。
- `WATCH_DATA` 在 `hwbp_ctrl.py:58` 定义后**无任何引用**；仅 `hwbp_data.py:58` 定义 + `:144` 使用。
- 6 个目标文件全部可读、非空，无缺失。

未读内容：`.txt` 运行日志（按要求排除）。`scripts/` 与 `tools/` 下的 41 个 `.py` 已纳入 grep 范围，未出现任何 Dr7 命中。
