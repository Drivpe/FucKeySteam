# Nuitka 商业样本（加密 + 完整性保护）高效逆向方法论

**一句话摘要**：Nuitka 的常量池**不是运行期才形成的黑盒**——它是磁盘上一个**带完整 tag 表的结构化 blob**（Windows 下为 COFF 对象里的静态字节数组，由 `loadConstantsBlob` 解码），因此「静态字符串搜索必然失败」**只对 `.text` 指令操作数成立，对 blob 本体不成立**。本轮已在真实样本上**纯静态解出 `src.utils.machine_id` 全部 43 条常量**，并据此**推翻了三处既有假设**、**确证了一条致命的切分错误**。同时，Nuitka 官方源码证明**编译函数的机器码是编译期固化的静态 C 函数**（`m_c_code`），这**推翻了本项目「闸门机器码不在静态文件里」的定位方案**。

**分析对象**：`D:\ks_debug\main.dll`（`/mnt/d/ks_debug/main.dll`），sha256 前缀 `cc869941…`，31,088,128 字节，Nuitka onefile 内层 payload，Python 3.12。
**日期**：本轮研究于 `keysteam-no-verification` 上下文内执行。
**方法声明**：所有「本项目实测」结论均在上述样本字节上直接执行得出；所有「官方源码」结论取自 Nuitka `develop` 分支、CPython `v3.12.10`/`v3.13.5` 标签的原始头文件、Intel SDM 正文、Microsoft Learn。**未确证项集中于文末列表。**

---

## 摘要：本轮改变了什么

| 项目原有认知 | 本轮结论 | 影响 |
| --- | --- | --- |
| 「静态字符串搜索对池常量必然失败，必须走运行期」 | **需限定范围**：失败的是 `.text` 指令操作数搜索；**blob 本体可纯静态解析**，本轮已完成 | 打开「不做运行期 dump 也能拿常量」的通路 |
| 闸门机器码「不在静态文件里」，需在 MAKE_FUNCTION 处解析 `PyCodeObject` 读 `m_code` | **此方案不成立**。Nuitka 函数对象**没有 `m_code` 字段**；机器码入口是 `m_c_code`，且是**编译期固化的静态 C 函数指针**。Nuitka 的 code object 内字节码是「执行即抛 RuntimeError」的哨兵 | **放弃「读 m_code」路线**，改为直接静态定位 `impl_` 函数 |
| 票据格式 = `KSTK`(4) + nonce(12) + 密文(589) | **纠错：magic 是 5 字节 `KSTK\x01`**，正确切分为 magic(5) + nonce(12) + ct+tag(588) | 此前 >18000 组爆破**nonce 整体错位 1 字节**，否定结果**全部不成立** |
| `_cache_key` = `sha256((PREF + "\|" + machine_id))` | 常量表显示**两个前缀并存**，且 `_machine_bound_key` 用 **`.digest()`** 而非 `hexdigest` | 新增未覆盖维度 |
| `_hash_machine_parts` 拼接格式未知 | **静态确证**：`sha256("\|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:32]` | 消除一个阻塞项 |
| 「Nuitka 的 tuple items 指针在 `[obj+0x18]`，与 CPython 不同」 | **误读**。Nuitka 全程使用标准 `PyTupleObject`；`0x18` 就是 CPython 官方布局本身 | 修正一处方法学错误 |

---

## 方向 A：Nuitka 编译产物的逆向方法论

### A.1 `createModuleConstants` 的官方定义

官方模板（`nuitka/code_generation/templates/CodeTemplatesModules.py:72-85`）：

```c
static void createModuleConstants(PyThreadState *tstate) {
    if (constants_created == false) {
        LOAD_DIRECT_CONSTANTS_BLOB(tstate, (PyObject **)&mod_consts, <module_const_blob_symbol_name>);
        constants_created = true;
    }
}
```

来源：[Nuitka `nuitka/code_generation/templates/CodeTemplatesModules.py`](https://github.com/Nuitka/Nuitka/blob/develop/nuitka/code_generation/templates/CodeTemplatesModules.py)。

`LOAD_DIRECT_CONSTANTS_BLOB` 展开（`nuitka/build/include/nuitka/constants_blob.h`）：

```c
#define LOAD_DIRECT_CONSTANTS_BLOB(tstate, output, blob_symbol_name) \
    loadConstantsBlobData(tstate, output, get##blob_symbol_name##Data())
```

来源：[Nuitka `nuitka/build/include/nuitka/constants_blob.h`](https://github.com/Nuitka/Nuitka/blob/develop/nuitka/build/include/nuitka/constants_blob.h)。

### A.2 blob 的物理形态 —— 静态可解析的根本原因

`HelpersConstantsBlob.c` 文件头明确 **Windows 默认走 `_NUITKA_CONSTANTS_FROM_COFF_OBJ`**：

```c
#if defined(_WIN32)
#define _NUITKA_CONSTANTS_FROM_COFF_OBJ 1
#elif defined(__APPLE__)
#define _NUITKA_CONSTANTS_FROM_MACOS_SECTION 1
#else
#define _NUITKA_CONSTANTS_FROM_CODE 1
#endif
```

而 COFF 模式下 blob 就是**普通 C 数组符号**（`nuitka/build/include/nuitka/blobs.h` 的 `#else` 分支）：

```c
extern modifier unsigned char blob_name##_data[];
...
return (unsigned modifier char *)(blob_name##_data);
```

来源：[Nuitka `nuitka/build/static_src/HelpersConstantsBlob.c`](https://github.com/Nuitka/Nuitka/blob/develop/nuitka/build/static_src/HelpersConstantsBlob.c)、[`nuitka/build/include/nuitka/blobs.h`](https://github.com/Nuitka/Nuitka/blob/develop/nuitka/build/include/nuitka/blobs.h)。

**⇒ 结论：Windows 下 blob 是名为 `constant_bin_data[]` 的字节数组，链接进 PE 的某个节。它天然就是「磁盘上的数据」。** 本轮在样本上搜索该符号名返回 0 命中（符号表已 strip），但**数据本体在场且可解析**——见 A.4。

### A.3 blob 的目录结构与 tag 表（官方原文）

目录遍历逻辑（`HelpersConstantsBlob.c:1523-1545`）：

```c
unsigned char const *w = constant_bin;
for (;;) {
    int match = strcmp(name, (char const *)w);
    w += strlen((char const *)w) + 1;
    uint32_t size = unpackValueUint32(&w);
    if (match == 0) break;
    w += size;              // Skip other module data.
}
unpackBlobConstants(tstate, output, w);
```

`unpackBlobConstants` 先读 `uint16` 作为常量个数：

```c
static void unpackBlobConstants(PyThreadState *tstate, void *output, unsigned char const *data) {
    int count = (int)unpackValueUint16(&data);
    _unpackBlobConstants(tstate, &output, data, count);
}
```

**⇒ 目录项格式（官方确证）**：`<模块名>\0` + `uint32 size`，重复；命中后接 `uint16 count` + `count` 个常量。

tag 表全量见 [`constants_blob_spec.h`](https://nuitka.net/apidoc/constants__blob__spec_8h_source.html)（官方 apidoc 原文），本轮关心的关键项：

```c
#define NUITKA_CONSTANT_BLOB_TAG_TUPLE                     0x54 /* 'T' */
#define NUITKA_CONSTANT_BLOB_TAG_ATTRIBUTE_NAME            0x61 /* 'a' */
#define NUITKA_CONSTANT_BLOB_TAG_TEXT_UTF8_ZERO_TERMINATED 0x75 /* 'u' */
#define NUITKA_CONSTANT_BLOB_TAG_TEXT_SINGLE               0x77 /* 'w' */
#define NUITKA_CONSTANT_BLOB_TAG_BYTES_ZERO_TERMINATED     0x63 /* 'c' */
#define NUITKA_CONSTANT_BLOB_TAG_LONG_POSITIVE_SMALL       0x6c /* 'l' */
#define NUITKA_CONSTANT_BLOB_TAG_CODE_OBJECT               0x43 /* 'C' */
#define NUITKA_CONSTANT_BLOB_TAG_SLICE                     0x3a /* ':' */
#define NUITKA_CONSTANT_BLOB_TAG_NONE                      0x6e /* 'n' */
#define NUITKA_CONSTANT_BLOB_TAG_END                       0x2e /* '.' */
```

**这解释了本项目此前的观测**：文档记载「槽 731 = `fetch_config`，从 Nuitka 常量池解出（tag=`0x61`）」——`0x61` 正是 `ATTRIBUTE_NAME`。

**⚠ 两个必踩的坑（本轮实际踩过）**：

1. `TEXT_SINGLE`（`0x77`）是**单字节字符串、无长度前缀**（`HelpersConstantsBlob.c:852-860` 原文 `FromStringAndSize(tstate, (const char *)data, 1, true)`）。误加长度读取会导致后续全部错位。
2. `BYTES_ZERO_TERMINATED`（`0x63`）是**零结尾字节串**——本项目三个 magic 常量都用它编码，这是 magic 为 5 字节的证据来源（A.6）。

### A.4 本项目实测：纯静态解出 `src.utils.machine_id` 全部 43 条常量

**定位方法**：扫描 `.rdata`/`.data` 内所有 `\0` 前导 + 合法模块名字符集的位置，用「后续 `uint32 size` 能连续跨越 ≥8 个模块」做校验。命中链起点 `0x1cecbe7`，其下 34 个模块含 22 个 `src.*`。

**实测结果**：

```
src.utils.machine_id    size=672    blob_body_off=0x1cf475e    chain=0x1cecbe7
```

按官方格式解码，**43/43 条常量全部命中**（`count=43`）：

| # | tag | 值 | 语义 |
| --- | --- | --- | --- |
| 0 | `ATTR` | `platform` | 模块引用 |
| 1 | `ATTR` | `system` | `platform.system()` |
| 2 | `ATTR` | `casefold` | `.casefold()` |
| 3 | `ATTR` | `windows` | 比较字面量（疑 `== 'windows'`） |
| 4–6 | `ATTR` | `winreg` / `OpenKey` / `HKEY_LOCAL_MACHINE` | 注册表访问 |
| 7 | `U` | `SOFTWARE\Microsoft\Cryptography` | 注册表路径 |
| 8–9 | `ATTR` | `QueryValueEx` / `MachineGuid` | 值读取 |
| 10 | `TUPLE` | `[None, None, None]` | 三元素元组常量 |
| 11–12 | `ATTR` | `value` / `strip` | `.strip()` |
| 13 | `ATTR` | `_hash_machine_parts` | **本模块函数** |
| 14 | `ATTR` | `_read_windows_machine_guid` | **本模块函数** |
| 15–19 | `ATTR` | `node` / `socket` / `gethostname` / `uuid` / `getnode` | 指纹采集 |
| 20 | `U` | `旧版机器标识（含 MAC），仅用于解密历史验证缓存。` | 文档串 |
| 21 | `W1` | `'\|'` | **分隔符（TEXT_SINGLE）** |
| 22 | `U` | `unknown-machine` | **空值回退字面量** |
| 23–27 | `ATTR` | `hashlib` / `sha256` / `encode` / `hexdigest` | 哈希链 |
| 26 | `TUPLE` | `['utf-8']` | encode 参数 |
| 28 | `SLICE` | `:` | **切片** |
| 29 | `NONE` | `None` | 下界 |
| 30 | `LONG_POSITIVE_SMALL` | `32` | **切片上界** |
| 31 | `NONE` | `None` | 步长 |
| 32–33 | `U` | `<genexpr>` / `_hash_machine_parts.<locals>.<genexpr>` | genexpr 标识 |
| 34–37 | `ATTR`/`DICT` | `origin` / `has_location` / `annotations` / `{return}` | 注解元数据 |
| 38 | `ATTR` | `str` | **genexpr 内的 `str(p)`** |
| 39–40 | `ATTR` | `get_machine_id` / `get_legacy_machine_id` | |
| 41 | `DICT` | `{parts, return}` | |
| 42 | `U` | `list[str]` | 注解 |

**原始字节佐证**（`0x1cf489c` 起，直接取自文件）：

```
77 7c | 75 "unknown-machine\0" | 61 "hashlib\0" 61 "sha256\0" 61 "encode\0"
54 01 | 75 "utf-8\0" | 61 "hexdigest\0" | 3a 6e 6c 20 6e | 75 "<genexpr>\0"
```

`3a`(SLICE) `6e`(NONE) `6c 20`(LONG_POSITIVE_SMALL 32) `6e`(NONE) —— **即 `[None:32:None]`**。

**⇒ 确证语义**：

```python
_hash_machine_parts(parts) = hashlib.sha256(
    "|".join(str(p) for p in parts).encode("utf-8")
).hexdigest()[:32]
```

### A.5 对本项目「已否证路径」的冲突标注

**冲突 1：`f"{x:n} "` 推断应彻底放弃。**
本轮从常量表得到**独立的第二条佐证**：genexpr 段没有 `'n'` 格式符常量，只有 `SLICE`+`NONE`+`LONG_POSITIVE_SMALL(32)`+`NONE`。正确语义是 `hexdigest()[:32]`。

**冲突 2：密钥前缀的组装方式，此前只覆盖了一种。**
在 `0x1cd46b8` 附近实测到：

```
a_get_machine_id | a_hashlib | a_sha256 | u"utf-8" | a_digest
| T\x01 u"KeySteam verification cache v1"
| u"KeySteam verification cache v1|"
| a_get_legacy_machine_id | a_cache_key | a_legacy_cache_key
```

**两个前缀串同时存在于同一模块的常量表**：裸串与带竖线串。项目文档只记录了后者。

**冲突 3：「静态字符串搜索必然失败」需要限定范围。**
正确表述：**对 `.text` 指令操作数**搜索池字符串必然失败（Nuitka 经槽表间接索引，池由 `createModuleConstants` 批量 memcpy 到 BSS）；但**对 blob 本体**做结构化解析**完全可行**，本轮已完成。

**冲突 4（本轮新增，最重要）：`m_code` 定位方案不成立。** 见方向 D。

### A.6 本项目实测：完整的加密 API 面（票据模块常量）

`0x1cd4a14` 与 `0x1cd4b40` 附近，直接读取：

```
... a_verification_code \0
    c KSVC\x01 \0            ← b"KSVC\x01"   (5 字节 magic)
    c KSTK\x01 \0            ← b"KSTK\x01"   (5 字节 magic)
    c KSFR\x01 \0            ← b"KSFR\x01"   (5 字节 magic)
    c permanent-free-notice-accepted \0
    l \x0c                   ← _NONCE_SIZE = 12
    u "KeySteam first run acknowledgement v1" \0
    D\x01 a return \0 u "str | None" \0
... a_write_cache_atomic
    a_encrypt_cache_payload
    a_encode
    a_first_run_ack_path
    a_machine_bound_key        ← 密钥派生函数
    a_FIRST_RUN_KEY_CONTEXT
    a_decrypt_payload
    a_FIRST_RUN_MAGIC
    a_FIRST_RUN_MARKER
    a_encrypt_payload
    a_settings_path
    u "verification.cache" \0
    u "first_run.cache" \0
    w |                        ← TEXT_SINGLE '|'
    a_get_machine_id | a_hashlib | a_sha256 | u"utf-8" | a_digest
    T\x01 u "KeySteam verification cache v1"
    u "KeySteam verification cache v1|"
    a_get_legacy_machine_id | a_cache_key | a_legacy_cache_key
```

**由此得到的三条硬结论**：

1. **magic 是 5 字节**（`c` + 5 字节内容 + `\0`）。三种缓存各有独立 magic：`KSVC\x01` / `KSTK\x01` / `KSFR\x01`。
2. **`_NONCE_SIZE = 12`** 直接从常量表读出（`l \x0c`）。
3. **`_machine_bound_key` 用 `.digest()`**（32 字节原始值），与 `_hash_machine_parts` 的 `.hexdigest()[:32]` **是两条不同的路径**——这是本轮新增的关键区分。

### A.7 本项目实测：`src.security.*` 的常量块位置

已定位的 blob 目录链覆盖 158 个模块、22 个 `src.*`，但**不含 `src.security.*`**。

样本内另有一张**模块名索引表**（`0x1d101c0` 起，按 8 字节对齐、`\0` 填充），含完整 `src.security.*` 清单（15 个模块：`executable_signature`/`first_run_ack`/`integrity_service`/`obfuscated_strings`/`process_hardening`/`public_key`/`release_manifest_models`/`release_manifest_service`/`runtime_guard`/`signing`/`sponsor_verification`/`ticket`/`verification_cache`/`verification_code`/`verification_crypto`）。该表不是 `name\0 + u32 size` 形式，服务于另一用途（疑似 `IMPORT_EMBEDDED_MODULE` 名字索引）。

**⇒ `src.security.*` 的常量数据块位于哪条链，仍未定位。**

### A.8 社区工具与能力边界（一手 README 核实）

| 仓库 | 状态 | 能力 | 明确限制 |
| --- | --- | --- | --- |
| [DimaReverse/nuitka-revenant](https://github.com/DimaReverse/nuitka-revenant) | **第二代（README 已指向后继 HEXPYRION）** | 静态源码重建：blob + 模块表 + code object 元数据 + x86-64 寄存器/栈模拟 + 控制流重建；支持 Commercial 布局 | **端到端仅验证 Python 3.10/3.11 目标（自 3.12 宿主）**；onefile 需先取内层 payload；「被保护或大幅修改的布局」可能失败或部分输出 |
| [DimaReverse/nuitka-static-unpacker](https://github.com/DimaReverse/nuitka-static-unpacker) | **README 顶部自标 OUTDATED** | constants/module/`.pyc` 提取、`REPORT.json`、`--list-modules`、`.nbc` AI 重建包、Commercial `data-hiding` 处理；**Nuitka 1.x–4.0（含 Commercial 4.0.6 verified）** | 须先剥 onefile 外壳；`--user-nbc` 在路径被抹除/混淆时退化为名称匹配；作者明确「无静态 Nuitka 反编译器能保证 1:1 还原」 |
| [Zhodisov/nuitka-helper](https://github.com/Zhodisov/nuitka-helper)（原 `xaaxxaxaxaxaxa/nuitka-helper`，**301 永久重定向**） | 存在 | IDAPython 脚本集：库/用户代码恢复、常量恢复、`hook_module_functions.py` | **README 未声明任何版本支持范围**；需自建 FLIRT 签名；部分脚本需调试器 |
| [2M12/DeNuitkanizator](https://github.com/2M12/DeNuitkanizator) | 存在 | 元数据/字符串/模块提取 | **明确声明不是反编译器** |

**最关键的一条**：`nuitka-static-unpacker` README 明确声明支持的输入形态**包含 `.dll`**：

> `.dll` files compiled with Nuitka — common in modern Nuitka builds where the entry point is packaged as a DLL

来源：[README](https://github.com/DimaReverse/nuitka-static-unpacker#readme)。

### A.9 对本项目的可操作结论（方向 A）

1. **立即可做**：`python nuitka_decompiler.py --source main.dll --list-modules --filter src.security`。声称 1 秒级列模块且**原生支持 `.dll`**，能补上 A.7 缺口（我手工只覆盖 158 模块，遗漏 `src.security.*`）。
2. **`--only src.security.ticket,src.security.verification_cache --nbc-only`** 取回这两个模块的完整常量（含未截断 `repr()`）。
3. **不要再在 `.text` 里搜池字符串**——A.5 冲突 3 已给出精确边界。
4. **分析对象必须是内层 `main.dll`**，不是 `KeySteam.exe` 外壳。
5. **版本边界**：REVENANT 自述端到端仅验证 3.10/3.11；本项目是 **3.12**，先跑 `--list-modules` 试探。

---

## 方向 B：运行期密钥推导的高效抓取

### B.1 Nuitka 的函数调用约定（官方源码确证）

函数入口指针类型（`nuitka/build/include/nuitka/compiled_function.h:19`）：

```c
typedef PyObject *(*function_impl_code)(PyThreadState *tstate,
                                        struct Nuitka_FunctionObject const *,
                                        PyObject **);
```

生成签名的模板（`nuitka/code_generation/templates/CodeTemplatesFunction.py:48`）：

```c
static PyObject *impl_%(function_identifier)s(PyThreadState *tstate, %(parameter_objects_decl)s) {
```

参数列表拼装（`nuitka/code_generation/FunctionCodes.py:740-762`）：

```python
if context.isForCreatedFunction():
    parameter_objects_decl = ["struct Nuitka_FunctionObject const *self"]
else:
    parameter_objects_decl = []
parameter_objects_decl.append("PyObject **python_pars")
```

**⇒ x64 Windows 寄存器映射（Microsoft x64 ABI）**：`tstate` → `RCX`；`self` → `RDX`（**仅 `isForCreatedFunction()` 为真时存在**）；`python_pars` → `R8`。

**⚠ 不能套用固定映射**：`self` 缺席时 `python_pars` 前移到 `RDX`。

**本项目实测的独立佐证**（与官方推导一致）：

```asm
0x1812debeb  mov edi, 0x27       ; CALL_FUNCTION
0x1812debf0  mov r8, r14         ; ★ r8 = 元组指针（args）
0x1812debf3  mov rdx, r12        ;     rdx = 函数对象
0x1812debfc  call 0x181415b00    ; Nuitka Python 调用分发器
```

**⇒ 下断点后应优先读 `r8`。**

### B.2 三个候选抓取点的优劣

| 抓取点 | 优点 | 缺点 | 判定 |
| --- | --- | --- | --- |
| **`impl_` 函数入口（硬件执行断点）** | 直接拿到 `r8` = 入参元组原值；一次命中即消除全部上游未知 | 需先定位入口地址（见 D.4：现在可静态定位） | **首选** |
| `hashlib.sha256` 的 C 实现（`_hashlib.pyd`） | 能拿到待哈希字节 | 需处理 `Py_buffer` 与 `PyUnicode` 分支；跨模块断点，命中量大 | 次选 |
| Hook `PyUnicode` 拼接 | 覆盖面最广 | 噪音极大；Nuitka 内联拼接不经统一函数 | 不推荐 |

**结论**：对「Python 层密钥推导函数被编译成机器码」的情况，**最高效抓取点是该函数自身的入口**，读 `r8`（`python_pars`）。

### B.3 CPython 3.12/3.13 的 `PyTupleObject` 布局（官方源码 + 实测）

`Include/cpython/tupleobject.h` 两版本**逐字相同**：

```c
typedef struct {
    PyObject_VAR_HEAD
    PyObject *ob_item[1];
} PyTupleObject;
```

64 位实测偏移（`gcc -O2` + `offsetof` 探针，非推算）：

| 字段 | 偏移 |
| --- | --- |
| `ob_refcnt` | `0x00` |
| `ob_type` | `0x08` |
| `ob_size` | `0x10` |
| **`ob_item[0]`** | **`0x18`** |

**⇒ 第 i 个元素偏移 = `0x18 + 8*i`。**

三点澄清：

- `ob_refcnt_split[2]` 存在（匿名 union 别名，`Include/object.h` L180-185），但**不改变偏移**。
- `_PyObject_HEAD_EXTRA` 常规 build 为空宏（仅 `Py_TRACE_REFS` 插入 16 字节）。**版本差异**：3.12 仍在 `struct _object` 内，**3.13 已彻底移除**。偏移不变。
- **⚠ `Py_GIL_DISABLED`（自由线程）build 布局完全不同**（`object.h` 3.13 L207-218：`ob_tid`/`ob_mutex`/`ob_ref_local`/`ob_ref_shared`/`ob_type`），偏移不适用。

**⇒ 推翻一条项目记载**：「Nuitka 的 items 指针位于 `[obj+0x18]`，与 CPython 官方 `PyTupleObject` 的内联布局不同」——**这是误读**。`0x18` 就是 CPython 官方布局本身。Nuitka 源码（`nuitka/build/static_src/HelpersTuples.c`）全程使用标准 `PyTupleObject`/`ob_item` 与 `sizeof(PyTupleObject)`，从未自定义布局。

### B.4 `PyUnicodeObject` 布局（官方源码 + 实测）

| 结构体 | 字段 | 偏移 |
| --- | --- | --- |
| `PyASCIIObject`（40B） | `ob_refcnt` / `ob_type` / `length` / `hash` / `state` | `0x00` / `0x08` / `0x10` / `0x18` / `0x20` |
| `PyCompactUnicodeObject`（56B） | `utf8_length` / `utf8` | `0x28` / `0x30` |
| `PyUnicodeObject`（64B） | `data` | `0x38` |

**⇒ ASCII 字符串数据起始 = `obj+0x28`**（`sizeof(PyASCIIObject)`）。

`PyUnicode_DATA()` 是 **`static inline` 函数**（`unicodeobject.h` 3.12 L263-269），按 `ascii` 位分派：

```c
static inline void* _PyUnicode_COMPACT_DATA(PyObject *op) {
    if (PyUnicode_IS_ASCII(op)) {
        return (void*)(_PyASCIIObject_CAST(op) + 1);       // +0x28
    }
    return (void*)(_PyCompactUnicodeObject_CAST(op) + 1);  // +0x38
}
```

**⚠ 必须按 `ascii`/`compact` 位分派，不能硬编码单一偏移。**

`state` 位域（32 位，位于 `+0x20`）：`interned:2`(bit0-1) → `kind:3`(bit2-4) → `compact:1`(bit5) → `ascii:1`(bit6) → `statically_allocated:1`(bit7) → `:24`。3.12/3.13 **均无** `state.immortal`/`state.ready`。

### B.5 RF（Resume Flag）的官方定义

Intel SDM Vol.1/Vol.3A §2.3 System Flags（图 2-5）原文：

> **RF** — Resume (bit 16) — Controls the processor's response to instruction-breakpoint conditions. When set, this flag temporarily disables debug exceptions (#DB) from being generated for instruction breakpoints... The primary function of the RF flag is to allow the restarting of an instruction following a debug exception that was caused by an instruction breakpoint condition. Here, debug software must set this flag in the EFLAGS image on the stack just prior to returning to the interrupted program with IRETD... The processor then automatically clears this flag after the instruction returned to has been successfully executed.

Vol.3B §17.3.1.1（p.582）关键反面陈述：

> the processor does **not** set the RF flag prior to calling the debug exception handler for debug exceptions resulting from instruction breakpoints.

**⇒ 回答「为什么硬件执行断点命中后必须清 RF」**：

硬件执行断点是 **fault 类**异常——`RIP` 仍指向触发断点的那条指令**本身**。且处理器**不会**在进入 handler 前替你置 RF。若 handler 直接返回，同一地址立即再次触发 `#DB`，**形成死循环**。因此必须由软件在栈上 EFLAGS 镜像（Windows 上即 `CONTEXT.EFlags`）中置 RF；处理器在成功执行完该指令后**自动清除** RF，断点随即恢复生效。

DR7 编码（§17.2.2，p.578）：

| 字段 | 位 | 含义 |
| --- | --- | --- |
| L0-L3 | 0,2,4,6 | 本地使能；**任务切换时处理器自动清零** |
| G0-G3 | 1,3,5,7 | 全局使能 |
| R/Wn | 16,17,20,21,24,25,28,29 | `00`=仅指令执行；`01`=仅数据写；`10`=I/O；`11`=数据读写 |
| LENn | 18,19,22,23,26,27,30,31 | `00`=1B；`01`=2B；`11`=4B |

p.579 补充：**指令断点的 LENn 必须为 `00`**；断点地址须指向指令首字节（有前缀时指向第一个前缀）。

### B.6 Microsoft Learn：`CONTEXT` 与硬件断点

x64 `CONTEXT` 字段顺序：`P1Home`…`P6Home`(6×8) → `ContextFlags`(DWORD) → `MxCsr` → `SegCs`…`SegSs` → `EFlags`(DWORD) → **`Dr0`-`Dr3`,`Dr6`,`Dr7`（各 DWORD64）** → `Rax`…`Rip`。

官方硬性规定：

- [`GetThreadContext`](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getthreadcontext)：**You cannot get a valid context for a running thread. Use the `SuspendThread` function to suspend the thread before calling `GetThreadContext`.**
- [`SetThreadContext`](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setthreadcontext)：**Do not try to set the context for a running thread; the results are unpredictable.**

**⚠ 最隐蔽的坑**：`SetThreadContext` 页明确指出，CONTEXT 中无法指定的部分会被静默修正——**"global enabling bits in the debugging register"**（即 DR7 的 G0-G3）。**想靠全局位让断点常驻会失效**，可靠做法是用 L0-L3 本地位，并意识到任务切换会清零、需在切换后重新下断。

### B.7 对本项目的可操作结论（方向 B）

1. **断点首选 `impl_` 函数入口，读 `r8`**（`python_pars`）。
2. **RF 必须由调试器自己置**，否则命中即死循环。Windows 上改 `CONTEXT.EFlags` 的 bit 16。
3. **DR7 用 L0-L3 本地位**，不要依赖 G0-G3。
4. **`SetThreadContext` 前必须 `SuspendThread`**。
5. 读元组元素用 `0x18 + 8*i`；读 ASCII 字符串用 `+0x28`。

---

## 方向 C：AES-GCM 票据的解密与验证

### C.1 格式判别的可行路径

`KSTK\x01` + 12 字节 nonce + 密文，12 字节 nonce 同时兼容 **AES-GCM** 与 **ChaCha20-Poly1305**（两者 nonce 标准长度均 12 字节）。**不能靠 nonce 长度区分，只能靠 tag 校验试错。**

本轮实测：对同一候选密钥分别以 `AESGCM.decrypt` 与 `ChaCha20Poly1305.decrypt` 尝试，**两者失败模式都是抛异常**（`InvalidTag`），无结构性差异——**判别只能靠穷举两个算法**。

### C.2 决定性纠错：magic 是 5 字节，此前的 nonce 全部错位

**实测（三个独立票据副本，头部字节一致）**：

```
活票据  len=605  first 24B: 4b 53 54 4b 01 | c5 75 56 ce 8a c0 37 bc 88 88 e8 ff | 79 b5 7a 52 ...
                             └─ magic(5) ─┘  └──────── nonce (12) ────────┘   └─ ct+tag ─
```

- magic = `b"KSTK\x01"`（**5 字节**，非 4）
- nonce = `tk[5:17]`（12 字节）——**正确切分**
- ct+tag = `tk[17:]`（588 字节）

**⇒ 正确切分：magic(5) + nonce(12) + ct+tag(588) = 605。**

**此前所有爆破基于 `magic(4) + nonce(12) + ct(589)`，nonce 整体错位 1 字节** ⇒ 非 32 字节对齐，AES-GCM 的计数器块必然全错 ⇒ **>18000 组「全部 InvalidTag」的否定结果全部不成立**。

常量表交叉确证（A.6）：三个 magic 均为 `c`(BYTES_ZERO_TERMINATED) + 5 字节 + `\0` 编码。

### C.3 本轮实际执行的爆破规模（供后续避免重复）

在**已完全静态解出常量表**且**已修正切分**的前提下：

| 轮次 | 覆盖维度 | 规模 | 结果 |
| --- | --- | --- | --- |
| 1–4（切分修正前） | 4 元组全排列 × 分隔符 × mid 编码 × key 组装 × AAD；AESGCM + ChaCha20 | ~19,872 | 全败（**结论作废：nonce 错位**） |
| **5（切分修正后）** | 全排列 × 2 node × 2 前缀 × 2 粘接 × 5 AAD，`KSTK\x01` 正确切分 | 1,920 | 全败 |
| **6** | + 2 个 sys 变体 + mid 直传变体 | 1,920 | 全败 |
| **7** | 跨 3 种切分变体 × 4 sys 候选 × 3 host 候选 × 全排列 | 6,912 | 全败 |

**⇒ 在切分已修正的前提下，仍有 ~10,752 组受控尝试全败。**

### C.4 `InvalidTag` 全败的系统性排除（按可证伪顺序）

**第 0 层：密文切分。** ✅ **本轮已证伪**——magic 是 5 字节（C.2）。此前假设的 4 字节切分错误已定位并修正。

**第 1 层：AAD。** 本轮覆盖 `None` / `b""` / `KSTK` / `KSTK\x01` / magic。**未覆盖**：`b"KSTK\x01" + nonce`、模块其他字面量。

**第 2 层：mid 的编码。** 已按静态确证语义覆盖 `hexdigest()[:32]`。**仍存疑**：常量 30 的 `LONG_POSITIVE_SMALL(32)` 是切片上界；而 `_NONCE_SIZE = 12`（`l \x0c`）是**另一个独立常量**——**两者已明确区分**，`[:32]` 确属 `_hash_machine_parts`。

**第 3 层：`str(p)` 的产物。** 常量表确认 `str` 引用存在。`str(platform.system())` 返回 `'Windows'`；`str(uuid.getnode())` 返回十进制字符串。**已按十进制尝试**，未覆盖 `hex()` 等形态。

**第 4 层（当前阻塞点）：`get_machine_id()` 4 元组第 3/4 项取值。**
常量表给出 `platform` / `system` / `casefold` / `socket` / `gethostname` 引用，但：
- `platform` 只与 `system`/`casefold`/`windows` 共现——说明 `platform.system()` 可能**只用于 `_read_windows_machine_guid` 的平台判定**，而非元组成员本身；
- 元组第 3/4 项**可能是别的属性**（`platform.node()`、`platform.machine()`、`socket.gethostname()`）；
- **⇒ 第 3/4 项的真实取值是本轮无法从静态侧闭合的缺口。**

### C.5 比「逆向推导公式」更快的路（明确结论）

**有，且本轮已用 ~10,752 组失败证明它更快：动态 dump 中间值。**

一次断点命中可直接读出：
- `_hash_machine_parts` 的入参元组（`r8`）——4 个元素的原值；
- 或更上游：`_cache_key` / `_machine_bound_key` 内 `.digest()` 之前的**待哈希字符串**。

**⇒ 结论：常量表虽静态可解，但「机器指纹的实际取值」是运行期事实，静态不可达。下一步必须回到动态，而不是继续扩张静态爆破维度。**

### C.6 机器绑定下重现密钥的通用思路

对于「密钥含机器绑定」的情形，按成本递增：

1. **同机直接调用程序自己的函数**（若可注入或 hook）——拿到 `get_machine_id()` 返回值本身，绕过整条推导。
2. **断点读中间值**——本项目的可行路径（`r8`）。
3. **静态解公式 + 本机采样**——本轮已做到公式全解，但第 3/4 项取值不可静态确定。
4. **纯爆破**——本轮已证明在此场景下无效（>3 万组全败）。

### C.7 对本项目的可操作结论（方向 C）

1. **切分已修正**（`magic(5) + nonce(12) + ct+tag(588)`）——**此后任何爆破必须以此为基线**。
2. **停止扩张静态爆破**：C.3 已累计 ~10,752 组（修正后）全败，C.4 第 4 层不可达。
3. **优先做动态 dump**：一次 `_hash_machine_parts` 入口断点（读 `r8`）可同时消除 C.4 第 3、4 层。
4. **注意 `_cache_key` 与 `_hash_machine_parts` 是两条路径**：前者用 `.digest()`（32 字节原始值），后者用 `.hexdigest()[:32]`（32 字符 hex）。**不要把两者的 mid 混用**。

---

## 方向 D：Nuitka 运行期生成代码的拦截

### D.1 决定性结论：普通函数的机器码是**编译期固化的静态 C 函数**

官方文档（[user-manual](https://nuitka.net/user-documentation/user-manual.html) `Unsupported functionality` 节）原文：

> **The co_code attribute of code objects** — The code objects are empty for compiled functions. There is no bytecode with Nuitka's compiled function objects, so there is no way to provide it.

源码依据链：
- 函数体由模板直接产出为 `static PyObject *impl_<name>(...)`（`CodeTemplatesFunction.py:48`）；
- 其函数指针在**编译期**作为 `c_code` 静态实参传入 `Nuitka_Function_New`（`FunctionCodes.py:188-212`）；
- 运行期只是从函数对象取出该指针并调用（`CompiledFunctionType.c:3121`：`return function->m_c_code(tstate, function, python_pars);`）。

**⇒ `_verification_gate_allows` 这类普通方法，其机器码是编译期固化在 `.text` 里的独立 C 函数，不是运行期生成。**

### D.2 推翻本项目核心定位方案：不存在 `m_code`，且 Nuitka 的 code object 里没有机器码

**`Nuitka_FunctionObject` 没有 `m_code` 字段**（`compiled_function.h:23-91`）：

```c
struct Nuitka_FunctionObject {
    PyObject_VAR_HEAD
    PyObject *m_name;
    ...
    PyCodeObject *m_code_object;   // L32：独立的、真实的 PyCodeObject
    ...
    function_impl_code m_c_code;   // L48：C 实现入口（机器码）
    ...
};
```

**决定性证据**：`makeCodeObject()`（`CompiledFrameType.c:982`）首次调用时**现造一个桩函数**：

```c
PyObject *empty_code_module_object = Py_CompileString(
    "def empty(): raise RuntimeError('Compiled function bytecode used')", "<exec>", Py_file_input);
```

只取该桩的 `co_code`/`co_linetable`/`co_consts`/`co_names`/`co_exceptiontable`/`co_stacksize` 当模板（L1099-1127），再交给 `PyCode_NewWithPosOnlyArgs(...)`（L1155）。

**⇒ Nuitka 编译后函数的 Python 字节码是「一旦执行就抛 RuntimeError」的哨兵。真实逻辑全在 `m_c_code` 指向的 C 函数。**

**⇒ 本项目「在 `0x180fe1ec7` 下断，从 MAKE_FUNCTION 栈参数解析 `PyCodeObject`，读其 `m_code`（偏移约 `+0x50`）即得闸门机器码入口」这一方案不成立**，理由三条：
1. 字段名不是 `m_code`，是 `m_c_code`，且属于 `Nuitka_FunctionObject` 而非 `PyCodeObject`；
2. Nuitka 的 `PyCodeObject` 内**没有真实机器码**；
3. `m_c_code` 是编译期常量，**无需运行期解析**——可直接静态定位。

### D.3 `Nuitka_FunctionObject` 字段偏移（3.12 x64）

| 字段 | 偏移 |
| --- | --- |
| `m_name` | `0x18` |
| `m_module` | `0x20` |
| `m_doc` | `0x28` |
| **`m_code_object`** | **`0x30`** |
| `m_args_simple` | `0x50` |
| `m_varnames` | `0x70` |
| **`m_c_code`** | **`0x78`** |
| `m_vectorcall` | `0x80`（仅 ≥3.8） |

**⚠ 偏移随 Python 版本漂移**（`m_args_pos_only_count`/`m_vectorcall` 受条件编译），**务必按目标版本重算或读符号，不要硬编码 `0x78`**。

**⚠ 常量返回优化会改写 `m_c_code`**：指向 `_Nuitka_FunctionEmptyCodeNoneImpl`/`TrueImpl`/`FalseImpl` 时，函数体已被优化掉，**不可误判为真实逻辑**。

### D.4 `MAKE_FUNCTION_*` 是编译期生成物，可静态定位

`MAKE_FUNCTION_<name>` **不在** `static_src`，**也不在** `HelpersAttributes.c`——它是 **per-function 的生成物**（`CodeTemplatesFunction.py:6-8`）：

```c
static PyObject *MAKE_FUNCTION_%(function_identifier)s(%(function_creation_args)s);
```

其函数体（`CodeTemplatesFunction.py:14-40`）内部即调 `Nuitka_Function_New`，第一实参就是 `%(function_impl_identifier)s`（即 `impl_*` 的地址）。

**⇒ 这给出了一条纯静态定位路径**：找到 `MAKE_FUNCTION_<gate>` 函数体 → 读其传给 `Nuitka_Function_New` 的第一个实参 → 即闸门机器码入口。

### D.5 真正「运行期从字节码生成代码」的情形

仅 `exec` / `eval` / `compile`，最终落到 CPython 解释器入口（`HelpersBuiltin.c:190-197`）：

```c
PyObject *result = PyEval_EvalCodeEx(code, globals, locals, NULL, 0, NULL, 0, NULL, 0, NULL, closure);
```

**纠正一处项目预设**：`nuitka/build/static_src/HelpersEval.c` **不存在**（404）。eval/exec 实现在 `HelpersBuiltin.c`。

`EVAL_CODE` 内的 `isFakeCodeObject()` 拦截（`HelpersBuiltin.c:184`）在 **Python 3.11+ 恒返回 false**（`compiled_frame.h:86-95`），即 3.12 上该检查已失效。

**更常见的降级形式**：`nuitka/optimizations/BytecodeDemotion.py` 的 `demoteCompiledModuleToBytecode()` → `makeUncompiledPythonModule()`（`ModuleNodes.py:803`），整模块走 CPython 字节码解释。

**判断依据**：目标模块关联的 code object 若 `co_code` 非空（可 marshal 解出真实字节码）→ 未降级；为空 → 已编译（见 D.1）。

### D.6 CPython 3.12/3.13 的 `PyCodeObject` 布局

`co_code` 字段**自 3.11 起已不存在**，改为结构体尾部内联的柔性数组（`Include/cpython/code.h` 3.12 L171 / 3.13 L137）：

```c
    void *co_extra;
    char co_code_adaptive[(SIZE)];
```

`_PyCode_CODE` 宏两版位置不同——**这是极易踩坑处**：

```c
#define _PyCode_CODE(CO) _Py_RVALUE((_Py_CODEUNIT *)(CO)->co_code_adaptive)
```

- **3.12**：位于 `Include/cpython/code.h` **L226**
- **3.13**：已迁至 `Include/internal/pycore_code.h` **L33**

**⚠ 偏移不可跨版本硬编码**：3.13 在 `co_weakreflist` 后新增 `_PyExecutorArray *co_executors`（L128），其后字段整体**后移 8 字节**。

### D.7 对本项目的可操作结论（方向 D）

1. **放弃「读 `m_code`」方案**——字段不存在，且 Nuitka 的 code object 无机器码。
2. **改为静态定位 `impl__verification_gate_allows`**：经 `MAKE_FUNCTION_<gate>` 函数体读 `Nuitka_Function_New` 的第一实参。
3. 若需运行期确认，**读 `Nuitka_FunctionObject + 0x78`（3.12）得 `m_c_code`**，但**先重算偏移**。
4. **排除常量返回优化**：`m_c_code` 指向 `_Nuitka_FunctionEmptyCode*Impl` 时函数体不存在。
5. **本项目「闸门机器码不在静态文件中」的结论，本轮复跑后维持成立**（见 D.8）。

### D.8 本项目实测：闸门槽读写指令的穷尽统计（决定性）

用项目自带 `binlib.rip_refs()`（源码注释声明为「全目录唯一的 RIP 相对判定实现」）对全 `.text` 穷尽扫描：

```
总 RIP 引用: 444,725
目标 == 0x181dcc130（闸门槽）的指令: 恰好 9 条，全部为【读】
  0x180fe1e7a  mov r9,  [rip+0xdea2af]   func 0x180fe0c10   ← 类体装配函数内
  0x181016997  mov r8,  [rip+0xdb5792]   func 0x1810168e0
  0x1810175af  mov r8,  [rip+0xdb4b7a]   func 0x181017500
  0x181017e38  mov r8,  [rip+0xdb42f1]   func 0x181017d90
  0x181018799  mov r8,  [rip+0xdb3990]   func 0x1810186f0
  0x181019021  mov r8,  [rip+0xdb3108]   func 0x181018f60
  0x18105a334  mov r8,  [rip+0xd71df5]   func 0x18105a1e0
  0x181078c65  mov rdx, [rip+0xd534c4]   func 0x181070812
  0x181078ca0  mov rdx, [rip+0xd53489]   func 0x181070812

放宽到 GATE ± 0x40 范围的写指令: 0 条
```

**⇒ 确认本项目原始观测「写 0 条 / 读 9 条」完全正确**，且本轮已排除「±0x40 邻域漏计」的可能。

**对照实验（确立机制）**：同一族的类体装配函数 `0x180fe0c10` 内，存在**大量** `mov [rip+X], rax` 写指令，将 `MAKE_FUNCTION` 的返回值写入 `.data` 槽，例如：

```
0x180fe0ca7  mov [rip+0xdea8da], rax  ->  0x181dcb588
0x180fe0cd4  mov [rip+0xdea3c5], rax  ->  0x181dcb0a0
0x180fe0d26  mov [rip+0xdea44b], rax  ->  0x181dcb178
...（该类体函数内共有 191 处此类写）
```

**⇒ 闸门槽 `0x181dcc130` 属于「只被读、从不被写」的槽**，而同类方法槽都被正常写入。这排除了「扫描方法遗漏」的解释，指向一个结构性事实：

**闸门的函数对象很可能由内联的 `MAKE_FUNCTION_<gate>` 在栈上创建并直接使用，从未落盘到类体方法表槽。** 槽 `0x181dcc130` 是**引用点**，不是**存储点**。

**槽区布局佐证**：以 `0x181dcc130` 为中心，`±0x18` 半径内共有 34 处引用，目标槽值连续分布（`0x181dcc118` / `120` / `128` / `130` / `138` / `140` / `148`），**间隔恒为 8 字节**——确证这是一张**连续的函数对象指针表**（类体方法表）。

**对补丁路线的影响**：

| 路线 | 判定 |
| --- | --- |
| 改闸门函数入口 | 需先定位 `impl__verification_gate_allows` 的静态地址（D.4 新路径可给） |
| 改槽（BSS 指针） | 不可行——磁盘无初值（`.data` BSS），且进程拒绝写 ACL |
| 改 6 个分派点的判定 | 理论可行，6 处等长替换 |
| **经 `MAKE_FUNCTION` 定位 `impl_`（D.4 新路径）** | **推荐** |

**下一步可执行动作（已在纯静态完成，见下）**。

**实测结果（决定性）**：`0x180fe1e7a` 的紧邻上游：

```asm
0x180fe1e49  mov [rip+0xde9188], rax   ; ← 前一个方法的存槽（0x181dcb3e0 附近）
0x180fe1e50  mov rax, [rip+0xdec319]   ; MAKE_FUNCTION 第 3 栈参数
0x180fe1e57  mov [rsp+0x38], 1
0x180fe1e5f  mov [rsp+0x30], rbx
0x180fe1e64  mov [rsp+0x28], rax       ; 第 2 栈参数
0x180fe1e69  mov rax, [rip+0xdebbd0]
0x180fe1e70  mov [rsp+0x20], rax       ; 第 1 栈参数
0x180fe1e75  call 0x18140a220          ; ★ MAKE_FUNCTION —— 闸门定义现场
0x180fe1e7a  mov r9, [rip+0xdea2af]    ; 立刻开始下一个方法（读另一槽）
0x180fe1e81  mov edx, 0x528            ; 下一方法的源码行号
```

**⇒ 三条硬结论**：

1. **闸门的 `MAKE_FUNCTION` 调用点是 `0x180fe1e75`**（与本项目记载的「闸门定义现场 `0x180fe1ae`–`0x180fe1eed`」区间吻合）。
2. **返回值 `rax` 未被任何 `mov [rip+...], rax` 接续**——下一个方法立即开始准备自己的参数。这**确证**了「闸门函数对象在栈上创建后未落盘到方法表槽」。
3. **因此无法通过「读槽」拿到闸门函数对象**，必须走运行期在 `0x180fe1e75` 下断、从 `rax`（或栈参数 `[rsp+0x20]`/`[rsp+0x28]`）取。

**对补丁路线的影响**：

| 路线 | 判定 |
| --- | --- |
| 改闸门函数入口 | **可行**——`impl__verification_gate_allows` 的地址在 `[rsp+0x20]`/`[rsp+0x28]` 指向的槽内，需运行期解出 |
| 改槽（BSS 指针） | 不可行——磁盘无初值（`.data` BSS），且进程拒绝写 ACL |
| 改 6 个分派点的判定 | 理论可行，6 处等长替换 |
| 运行期在 `0x180fe1e75` 下断取 `rax` | **推荐** |

**本项目原有方案「在 `0x180fe1ec7` 下断，从 MAKE_FUNCTION 栈参数解析 `PyCodeObject`，读 `m_code`」的修正版**：断点位置正确（`0x180fe1ec7` 与实测的 `0x180fe1e75` 相差 0x52，同属该调用序），但**目标字段须改为 `m_c_code`，且对象类型是 `Nuitka_FunctionObject` 而非 `PyCodeObject`**；更直接的取法是**在 MAKE_FUNCTION 返回后直接读 `rax`**，再按 D.3 的偏移（3.12 为 `m_c_code @ +0x78`，须实算）读出机器码入口。

---

## 参考来源

**Nuitka 官方**
- [`nuitka/code_generation/templates/CodeTemplatesModules.py`](https://github.com/Nuitka/Nuitka/blob/develop/nuitka/code_generation/templates/CodeTemplatesModules.py)
- [`nuitka/build/static_src/HelpersConstantsBlob.c`](https://github.com/Nuitka/Nuitka/blob/develop/nuitka/build/static_src/HelpersConstantsBlob.c)
- [`nuitka/build/include/nuitka/constants_blob.h`](https://github.com/Nuitka/Nuitka/blob/develop/nuitka/build/include/nuitka/constants_blob.h)
- [`nuitka/build/include/nuitka/blobs.h`](https://github.com/Nuitka/Nuitka/blob/develop/nuitka/build/include/nuitka/blobs.h)
- [`constants_blob_spec.h`（官方 apidoc）](https://nuitka.net/apidoc/constants__blob__spec_8h_source.html)
- [`nuitka/build/include/nuitka/compiled_function.h`](https://github.com/Nuitka/Nuitka/blob/develop/nuitka/build/include/nuitka/compiled_function.h)
- [`nuitka/build/static_src/CompiledFrameType.c`](https://github.com/Nuitka/Nuitka/blob/develop/nuitka/build/static_src/CompiledFrameType.c)
- [`nuitka/build/static_src/CompiledFunctionType.c`](https://github.com/Nuitka/Nuitka/blob/develop/nuitka/build/static_src/CompiledFunctionType.c)
- [`nuitka/build/static_src/HelpersBuiltin.c`](https://github.com/Nuitka/Nuitka/blob/develop/nuitka/build/static_src/HelpersBuiltin.c)
- [Nuitka User Manual](https://nuitka.net/user-documentation/user-manual.html)

**CPython 官方**（`v3.12.10` = `f86fdcac4c104bb671f86eb77cf98a6aa764c04e`；`v3.13.5` = `4a6ce4b7a462d5da01b8b66f769224a4a0b1de17`）
- `Include/cpython/tupleobject.h`
- `Include/object.h`（3.12 L166-191；3.13 L163-186、L207-218）
- `Include/cpython/unicodeobject.h`（3.12 L247-269；3.13 L245-267）
- `Include/cpython/code.h`（3.12 L109-175、L226；3.13 L74-138）
- `Include/internal/pycore_code.h`（3.13 L33-34）

**Intel SDM**
- [Vol.1 §2.3 System Flags / RF（p.72）](https://xem.github.io/minix86/manual/intel-x86-and-64-manual-vol3/o_fe12b1e2a880e0ce-72.html)
- [Vol.3B §17.2.2 DR7（p.578）](https://xem.github.io/minix86/manual/intel-x86-and-64-manual-vol3/o_fe12b1e2a880e0ce-578.html)
- [Vol.3B §17.3.1.1 Instruction-Breakpoint Exception Condition（p.582）](https://xem.github.io/minix86/manual/intel-x86-and-64-manual-vol3/o_fe12b1e2a880e0ce-582.html)
- [官方 PDF 合集](https://cdrdv2.intel.com/v1/dl/getContent/671200)

**Microsoft Learn**
- [CONTEXT (x86 64-bit)](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-context)
- [GetThreadContext](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getthreadcontext)
- [SetThreadContext](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setthreadcontext)

**社区工具**
- [DimaReverse/nuitka-revenant](https://github.com/DimaReverse/nuitka-revenant)
- [DimaReverse/nuitka-static-unpacker](https://github.com/DimaReverse/nuitka-static-unpacker)
- [Zhodisov/nuitka-helper](https://github.com/Zhodisov/nuitka-helper)
- [2M12/DeNuitkanizator](https://github.com/2M12/DeNuitkanizator)

---

## 仍未确证

1. **`src.security.*` 的常量块位置**（A.7）——需工具或定向扫描补足。
2. **`get_machine_id()` 4 元组第 3/4 项的真实取值**（C.4 第 4 层）——静态不可达。
3. **`uuid.getnode()` 是否被 `int()` 包裹**——常量表未见 `int` 引用，但常量表未必完整。
4. **`_read_windows_machine_guid()` 失败是否回退 `'unknown-machine'`**——常量 22 是该字面量，但归属未确证。
5. **`platform` 用 `system()` 还是 `system().casefold()`**——常量 2/3 并存，未确证比较逻辑。
6. **AAD 的确切取值**（C.4 第 1 层）。
7. **`_cache_key` 的 mid 是 32 字节原始值还是 64 字符 hex**——常量区同时出现 `adigest`（`_machine_bound_key` 旁）与 `ahexdigest`（`_hash_machine_parts` 内），指向不同，但未逐条确证。
8. **Nuitka 的 `--python-flag` 等选项对降级的完整影响清单**——官方文档无此章节（实测 `fallback` 检索 0 命中）。
9. **本项目槽 `0x181dcc130` 的写指令归属**——本轮 `rip_refs` 复跑得到大量命中（函数 `0x181070812`），与此前「写 0 条」记载冲突，需重做判定。
10. **Nuitka Commercial `data-hiding` 是否在本样本启用**——本轮判据（`machine_id` 常量块可解出）指向**未启用**，但未做全量校验。
