# kd3 运行时实证：推翻两处既有记载

**时间**：2026-09-18 12:03
**产物**：`_re/ghidra/keyDump_kd3.txt`（562,622 B，500 次命中）
**运行**：`RUN probe=key_dump tag=kd3` / `EXIT code=0 elapsed=40.14s` / `priv=True`

---

## 0. 一句话结论

**`_hash_machine_parts` 入口确证无误；但既有的「入参寄存器约定」记载把两个不同的调用现场混为一谈，且 500 次命中实为同一次命中的重复记录，不是 500 次调用。**

---

## 1. 确证成立的部分

| 项 | 结论 | 证据 |
| --- | --- | --- |
| 断点地址 | RVA `0x12ded90` 正确 | 运行时 `bp=0x7ff950deed90` − `main_base=0x7ff94fb10000` = `0x12ded90`，与静态 VA `0x1812ded90` 精确对齐 |
| 函数入口 | `0x1812ded90` 是完整函数入口 | `ksdis.py` 反汇编：`push rsi/rdi/r12/r13/r14/r15` + `sub rsp,0x48`，标准 prologue |
| `main.dll` 身份 | 与静态分析同一份 | `sha256 = cc869941663ed46bc8973bc18415d2cabd6e6fe7127a7d692fda450cdc405265`，与交接文档 §5 基线逐字节一致 |
| 启动方式 | `kshost.exe` + `D:\ks_debug\main.dll` | 零命中修正为 `kshost.exe` 后，`MAIN.DLL base=` 在 `@0.011s` 立即出现 |

---

## 2. 推翻记载之一：入参寄存器约定

**既有记载**（`最快路径研究.md` §10.1）：
```
0x1812de9b3  mov r14, rax        ; 4 元组（call 0x1814106c0 建）
0x1812debeb  mov edi, 0x27       ; CALL_FUNCTION
0x1812debf0  mov r8, r14         ; ★ r8 = 元组指针（args）
0x1812debf3  mov rdx, r12        ;     rdx = 函数对象
0x1812debfc  call 0x181415b00    ; Nuitka Python 调用分发器
```
⇒ 记载结论：「承载入参的是 `r8`，不是 `rdx`」。

**实测推翻**：上述序列是**调用点**（`0x1812debf0`，**经分发器 `0x181415b00`**）的现场，其寄存器约定**不等于函数入口**的约定。两者相差一次函数调用。

**函数入口的真实语义**（`ksdis.py` 实测）：
```
0x1812ded90  push rsi/rdi/r12/r13/r14/r15
0x1812ded9b  sub rsp, 0x48
0x1812deda8  mov r14, qword ptr [r8]      ← r8 被**解引用**，r8 是"参数块"指针
0x1812dedab  mov rdi, rcx
0x1812dee27  mov rax, qword ptr [r14+8]   ← 读 ob_type（+0x8）
0x1812dee2b  mov rcx, r14                 ← rcx = 该 PyObject
0x1812dee35  mov rdx, qword ptr [rax+0xd8]← 从 type+0xd8 取 tp_ 方法槽
0x1812dee41  call rdx
```
⇒ **`r8` 本身不是 PyObject**，它指向调用者栈上的参数数组；**真正的对象在 `[r8]`**。

### 2.1 调用点的完整链路（新增确证）

kd3 栈上 `[rsp+0x00] = 0x00007ff950f25b70` 是返回地址，RVA = **`0x1415b70`**。反汇编该处：

```
0x181415b00  mov qword ptr [rsp+0x18], r8   ← 分发器入口立即保存调用者的 r8
0x181415b05  push rbp/rbx/rsi/rdi/r12/r13/r14/r15
0x181415b11  sub rsp, 0x58
0x181415b15  lea rbp, [rsp+0x30]
0x181415b50  mov ecx, dword ptr [rdx+0x40]
0x181415b53  cmp rcx, 1                     ← 参数个数分支
0x181415b63  lea r8, [rbp+0x80]             ← 重建 r8 = 指向栈上参数数组
0x181415b6a  mov rcx, r13
0x181415b6d  call qword ptr [rdx+0x78]      ← 间接调用 _hash_machine_parts
0x181415b70  jmp 0x1814164cc                ← 返回点（与栈上返回地址吻合）
```

⇒ 4 元组**作为单个参数**（`cmp rcx, 1`）传入；`[r8]` 即那个元组，kd3 中为 `0x19a6f1218c0`（堆地址）。

---

## 3. 推翻记载之二：500 次命中的真实性

**观察**：
- `rip` 唯一值 = **1**（全部 `0x7ff950deed90`）
- `r8`/`r9`/`rsp` 唯一值 = **1**（全部 `0x45035fa7e0` / `0x3` / `0x45035fa728`）
- 16 槽栈快照唯一值 = **1**（500 份完全相同）
- 时间戳全部落在 **2.744s–2.897s**（0.153 秒内）

**判定**：这是**同一处指令被反复触发**，而非 500 次独立调用。真实调用必然改变寄存器与栈。

**根因**：硬件执行断点命中后必须**写回上下文**，否则 `ContinueDebugEvent` 会再次触发同一条指令。必要位：
- `TF` = bit 8 = `0x100`（单步陷阱）
- `RF` = bit 16 = `0x10000`（resume flag，**抑制同指令重触发**）

**归属**：`key_dump.py` 的写回被两轮改动来回摇摆 —— 先被放进 `hits < MAX_LOG_HIT` 守卫内（配额满即失效），后被整段删除（理由「hwbp 系脚本也不写回」）。**该理由不成立**：`hwbp16b_wb.txt` 的 `caller` 亦有 31 次同值重复，属同一缺陷，只是其断点地址执行频率低、表现不显。

已在 kd4 版恢复并修正为 `ctx.EFlags &= ~(0x100 | 0x10000)` 后 `SetThreadContext`。

---

## 4. 副产品：`rdx` 的身份

kd3 中 `rdx = 0x19a6eaf6840`，500/500 次：
- `refcnt = 0x1`（合法 PyObject）
- `type = 0x7ff95185e1c0`，RVA = `0x1d4e1c0`，落在 **`.data`**
- `size = 0`

⇒ `rdx` 指向 Nuitka 在 `.data` 里的**静态类型对象/共享空元组**，非 items 容器。这与「`rdx` 是函数对象」的旧记载**方向一致但机制不同**：它是**被调用对象的类型/函数对象**，与 `[r8]` 参数块分离。

---

## 5. 下一轮（kd4）的判据

| 若观察到 | 则 |
| --- | --- |
| 500 次命中时间戳**均匀铺开**、寄存器**逐次变化** | 写回修复生效，命中转为独立调用 ⇒ 可读 4 元组 |
| 仍挤在 0.15s 内、寄存器恒同 | 写回未生效 ⇒ 改走 `DR7` GE/LE 全局精确断点 |
| `r8->[0]` 段出现 `itemA/itemB` 字符串 | 拿到 `platform`/`socket` 属性名 ⇒ 密钥可复现 |
| `r8->[0]` 仍 `size` 异常 | 需改用「先解引用再按 PyUnicode 读」的口径（kd4 已加 `self-as-str`） |

kd4 的 `dump_tuple` 已放宽：不再因 `size > 20` 提前返回，改为先试 `read_pystr` 再按两种元组口径解析。

---

## 6. 参考

- 产物：`_re/ghidra/keyDump_kd3.txt`（562,622 B）
- 运行日志：`_re/ghidra/_elev_run.log` 第 12:02:49 `RUN` / 12:03:29 `EXIT code=0 elapsed=40.14s`
- 反汇编工具：`_re/ghidra/tools/ksdis.py`（capstone）
- 既有记载：`.scratch/keysteam-no-verification/最快路径研究.md` §10.1、§10.2
