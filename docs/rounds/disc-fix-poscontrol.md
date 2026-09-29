# disc.py 静默 fallback 修复 + 阳性对照（#19 AC3）

**日期**：2026-09-17
**对象**：`_re/ghidra/disc.py`
**验证深度**：静态半 = 直接观测（从原样本实时解析）；运行期半 = 未执行（见下「限制」）

## 一、缺陷确认（直接观测）

原代码两处构成静默 fallback：

```python
# 原 :31-32
if MODE=="many": funcs=load_funcs()
else:            funcs=None
# 原 :83
a = main_base+funcs[0][0] if funcs else main_base+0x1000
```

`mode=="one"` 走 `else` → `funcs is None` → **必然**取 `main_base+0x1000`。
即「one 组」写的不是「main.dll 第一个函数入口」，而是一个魔数地址。

**物证**：既有运行记录 `disc_one.txt` 写：
```
wrote 1 INT3 @0x7ff902f21000
```
`main.dll` 基址 `0x7ff902f20000` ⊕ `0x1000` = `0x7ff902f21000` —— 正是魔数地址。

## 二、修复

`funcs` 改为无条件加载，并在 `one`/`many` 下显式断言非空；空表**大声失败**（exit 2），
不再退化为魔数地址。写入点改为显式 `a = main_base+funcs[0][0]`。

## 三、阳性对照

### 静态半（已执行，直接观测）
从原样本实时解析 `.pdata`（`tools/binlib.py` 口径，与 `rederive.py` 同源）：

- `.pdata` 函数数 = **17863**
- `funcs[0] = (0x1000, 0x101a)`，长度 26 字节
- 该 VA 处字节可反汇编为合法指令序列：`push rdi` / `sub rsp, 0x20` /
  `cmp qword ptr [rip + 0x1d5b932], 0` / `mov rdi, rcx` —— 是真实函数序言

### 关键限定（避免过度声称）
**在本样本上 `funcs[0][0] == 0x1000`，与旧 fallback 的魔数 `0x1000` 数值相同**
（因为 `.text` 起点 RVA 就是 `0x1000`，而首函数恰好从 .text 起点开始）。

推论：上一轮 `disc_one` 实验的**结论未被污染** —— 它写的地址在数值上
确实等于「main.dll 第一个函数入口」。

但这是**巧合而非设计**：
- 旧写法是**魔数常量**，不随样本/版本更新；
- 新写法从 `.pdata` 读**真实首函数入口**，样本一变即随之变。

故本缺陷的正确定性是「**可掩蔽的逻辑缺陷**」：在 `.pdata[0]` 恰为 `.text` 起点的
样本上，错误值与正确值撞车；换一个首函数不在 `.text` 起点的样本即暴露。
审查记录称「三组对照的科学前提被破坏」——就**逻辑**而言成立，就**本样本的实测值**
而言未造成污染。两句话都保留。

### 运行期半（未执行）
本脚本依赖 `ctypes` 调 Win32（`CreateProcessW` / `WriteProcessMemory` /
`WaitForDebugEvent`），**在 Linux 侧无法执行**。修复后的 `disc.py` 已写入
阳性对照逻辑：

- `posctl.pre_bytes` —— 写入前读 16 字节，证明是代码而非空白
- `posctl.aligned_to_pdata_entry` —— 该 RVA 是否与 `.pdata` 条目精确对齐
- `posctl.expect_cc` / `actual` —— 读回验证是否真的写进了 `0xCC`
- `posctl.BP_HIT` —— 在该地址捕获到 `EXCEPTION_BREAKPOINT`
- `posctl.VERDICT` —— `PASS` 当且仅当 `bp_hit`，即「所写地址确实被执行」

**待办（需 Windows + 管理员）**：运行
`Start-Process -Verb RunAs python.exe disc.py one`
后，把 `disc_one.txt` 的 `posctl.VERDICT=PASS` 一行贴回本文件，
运行期半即闭环。当前该半为**未执行**，不得声称已验证。

## 四、检索词表（docs/agents/domain.md:86）

定位本缺陷时检索的词/模式：`funcs` / `funcs[0]` / `0x1000` / `MODE=="one"` /
`MODE=="many"` / `load_funcs` / `disc_one.txt` / `wrote 1 INT3`。
（`grep -n "funcs" disc.py`、`grep -n "0x1000" disc.py`、
`grep -n "wrote 1 INT3" *.txt`）
