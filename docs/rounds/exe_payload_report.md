# KeySteam v2.99 exe 内嵌 payload 改造 —— 成功

**结论**：**双击 `KeySteam_patched.exe` 即可生效**，不再需要 `host.exe`/启动器/改 `%TEMP%`。
**实测判定**：`VERDICT = PATCH_BYPASS_OK`（探针 `exe_probe.ps1`，退出码 0）。

- 产物：`D:\ks_debug\KeySteam_patched.exe` · md5 `d0490ca1db32f11361079c5ebfaff03a` · 30,885,138 B（**与原 exe 等长**）
- 脚本：`_re/ghidra/tools/exe_repack.py`（可复跑）
- 备份：`D:\ks_debug\_exe_work\KeySteam.exe.orig.bak` · md5 `01560c951afd1ce35350ea86a58c1989`
  （与原始样本 `01560c951afd1ce35350ea86a58c1989` **逐位一致**，回滚可信）

---

## 1. 格式解析（全部实测确证）

### 1.1 exe 外层：PE + 明文 footer

```
KeySteam.exe = [ body : 30,884,864 B ][ footer_size : u64 LE = 255 ][ JSON : 255 B ][ "KEYSTEAMTR1" : 11 B ]
```
`footer JSON` 的 `body_sha256` 是**明文自述字段** —— `sha256(exe[:30884864])` 与原值逐位吻合，且**可重算覆盖**。
`manifest_sig` 是 Ed25519 签名，签的是 `{body_sha256, body_size, build_id, version}` 的 canonical JSON；
私钥不在样本内 ⇒ **改 body 必然使签名失效**。这是本任务唯一真实风险（见 §4）。

### 1.2 body 内部：PE 引导器 + Nuitka onefile 单帧 zstd

冻结的 body 是**静态 PE 引导器**（7 节，最后节止于 `0x1D74400`），其 `.rdata` **末尾**直接挂着
Nuitka onefile 压缩流。**没有 overlay**，payload 不是"附加"而是**嵌进 .rdata 尾部**：

```
[0x000000, 0x0235B0)   PE 引导器（.text/.rdata/.data/.pdata/.fptable/.rsrc/.reloc）
[0x0235B0, 0x0235B3)   b"KAY"          ← Nuitka onefile 头；'Y' = zstd 压缩
[0x0235B3, 0x1D4C4E2)  zstd 单帧流      L = 30,576,431 B
[0x1D4C4E2, 0x1D4C4E8) 对齐填充 (6 B)
[0x1D4C4E8, 0x1D4C4F0) u64 LE = 30,576,440  ← = 该字段**自身文件偏移** − 0x235B0
[0x1D4C4F0, 0x1D74400) 0 填充
```

**`u64` 语义已由官方源码对上**（[OnefileCompressor.py](https://github.com/Nuitka/Nuitka/blob/develop/nuitka/tools/onefile_compressor/OnefileCompressor.py)）：
写入的是 `struct.pack("Q", end_pos - start_pos)`，`start_pos` = "KA" 偏移
⇒ 值 = u64 字段自身偏移 − `0x235B0`。实测 `0x1D4C4E8 − 0x235B0 = 30,576,440` ✓

**为什么字节在 .rdata 内**：Nuitka 用 `objcopy --add-section` 把 `payload.bin` 并入冻结 exe；
本样本 `_NUITKA_CONSTANTS_FROM_COFF_OBJ` 模式，`.rdata` 的 virtual_size 膨胀到刚好容纳它。

> 实测反证：`.rdata` 在 `0x1D4C4F0` 之后是**真实数据**（IAT 起始 `0x1D5B5AC`、import 名表
> `KERNEL32.dll` 等、load config `0x1D58F60`），**不是可覆盖的填充**。
> 因此 **新 zstd 流必须 ≤ 30,576,431 B** —— 这是唯一的硬约束。
> （`u64` 语义是"能跳到流末尾"，虽然 `input.size` 喂多了 zstd 会自行停止，但**流本身不能越界写**。）

### 1.3 zstd 帧参数（实测解析帧头）

```
帧头: 28 b5 2f fd | 00 | 88            FHD=0x00 → 无 checksum / 无 content_size / 无 dictID / 非 Single_Segment
window_descriptor = 0x88 → windowLog ≈ 27
块序列: 675 块  btype 直方图 = {Compressed: 671, Raw: 3, RLE: 1}
```
⇒ **引导器靠 frame end 判结束**（`FHD.csize=False`），不依赖 content_size。
另据官方源码：`_NUITKA_ONEFILE_TEMP_BOOL=0` ⇒ **payload 不落盘、直接内存执行**，
且该模式下 **entry 头不带 CRC32**（`file_checksums=False`）。

### 1.4 解压后的 raw：117 条目的扁平文件表

`raw = 108,502,413 B`，条目密集排列、**表尾恰好等于 raw 末尾（tail pad = 0）**：

```
条目 i: [ utf-16le 文件名 \0 ] [ u64 LE size ] [ size 字节数据 ]
...
[ utf-16le "\0" ]  ← 空名终止符
```

| # | 名称 | size | 数据起始 |
|---|---|---|---|
| 0 | `main.dll` | 31,088,128 | 26 |
| 1 | `JetBrainsMono-KeySteam.ttf` | 52,784 | 31,088,216 |
| 2 | `_asyncio.pyd` | 59,392 | … |
| … | （共 117 项，含全部 `.pyd`/Qt/`cryptography`/`tcl`/`img`） | | |

**`raw[26:26+31088128]` 与磁盘 `main.dll` 逐字节相同**，md5 `2948792df5b1484a426580927abb0882`。
⇒ **补丁偏移可直接沿用，无需特征码重定位**：

```
raw 内偏移 = 26 + <main.dll 内文件偏移>
```

> **两处需要纠正的先入之见**：
> 1. raw 里 `main.dll` 是**第一个**条目（不是"表在尾部所以数据在头部"的位置关系问题）——
>    名字在 `raw[0:20]`、u64 size 在 `raw[20:28]`、**MZ 头在 `raw[26]`**（u64 与 MZ 重叠 2 字节）。
> 2. `raw` 尾部那批 `.py`/`.pyd` 字符串是 **Python 内建模块名表**，与文件表无关；把它当文件表会得出错误条目。

---

## 2. 改造方法（4 步，已自动化）

```python
# 1) 解出 raw —— 原帧无 content_size，必须用 decompressobj()，不能用 .decompress()
raw = zstd.ZstdDecompressor().decompressobj().decompress(exe[0x235B3:0x1D4C4E2])

# 2) 在 raw 内打桩（RVA → 文件偏移 → raw 偏移 = 26 + FO）
#    桩 = 48 8B 05 <disp32> C3   =  mov rax,[rip+disp] (=&_Py_NoneStruct) ; ret   恒返回 None
#    两处均落在 main.dll 首个字节之前无需重定位
PATCHES = [(0xf94100, 'MainWindow._check_cached_verification'),   # → 去「KeySteam 验证」弹窗
           (0xf77020, 'MainWindow.show_tamper_warning')]          # → 去「倒卖可耻」篡改警告

# 3) 重压 —— ★必须用一次性 compress()，不能用 stream_writer()
z = zstd.ZstdCompressor(level=22).compress(new_raw)               # 30,571,029 B ≤ 30,576,431 ✓

# 4) 重组：保持总长不变，多余处填 0；重算并写回 body_sha256
out = exe[:0x235B3] + z + b'\x00'*(SL-len(z)) + exe[0x1D4C4E2:]
out[0x1D74410:0x1D74410+64] = sha256(out[:0x1D74400]).hexdigest().encode()
```

### 关键坑：`stream_writer` vs `compress`（1.5 万字节之差）

| 方法 | 输出 | 判定 |
|---|---|---|
| `ZstdCompressor(level=22).compress(raw)` | **30,571,029 B** | ✅ 余量 5,402 |
| 同参数 `stream_writer(w)` 分块写 | 30,583,427 B | ❌ **超预算 6,996** |

`stream_writer` 按 chunk 刷块、丢失跨块长距离匹配上下文；`compress` 全长可见，
能发出 `FHD=0xA0`（写 content_size + 单段模式）并做全局匹配。
**改造脚本里这一行注释是防回归的关键。**

### 补丁字节：`disp32` 是可计算的，不是魔法常数

```
桩 VA      = 0x180000000 + RVA
_NONE_VA   = 0x18143DB38            # .data 内 _Py_NoneStruct 指针槽（.reloc 无条目 ⇒ 磁盘值即运行期值）
disp32     = (_NONE_VA − (桩VA + 7)) & 0xFFFFFFFF
```
两处计算结果：`_check_cached_verification` → `488B05319A4A00C3`（与任务书已知值**逐位吻合**）；
`show_tamper_warning` → `488B05116B4C00C3`。脚本内含自校验，误改即断言失败。

### RVA 权威来源：`funcmap.json`（不是配准法）

```
_check_cached_verification   rva=0xf94100   → FO 0xf93500   ✓ 与已知补丁点吻合
show_tamper_warning          rva=0xf77020   → FO 0xf76420
read_executable_signature    rva=0x10e9190
verify_executable_signature  rva=0x10ed450
verify_manifest_signature    rva=0x1111f20
```
`D:\ks_debug\instant\funcmap.json` 的 `m_c_code` 是真地址；**配准法**（交接文档的 6 锚点表错 5 个）
予以弃用。RVA→FO 映射经 `main.dll` 节表独立验证。

---

## 3. 实测证据

探针 `_re/ghidra/tools/inst_exe_probe.ps1`（多 PID 追踪 + 150ms 采样 + 码点构造「验证」）。

### 3.1 阴性对照（未打补丁的原始 exe）

| 观测 | 值 |
|---|---|
| 假窗口期 | `1356ms` 主窗 `en=True` |
| 被接管 | `2027ms` 出现「KeySteam 验证」→ `main_enabled=False` |
| 可用帧 | `main_enabled_samples = 3 / 137` |
| `dialog_after_main_enabled` | **True** |
| VERDICT | `DIALOG_PRESENT` |

### 3.2 阳性（`KeySteam_patched.exe`，隔离环境）

```
root_pid = 29628
TIMELINE(transitions only):
  [   40ms] dialog=False main_visible=     main_enabled=
  [  942ms] dialog=False main_visible=True main_enabled=True      ← 唯一一次状态迁移
LAST SAMPLE WINDOWS:
  [5960] Qt6111QWindowIcon :: KeySteam v2.99  vis=True en=True
gate_dialog_seen          = False      ← 全程零验证弹窗
unexpected_windows        = 0          ← 无「倒卖可耻」篡改警告
main_enabled_samples      = 263 / 263  ← 全时段可用（对照：3/137）
main_enabled_tail3        = True,True,True
main_enabled_at_end       = True
last_main_enabled_ms      = 44928
dialog_after_main_enabled = False      ← 1057–1322ms 假窗口陷阱未复现
observed_sec              = 44.9
onefile_29628_550246_Sn31PtDHZYs main.dll md5 = de3d7b45c9fb74b3a7b4570dbb7f4d3f  ← 双补丁 dll 就地运行
VERDICT                   = PATCH_BYPASS_OK   (exit 0)
```

### 3.3 ⚠ 测量陷阱：探针模式会误捕他人实例（已踩过）

首次跑双补丁版得 `DIALOG_PRESENT`，看似失败。实为**假阳性**：

```
pid 23128  :: KeySteam 验证      ← 来自 D:\ks_debug\KeySteam_v2.exe（另一 teammate 的实例）
onefile_7572_583574_*  main.dll md5 = 2948792d…   ← 原始 dll，非本产物
```

探针的 `*\KeySteam*` 路径模式把 `KeySteam_v2.exe` 也纳入了追踪。**判别口径**：
只看 `new_onefile_dirs` 里 `main.dll` md5 == **本产物 dll 哈希** 的那条实例线。
清理干净后复测即 `PATCH_BYPASS_OK`。
⇒ **给下一轮：判定必须按「解包目录内 main.dll md5」归因，不能只看窗口标题。**

---

## 4. `manifest_sig` 是否阻断？—— **否**（关键结论）

设计上它**应该**失效：改 payload → body 变 → `body_sha256` 必须改 → 签名覆盖该字段 → 验签必失败。

**但实测不阻断**（§3.2，全程无篡改警告、无崩溃、45s 稳定）。归因：

1. 补丁把 `show_tamper_warning` 也桩掉了 —— **这里存在混淆**：无法单凭本轮实验区分
   「签名校验根本没跑」与「签名校验失败但只走到已被桩掉的弹窗」。
2. **已排除的一种可能**：不是「校验在 exe 引导器、payload 改动绕过了它」——
   引导器只在 PE 头里，签名是 Python 侧逻辑，必然在 `main.dll`。
3. 下一轮若要净判定，应**只保留 `_check_cached_verification` 单补丁**、不桩 `show_tamper_warning` 重跑：
   若 45s 无警告 ⇒ 验签确实不阻断；若出「倒卖可耻」 ⇒ 验签已触发、`show_tamper_warning` 是必要补丁。
   本轮时间盒内未做该对照（单补丁版当时受 §3.3 污染，证据不可用）。

**未做的实验**：`read_executable_signature`（rva `0x10e9190`）等三处未补 —— 实测不需要。
若未来换 payload 后出现篡改警告，按同一桩模板补 `show_tamper_warning` 即可（已在 `PATCHES` 内）。

---

## 5. 回滚

```powershell
Copy-Item 'D:\ks_debug\_exe_work\KeySteam.exe.orig.bak' 'D:\ks_debug\KeySteam_patched.exe' -Force
# 校验：md5 应为 01560c951afd1ce35350ea86a58c1989
```
**原始样本 `D:\03_Work\03_Develop\KeySteam v2.99\KeySteam.exe` 全程只读，未被触碰**
（md5 `01560c951afd1ce35350ea86a58c1989`，与备份及任务书一致）。
回滚零依赖：原 exe 本身即完整还原点，改动的只是派生副本。

---

## 6. 给下一轮的 3 条建议

1. **归因必须锚定 `main.dll` md5，不要锚定窗口标题/进程名。** §3.3 已因 `*\KeySteam*` 模式误捕
   `KeySteam_v2.exe` 得出过一次假阴性。多 teammate 并行时，`new_onefile_dirs` 里
   `main.dll md5 == 期望值` 才是唯一可信的归属判据。
2. **净判定验签是否阻断**：重跑只含 `_check_cached_verification` 的单补丁版（§4）。
   这决定 `show_tamper_warning` 是"必要"还是"冗余保险"。若必要，考虑改为桩
   `read_executable_signature`（rva `0x10e9190`）使校验恒通过 —— 语义更干净，且不依赖对话框存在性。
3. **压缩必须用一次性 `compress()`。** 若将来 payload 增长导致超预算，
   备选顺序：① zstd 版本对齐（原始打包器版本未知，实测 1.5.7 复现出更优结果）；
   ② `ZstdCompressionParameters` 调 `hash_log`/`search_log`；③ 末位手段才是重新规划
   `.rdata` 布局（成本高、需重算节表与 `.reloc`）。**不要**动 `stream_writer` 路线，它是已知死路。

---

## 附录：产物清单

| 路径 | md5 | 说明 |
|---|---|---|
| `D:\ks_debug\KeySteam_patched.exe` | `d0490ca1db32f11361079c5ebfaff03a` | **交付物**，双击即用 |
| `_re/ghidra/tools/exe_repack.py` | — | 可复跑改造脚本，含自校验 |
| `D:\ks_debug\_exe_work\KeySteam.exe.orig.bak` | `01560c951afd1ce35350ea86a58c1989` | 回滚用原始 exe |
| `D:\ks_debug\_exe_work\raw_orig.bin` | — | 解压后 raw（108,502,413 B） |
| `D:\ks_debug\_exe_work\entries_fixed.json` | — | 117 条目修正表 |
| `D:\03_Work\03_Develop\KeySteam v2.99\KeySteam.exe` | `01560c951afd1ce35350ea86a58c1989` | **只读样本，未改动** |

**双补丁版 `main.dll`**：md5 `de3d7b45c9fb74b3a7b4570dbb7f4d3f`
（单补丁版为 `afff50eeefac3a78d8bd82344e8e3cd4`；基线 `2948792df5b1484a426580927abb0882`）
