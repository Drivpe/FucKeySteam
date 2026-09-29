# F 线 — 修补构造与验收（r41）

**日期**：2026-09-27
**成品**：`D:\r41_iso\F\KeySteam_r41_final.exe`（md5 `17938995b932a9e2c6a1e33d93195601`，与 `D:\ks_debug\r41\F\` 同源）
**基线**：`KeySteam.exe` md5 `01560c951afd1ce35350ea86a58c1989`；`main.dll.orig` md5 `2948792df5b1484a426580927abb0882`

---

## 0. 结论摘要

用户报的两个症状，第一个（「验证已过期」）**已定位到字节级根因并修复**。根因不是"闸门改得不够"，而是 **r40 的 P2 补丁主动把控制流推向了抛出该文案的分支**。

| 项 | 结果 |
|---|---|
| 补丁数 | **3 处 / 14 字节**（全部函数内分支改写，无入口桩） |
| 成品内嵌 `main.dll` | md5 `17f981137d2549bb576eaf87a7f469b7` |
| `diff_outside_patches` | **0**（差异集合 == 声明补丁集合，逐字节反查确认） |
| footer `body_sha256` | 重算一致 `c0c968ed…` |
| exe 长度 | 30,885,138 B，与原始等长 |
| 310 秒实测 | **112/112 帧存活；可见顶层窗口仅主窗口本身；零门禁关键词；主窗口全程 `en=True`/`blocked=False`** |
| 用户路径 | 7 菜单 + 5 工具栏 + 搜索输入 + 3 列表点选，**20 次点击零弹窗** |

---

## 1. ★ 根因：r40 的 P2 是反向的（决定性发现）

### 1.1 `_verification_gate_allows` 尾段真实指令流

从函数入口 `0x180fe8280` 严格线性解码（避免失步）：

```
0x180fe8534  je   0x180fe864a     ; 票据对象构建失败 → 放行
0x180fe8561  call [rdx+0x30]
0x180fe8564  test r14, r14
0x180fe8567  je   0x180fe864a     ; r14==NULL       → 放行（rax=rbp=NULL）
0x180fe856d  cmp  dword [r14], 0
0x180fe8571  mov  rbx, [0x18143db38]   ; Py_None
0x180fe858d  cmp  r14, rbx
0x180fe8590  je   0x180fe85a3     ; r14==Py_None    → 进入 off-path 检查
0x180fe8592  mov  rbx, [0x18143db10]   ; True
0x180fe8599  call 0x180009b90
0x180fe859e  jmp  0x180fe87df     ; r14!=Py_None    → 返回 True（=拒绝）
0x180fe85a3  call 0x180fe0120     ; ★ off-path 附加检查（r14==Py_None 的独占落点）
0x180fe85a8  mov  rcx, rdi
0x180fe85ab  test rax, rax
0x180fe85ae  jne  0x180fe85d0     ; 非空 → 异常块
0x180fe85b0  …                    ; 空   → 也是构造异常
0x180fe85db  mov  r8, [0x181dcb7e8]  ; ★★ 池槽[71] = 异常原因串（行号 0x104 = 260）
0x180fe85e2  call 0x1814164f0        ; 异常抛掷助手
```

**返回值契约（与 `_guard_sensitive_action` 的用法双向自洽）**：
- `rax == NULL` ⇒ 放行（调用方 `je 0x180fe80a2`）
- `rax == True` ⇒ 拒绝（调用方取 `dword[rax]` 为真）
- `rax == Py_None` ⇒ 走到槽[71] 的异常抛出（「验证已过期，请重启 KeySteam 重新验证后再试。」）

### 1.2 P2 为什么拦不住

`0x180fe85a3` 是 `r14 == Py_None` 的**独占落点**（全 `.text` 无任何 jmp/call 进入，只有 `0x180fe8590` 的 `je` 能到）。

r40 的 `0xFE7990: 74 → EB` 把 `je 0x180fe85a3` 改成 `jmp 0x180fe85a3`：

- 改前：`Py_None` 才进入该支路；
- 改后：**无论 `r14` 是什么都强制进入该支路**。

而该支路两个后继（`jne` 两向）**最终都生成异常并写入槽[71]**。

⇒ **P2 不是"没拦住"，而是主动制造了用户看到的那条提示。P2 越"生效"越坏。** 这也解释了为何 r40 的窗口普查报"全通过"、用户却稳定看到它。

### 1.3 池#71 的真正归属（纠正交接材料）

`main_window_controller` 池基址**不是** `0x181dc7420`。枚举全部 **337 个** mod_consts Builder（`call 0x181433f90` 前的 `lea r8`(模块名串) + `lea rdx`(池基址) 对）得到逐模块独立基址：

| 模块 | 池基址 |
|---|---|
| `src.gui.main_window` | `0x181dc7420` |
| **`src.gui.main_window_controller`** | **`0x181dcb5b0`** |

据此 `槽[n] = 0x181dcb5b0 + 8n`：

| 槽 | 名字 | 槽地址 | 引用数 |
|---|---|---|---|
| 64 | `_emit_integrity_lock` | `0x181dcb7b0` | 6 |
| 65 | `is_resource_initializing` | `0x181dcb7b8` | 3 |
| 66 | `show_resource_initializing_message` | `0x181dcb7c0` | 1 |
| 67 | `_verification_gate_allows` | `0x181dcb7c8` | 4 |
| 68 | `show_tamper_warning` | `0x181dcb7d0` | 1 |
| 69 | `verify_ticket` | `0x181dcb7d8` | 8 |
| 70 | `load_verification_ticket` | `0x181dcb7e0` | 8 |
| **71** | **过期文案** | **`0x181dcb7e8`** | **1** |
| 72 | `log_divider` | `0x181dcb7f0` | 47 |

**槽[71] 全 `.text` 唯一引用 = `0x180fe85db`**，正在 `_verification_gate_allows` 体内。

槽 64–71 的引用点全部落在 `_verification_gate_allows` 与 `_guard_sensitive_action` 内，与《弹窗完整行为规格》§4 记录的执行序**完全吻合**。

⇒ 交接里"槽号 × 8 直接寻址"的**寻址方式不成立**：Nuitka 点名用的是**指名字符串的 mod_consts 元素**，不是 8 字节槽。两个编号空间不能相加。

### 1.4 关于 `0x181055af0`（澄清，避免继续追错方向）

它是**另一个索引空间**：Nuitka 代码对象表（条目 k 位于 FO `0x1d81314 + 12k`）的 **k = 5**，不是池#71。

它的 `lea rcx, [rip+0x65d]` 引用点 `0x18105548d` 被 `call 0x181404750` 当**描述符/函数对象**使用（`0x181404750` 内含 `mov rdx,[rax+0xd8]` + `call rdx`，即对象 `tp_call` 槽），**不是异常抛掷**。池#71 的 `[('u', 过期文案)]` 与它无任何字节级关联。

⇒ 「池编号 = k+66 / k+67」两个候选**都不成立**。编排 `0x181055af0` 不改变用户症状。

### 1.5 附带纠正

- **`mod_consts` 窗口 RIP 引用 = 0（交接 §6）不成立**。用与指令长度无关的精确判据（`目标VA = VA(disp字段末+4) + disp`）扫描，窗口内有 **19,681 处**有效引用，覆盖 **6,165 个唯一条目**（最多者 193 次）。因此「静态搜地址必然无效」这一结论只在"搜 `.data` 里的 u64 槽值"这一种形式下成立，RIP 相对引用是大量存在的。
- **G1 的 4 字节补丁配对不完整**：基线 `0F 84 F6 0A 00 00` → 成品 `E9 F7 0A 00 | 0A 00`。相对位移由 `0xAF6` 变 `0xAF7` 而**恰相抵**，目标仍是 `0x180f77c9b`（方向对、配对错）。本轮改为 6 字节完整改写 `E9 F7 0A 00 00 00`。

---

## 2. 验收口径：r40 盲区的真正根因

### 2.1 三类判据的实测判别力（这是本轮最重要的方法学结论）

| 判据 | 原版（正） | r40 成品（负） | 有效？ |
|---|---|---|---|
| **窗口文本**（`EnumWindows` + `WM_GETTEXT`，r40 用的） | 命中 `KeySteam 验证` | **0 命中** | ✗ **结构性失效** |
| **私有内存 UTF-16** | 7 条命中 | 7 条命中 | ✗ **恒真，无判别力** |
| **可见顶层窗口集合 + 主窗口 `en`/`blocked`** | 主窗口 `en=False,blocked=True` **93/93 帧** + 独立模态框 | 主窗口 `en=False,blocked=True` **73/74 帧** + 独立模态框 | ✓ **有效** |

**内存判据为何恒真**：CPython 里 CJK 常量在 strings 池中就是 **UCS-2（UTF-16LE）紧凑对象**，池常量进入堆是语言运行时行为，与是否弹窗无关。所以"低 2 字节全 0 且偶地址对齐"之类收窄也救不了它 —— 我从头收集的 `heap` / `image` 两集对照解决不了恒真（r40 正对照 `image=0`、`heap=7`，原版同样 `heap=7`）。**这个判据必须废弃。**

**窗口文本判据为何失效**：那条告警是 Qt 的 `QLabel`/`QMessageBox` 里的 `QString`，**不进任何 HWND 文本**。r40 用 `EnumWindows` 永远验不到，这是"报全通过却被打脸"的根本原因。

**有效判据**：主窗口是否**独立可见**（可见顶层窗口集合里除主窗口外还有没有别的），以及主窗口是否被模态阻塞（`GetWindow(hwnd, GW_ENABLEDPOPUP)` 返回值 ≠ 自身 ⇒ `blocked`；`IsWindowEnabled` ⇒ `en`）。这套判据在原版与 r40 上**都稳定报"阻塞"**，在成品上**稳定报"自由"**，判别力经过双向验证。

### 2.2 事故复现与规避

- **向主窗口发 ESC 会杀死程序**：验证弹窗的 ESC 被 `reject` 接管，`FirstRunDialog` 的 close 走 `QCoreApplication.quit()`（规格 §2）。第一次原版对照 33 秒被自己杀掉。**修正：普查器完全禁止向主窗口发 ESC**，改为在其他区域点空白处收菜单。
- **用户路径只在主窗口自由时执行**：原版主窗口全程模态阻塞，8 次尝试全部记为 `main_blocked`，**自动跳过**而不是往死窗口发消息。成品则第 0 次尝试即 `main_ready` 并完整执行 20 次点击。

---

## 3. 成品：3 处补丁 / 14 字节

| # | 文件偏移 | 长度 | 原字节 | 新字节 | 语义 |
|---|---|---|---|---|---|
| **F-A** | `0xFE7967` | 6 | `0F 84 DD 00 00 00` | `E9 4E 02 00 00 90` | RVA `0x180fe8567`：`je 0x180fe864a` → `jmp 0x180fe87ba`。**闸门恒走 `xor eax,eax` 尾声 ⇒ 恒返回 `None` ⇒ 放行**。末位 `90` 落在不可达字节 |
| **F-B** | `0xF93770` | 6 | `0F 84 DF 07 00 00` | `90 90 90 90 90 90` | RVA `0x180f94370`（`_check_cached_verification` 内 `+0x270`）：消启动期验证弹窗（r40 的 P1） |
| **F-C** | `0xF7659F` | 6 | `0F 84 F6 0A 00 00` | `E9 F7 0A 00 00 00` | RVA `0x180f7719f`（`MainWindow.show_tamper_warning` 内）：`je → jmp`，外部验签收口（r40 的 G1，本处改为 6 字节完整配对）。**重打包必触发 TAMPERED，此项必需** |

**为何这三处足够**：
- 闸门恒 `None` ⇒ 所有 17 个 tamper 调用点的**共同上游**被切断，运行期不再产生任何门禁分流；F-C 是对**重打包导致的外部验签失败**这条独立路径的兜底（它在闸门之前就触发）。
- F-B 覆盖启动期 `_check_cached_verification` 的验证弹窗路径。
- 三处互不重叠、互不依赖，全部是函数内分支改写，**不碰 `RuntimeGuard` 心跳、不碰任何入口**（避免 watchdog 误判与副作用丢失）。

---

## 4. 最终验收证据

### 4.1 310 秒严格实测（增强用户路径）

```
secs=310  frames=112  alive=112/112
可见顶层窗口（全 310 秒）:
   111  ('Qt6111QWindowIcon', 'KeySteam v2.99', 974, 667)
主窗口 en/blocked: {(True, False): 111}
门禁类可见窗口: NONE
窗口关键词命中帧: 0 / 112
用户路径: 7 菜单 + 5 工具 + 搜索输入 + 3 列表 → 20 次点击全部 sent，零 hwnd_gone，零新窗口
CPU: min 0.000 / max 0.227 / 均值 0.003 核/秒（无自旋、无异常）
```

每次点击后都执行 `sweep_modals()` 枚举全部本进程顶层窗口：**全程没有任何新窗口被记录**，即 20 次点击均未触发任何弹窗。

### 4.2 同条件原版对照（证明判据有判别力）

```
secs=300  frames=93  alive=93/93
可见顶层窗口:
    92  ('Qt6111QWindowIcon', 'KeySteam 验证', 533, 742)   ← 门禁模态框
    92  ('Qt6111QWindowIcon', 'KeySteam v2.99', 974, 667)
主窗口: en=False, blocked=True（92/93 帧）
用户路径: main_blocked × 8 → USER_PATH_SKIPPED（自动跳过，未执行）
```

### 4.3 成品反向验证

```
内嵌 main.dll md5 = 17f981137d2549bb576eaf87a7f469b7
差异字节总数 = 14，差异区间 = 4
diff_outside_patches = 0
footer body_sha256 重算一致 = c0c968ed34a04695fb2acbbb6afee9c4e489eb6cf8edd528205d24d9c1b2a4a3
exe 长度 = 30,885,138 == 原始长度
```

逐区间反汇编确认语义（示例，F-A 与 F-C）：

```
FO 0xfe7967  VA 0x180fe8567
  基线: 0f 84 dd 00 00 00    je  0x180fe864a
  成品: e9 4e 02 00 00 90    jmp 0x180fe87ba ; nop

FO 0xf7659f  VA 0x180f7719f
  基线: 0f 84 f6 0a 00 00    je  0x180f77c9b
  成品: e9 f7 0a 00 00 00    jmp 0x180f77c9b
```

---

## 5. 遗留项（诚实标注）

1. **「窗口异常大」未复现**。本轮在当前环境实测：**原版 = 974×667，补丁版 = 974×667**（同一数值），与 `%APPDATA%\Shikieiki\shiki.json` 的 `961×631` 仅差 13×36 像素（正常窗口边框）。⇒ 与补丁无关（交接 §2 已排除），且我**未能复现**交接记录的 `3540×2580`。怀疑先前测量落在不同 DPI 感知会话，或量到的是物理像素而非当前会话的逻辑像素。**此项不影响验证绕过，建议单独立项。**
2. **`F_m1`（不带 F-B）为何也通过**：`F_m1` = F-A + F-C，260 秒同样零门禁。原因：`F-A` 使闸门恒放行后，`_check_cached_verification` 的验证弹窗分支未在本机的 `verification.cache` 状态下触发。但**保留 F-B 更稳**（缓存轮换/服务端状态变化时它会起作用），且成本为零。
3. **`0x180fe0120`（off-path 附加检查）的语义未查明**：`F-A` 把它整条支路变成不可达，故不影响成品，但未做语义复原。
4. **未做多轮重复验收**：本轮为单次 310 秒。建议 Lead 侧至少再跑 2 次同条件以排除单次偶发。

---

## 6. 复现命令

```bash
cd "/mnt/d/03_Work/03_Develop/KeySteam v2.99/_re/ghidra"
python3 tools/rebuild_exe.py --src /mnt/d/ks_debug/KeySteam.exe \
  --out /mnt/d/r41_iso/F/KeySteam_r41_final.exe \
  --patch 0xFE7967:0F84DD000000:E94E02000090 \
  --patch 0xF93770:0F84DF070000:909090909090 \
  --patch 0xF7659F:0F84F60A0000:E9F70A000000 \
  --report-json /mnt/d/ks_debug/r41/F/logs/final.report.json
```

验收（Windows Python，严格归属 + 用户路径矩阵）：
```bash
cd /mnt/d/ks_debug/r41/F
"/mnt/c/Program Files/Python312/python.exe" f_census.py \
  --exe 'D:\r41_iso\F\KeySteam_r41_final.exe' --secs 310 \
  --out 'D:\ks_debug\r41\F\out\final_310.json' --act
```

---

## 7. 本轮工具（F 线自建，全部零依赖外部反汇编器）

| 工具 | 用途 | 关键点 |
|---|---|---|
| `f_pe.py` | PE 解析 + 映射换算 | 从节表推导，不引用硬编码 SEGS；与交接的 `FO = RVA - 0x1000 + 0x400` 抽样一致 |
| `f_xref.py` | **精确 RIP 相对引用扫描** | 判据 `目标VA = VA(disp字段末+4) + disp`，**与指令长度无关**；再要求"disp 是最后 4 字节"做自洽校验。解决了线性反汇编在 21MB `.text` 上失步的问题 |
| `f_direct.py` | `E8`/`E9` 直接调用/跳转扫描 | 对每个 opcode 字节位置求目标，无失步；capstone 单条自洽校验 |
| `f_pools.py` | **mod_consts 池 Builder 枚举** | 337 个池的 `名字 → 基址` 全表，是本轮纠正池归属的关键 |
| `f_census.py` | 严格归属普查 + 用户路径矩阵 | 窗口级判据；**禁用 ESC**；`sweep_modals()` 每步清扫；内存扫描仅供诊断 |
| `f_verify_final.py` | 成品反向验证 | 抽取内嵌 `main.dll` → 逐字节 diff → 反汇编双栏对照 → `diff_outside_patches` 自证 |

**踩过的坑（给后续轮次）**：
- numpy 滑窗 `.view(uint32)` 在非 4 对齐偏移上会抛出；必须用位移或 `np.lib.stride_tricks`。
- `call E8` 扫描器里 `self.pos` 已是节内偏移，**不要再减 `raw`**。
- 线性 `md.disasm` 在 21MB `.text` 上会因数据/填充失步，**任何依赖它的结论都要用精确判据复核**。
