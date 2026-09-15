# 宿主契约（ticket #2 / issue #2）

本文件是 issue #2 的产出。它记录构建宿主前必须固定的决策与已实测的技术事实。

**状态**：已定。所有事实来自反汇编实测或工具链实测，来源标注在每节末尾。

---

## 1. 宿主语言：C

用现有 mingw64 工具链编译 C。不新增工具链。

此前「无 mingw」的结论有误——那是基于 PATH 搜索得出的。实测：

```
C:\Program Files\mingw64\bin\x86_64-w64-mingw32-gcc.exe   3024896 B
C:\Program Files\mingw64\bin\x86_64-w64-mingw32-g++.exe   3028480 B
x86_64-w64-mingw32-gcc.exe (x86_64-win32-seh-rev0, Built by MinGW-Builds project) 15.1.0
```

完整 GCC 15.1.0，含 C++ 前端 `cc1plus.exe`、`crt2.o`、`libucrt.a`。系统侧 `ucrtbase.dll` 与 `vcruntime140.dll` 齐备，链接与运行闭环。

**为什么不选 C#**：`main.dll` 静态导入 `python312.dll`，宿主必须把该依赖的解析强制到 payload 目录。而 `SetDllDirectoryW` / `SetDefaultDllDirectories` 是**进程级** API，在 CLR 宿主里改全局 DLL 搜索路径会波及运行时自身的原生依赖解析。C 宿主与 Nuitka 官方实现同构，且不需要碰这些 API。

**为什么不选 Python + ctypes**：`main.dll` 静态导入 `python312.dll`。Windows loader 按 basename 去重，若进程内已加载过同名模块，`main.dll` 会被链接到一个不经 Nuitka bootstrap 初始化的 CPython 运行时。`python.exe` 宿主本身就满足这个致命前提，`subprocess` 起新 `python.exe` 同样满足。此路已排除。

**构建互操作问题**：从 WSL 直接调用 mingw exe 会失败——

```
x86_64-w64-mingw32-gcc.exe: fatal error: cannot execute 'cc1': CreateProcess: No such file or directory
```

**根因不是「Windows exe 无法理解 WSL 的 Linux 路径」。** 这个解释看似合理，并被实测证伪：传入 Windows 原生路径 `gcc.exe 'D:\...\t.c' -o 'D:\...\t.exe'` **同样失败，报同样的 cc1 错误**。源码路径与输出路径都无关。

真实根因是**工具链搜索根的推导**。证据来自 gcc 自身：

```
$ gcc.exe -print-search-dirs
install:  D:/03_Work/03_Develop/keysteam-unlock-spike/../lib/gcc/x86_64-w64-mingw32/15.1.0/
programs: =D:/03_Work/03_Develop/keysteam-unlock-spike/../libexec/gcc/x86_64-w64-mingw32/15.1.0/;...
```

搜索根被推导为**当前工作目录**（`.../keysteam-unlock-spike/`），而非 `C:/Program Files/mingw64/`。于是 `../libexec/gcc/...` 指向一个不存在的位置，gcc 便找不到 `cc1.exe`。错误信息里的 "cc1" 是**误导**——`cc1.exe` 本身完好存在于 `C:/Program Files/mingw64/libexec/gcc/x86_64-w64-mingw32/15.1.0/`（41,524,736 B）。

**解法**：用 `-B` 显式指定工具链的四个搜索根。四个**缺一不可**，已逐个删除验证：

```bash
-B 'C:\Program Files\mingw64\libexec\gcc\x86_64-w64-mingw32\15.1.0\'   # cc1, collect2
-B 'C:\Program Files\mingw64\bin\'                       # as, ld
-B 'C:\Program Files\mingw64\x86_64-w64-mingw32\lib\'    # crt2.o, libmingw32.a
-B 'C:\Program Files\mingw64\lib\gcc\x86_64-w64-mingw32\15.1.0\'  # crtbegin.o, -lgcc
```

删第四项 → `cannot find -lgcc`；删第三项 → `cannot find crt2.o`。单个 `-B` 指向 mingw64 根**不行**——`-B` 是前缀而非递归根。

注意 `-B` 只解决**工具链定位**。头文件搜索是另一件事，需要单独的 `-I`（见 `host/build.sh`）。

**从 WSL 侧构建是可用的**，前提是加 `-B`。实测：连续两次构建产出字节一致的 `host.exe`。此前「构建必须从 Windows 侧发起」的说法是错的，已废弃。

解法见 `host/build.sh`（自动探测 libexec 版本号，用 `wslpath -w` 转换路径）与 `host/README.md`。

### 一个已特征化但未根因定位的故障

从 **Windows 侧**发起构建时，gcc 会出现「驱动在 spawn 子进程处静默死亡」：

| 命令 | 结果 |
|---|---|
| `gcc.exe --version` | exit 0 ✅ |
| `gcc.exe -### t.c` | exit 0 ✅（驱动逻辑正常） |
| `gcc.exe -v t.c -o out.exe` | **exit 1，stderr 完全为空**，`-v` 输出止于 `as.exe` 命令行 |
| `cc1.exe t.c -o manual.s` 直调 | exit 0 ✅（428 B 汇编） |
| `as.exe -o manual.o manual.s` 直调 | exit 0 ✅（768 B 目标文件） |

**组件全好，坏的是驱动的子进程 spawn。** 已实测排除：TEMP 不可写、空格路径（8.3 短路径同样失败）、Windows 侧加同样四个 `-B`、UCRT dll 缺失、杀软拦截。

此故障**不是间歇性的**——在探针中 5/5 必现。早先「有时能跑通」的判断来自误读：一次 `-v` 运行显示到达 `as.exe`，但那只是 gcc 打印了它**正在尝试**的命令，不代表执行成功。同时，该故障只影响 Windows 侧发起路径，而 `build.sh` 走 WSL 侧，不受影响。`build.ps1` 因此标注为 documented dead end。

---

## 2. `run_code` 签名：三参数

```c
int run_code(int argc, wchar_t **argv, const wchar_t *dll_filename);
```

**证据一——`main.dll` 入口反汇编**（RVA `0x143b380`，ImageBase `0x180000000`）：

```
0x180143b380: sub  rsp,0x28
0x180143b384: mov  eax,ecx        ; arg1 -> argc 使用
0x180143b386: test r8,r8          ; arg3 判空
0x180143b389: je   +8
0x180143b38e: call 0x18014135e0   ; setDllFilename(arg3)
0x180143b395: call 0x180143a430
```

x64 调用约定：`rcx`=arg1、`rdx`=arg2、`r8`=arg3。三个寄存器都被使用。

**证据二——外层 `KeySteam.exe` 调用点**（RVA 0xbfc2–0xc013）：

```
0xbfc2: lea  rcx,[0x141d6f740]   ; 解包目录路径
0xbfc9: call [IAT 0x24028]       ; AddDllDirectory
0xbfcd: xor  edx,edx
0xbfd1: lea  rcx,[0x141d5d720]   ; 缓冲
0xbfd8: mov  r8d,0xd00
0xbfde: call [IAT 0x24108]       ; LoadLibraryExW
0xbfed: lea  rdx,[0x141d55a50]   ; "run_code"
0xbff4: mov  rcx,rax
0xbff7: call [IAT 0x240c8]       ; GetProcAddress
0xc006: lea  r8,[0x141d5d720]    ; arg3 = main.dll 路径
0xc00d: mov  rdx,r13             ; arg2 = argv
0xc010: mov  ecx,r12d            ; arg1 = argc
0xc013: call rax                 ; run_code(argc, argv, dll_path)
```

三寄存器齐填后才 `call`。参数**必须是宽字符** `wchar_t**`（UTF-16LE），不是 `char**`。

### 为什么不照 `boot.c` 写

外部参照实现 `nuitka-dll-bootloader/boot.c` 用的是**两参数**形式：

```c
typedef const wchar_t filename_char_t;
typedef wchar_t native_command_line_argument_t;
typedef int(__stdcall *nuitka_dll_function_ptr)(int, native_command_line_argument_t **);
```

它只填 `rcx`/`rdx`，`r8` 未设。在 x64 调用约定下 `r8` 读到调用者栈上的残留值，而入口的 `test r8,r8; je +8` 在 `r8==0` 时恰好跳过 `setDllFilename`——**这是踩了运气，不是正确调用**。

后果：`boot.c` 路线**静默丢掉 `main.dll` 的路径**。该路径决定 `getBinaryFilenameWideChars` 的返回值（进而是资源搜索基准与 `original_argv0` 的派生路径）：传 NULL 时程序回落到 `GetModuleFileNameW(NULL,...)`，报告的是 `main.dll` 自身而非宿主。`boot.c` 在这种状态下靠的是栈残留恰好为 0。

---

## 3. `argv[0]` 的取值

传一个**显式路径，以 `.py` 结尾**，建议：

```
<payload目录>\KeySteam.py
```

机制：程序用 `sys.argv[0]` 判定是否处于「源码运行」状态。判定形式（实测）为取字符串后 `strip()` + `casefold()`，再对 `(".py", ".pyw")` 做成员/后缀比较。

**修正 spec 原文**：spec 写的是 `Path(sys.argv[0]).resolve().suffix.strip().casefold() in ('.py','.pyw')`。实测常量区**无 `a_suffix` 属性名**，`suffix` 仅作局部变量名出现；而 `asuffix`、`astrip`、`acasefold` 与常量元组 `P\x02u.py\0u.pyw\0`（即 `(".py",".pyw")`）同段出现。故实际形式是字符串后缀比较，不是 `pathlib` 属性访问。**对本用途两者等价**，但依据不同。

相关常量命中（文件偏移）：

| 字符串 | 偏移 |
|---|---|
| `P\x02u.py\0u.pyw\0`（元组） | `0x1ccecd0` 段内（VA `0x01cd04d0`） |
| `original_argv0` | `0x1d0de58` |
| `containing_dir` | `0x1d0dc38` |
| `NUITKA_ONEFILE_DIRECTORY` | `0x1d1a110` |
| `NUITKA_ONEFILE_TEMP` | `0x1cd1b15`, `0x1cd1fb0`, `0x1cf4efb` |
| `NUITKA_ONEFILE_BINARY` | **零命中** |

`main.dll` 中 `__argv` 与 `NUITKA_ONEFILE_BINARY` 均**零命中**；后者的职能由 `NUITKA_ORIGINAL_ARGV0` 承担。

---

## 4. `argv` 的来源

外层 `KeySteam.exe` 的 `argc`/`argv` 来自：

```
0xc16f: call [IAT 0x24030]   ; GetCommandLineW
0xc175: mov  rcx,rax
0xc178: lea  rdx,[rsp+0x50]  ; &argc
0xc17d: call [IAT 0x242d0]   ; CommandLineToArgvW  <-- 全文件唯一调用点
0xc18b: mov  r15,rax         ; r15 = wchar_t** argv
```

即 `argv` 直接来自**外层 exe 进程的原始命令行**，`argv[0]` 就是该 exe 自身路径。

宿主应同法构造：`CommandLineToArgvW(GetCommandLineW(), &argc)`，跳过第一个元素后透传，并把 `argv[0]` 替换为 `.py` 结尾的显式路径。

**未确证**：`0xc1d0–0xc466` 区间存在转义重写循环与 `argv[r14]` 索引访问，**未能确认 `argv[0]` 是否被原地替换**。该逻辑倾向仅重写参数转义，无决定性证据。宿主显式设定 `argv[0]`，不需要依赖这一点。

---

## 5. 第三参数不是环境块，是 `main.dll` 的路径

**本节是对先前错误结论的更正。** 本文档早先版本把第三参数当作环境块，据此给出了一套环境数组构造方案，并让 `host.c` 照此实现。**那个实现是错的。**

第三参数的类型是 `filename_char_t const *`（Windows 即 `wchar_t const *`），内容是**被加载的 `main.dll` 的绝对路径**，形式是**单个以 NUL 结尾的宽字符串**。

### 源码依据

```c
// OnefileBootstrap.c:930-976，runPythonCodeDLL
typedef int(__stdcall * nuitka_dll_function_ptr)(int, wchar_t **, wchar_t const *);
return (*nuitka_dll_function)(argc, argv, dll_filename);   // 第 956 行
```

```c
// MainProgram.c:2396-2403，接收方
NUITKA_DLL_FUNCTION int run_code(int argc, native_command_line_argument_t **argv,
                                 filename_char_t const *dll_filename) {
    if (dll_filename != NULL) { setDllFilename(dll_filename); }
    return Nuitka_Main(argc, argv);
}
```

`setDllFilename` 的完整实现（`HelpersFilesystemPaths.c:48`）只有一行赋值：`_pseudo_dll_filename = filename;`

### 反汇编依据（本机实测）

`setDllFilename` @ `0x1814135e0` —— **整个函数两条指令**：

```
48 89 0d c9 74 9d 00    mov [rip+0x9d74c9],rcx   ; _pseudo_dll_filename = rcx
c3                      ret
```

消费点 @ `0x1814137ae`（属 `getBinaryFilenameWideChars`）的复制循环：

```
48 8b 0d ...            mov   rcx,[rip+...]      ; rcx = _pseudo_dll_filename
66 83 39 00             cmp   WORD PTR [rcx],0    ; 单个 wchar 是否为 NUL
0f b7 01                movzx eax,WORD PTR [rcx]  ; 读一个 wchar
66 89 02                mov   WORD PTR [rdx],ax   ; 写一个 wchar
48 83 c1 02             add   rcx,0x2             ; 步进 2 字节
```

**只有一层解引用，按 wchar 线性遍历到单个 NUL 终止。**

- 若第三参数是 `wchar_t**` 指针数组，必须出现**两层**解引用（先取数组元素，再读字符串字符）。
- 若是 `NAME=VALUE\0` 扁平环境块，必须出现 `=` 分隔符处理或双 NUL 块尾判定。

**实测两者皆无。**

### 为什么这个错误很危险

把环境数组传给这个参数**不会崩溃**。`setDllFilename` 只是保存指针；消费点会把数组的首个槽当作字符数据读取——首个槽是别的指针值，于是被逐字节解释成"路径"，直到撞上某个 NUL。

结果是 `_pseudo_dll_filename` 指向垃圾路径，`getBinaryFilenameWideChars` 返回乱码，程序的路径推导全错，**但进程照常运行、不报错**。这是最难发现的一类失败。

### 正确用法

```c
AddDllDirectory(payload_dir);
HINSTANCE h = LoadLibraryExW(main_dll_path, NULL,
    LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32
  | LOAD_LIBRARY_SEARCH_USER_DIRS);
int (*run_code)(int, wchar_t **, const wchar_t *) =
    (void *)GetProcAddress(h, "run_code");
run_code(argc, argv, main_dll_path);   /* 第三参数 = main.dll 绝对路径 */
```

### 传 NULL 的行为

有显式处理，不是未定义行为。`if (dll_filename != NULL)` 被跳过，`_pseudo_dll_filename` 保持 NULL，`getBinaryFilenameWideChars` 回落到 `GetModuleFileNameW(NULL, ...)`（反汇编 `0x1814137c0: je 0x1814137f8` 即此分支），取**当前模块 `main.dll` 自身**的路径。

不崩，但 `__compiled__.original_argv0` 及派生路径会指向 `main.dll` 而非宿主。这是 `--no-envp` 开关的对照条件。

---

## 5b. 环境变量（经进程环境传递，与本参数无关）

| 变量 | 语义 | 来源 | 必需性 |
|---|---|---|---|
| `NUITKA_ONEFILE_DIRECTORY` | **宿主二进制所在目录**，不是解包目录 | `OnefileBootstrap.c:1357`：`setEnvironmentVariable("NUITKA_ONEFILE_DIRECTORY", stripBaseFilename(binary_filename))` | 由引导器设置 |
| `NUITKA_ORIGINAL_ARGV0` | `__compiled__.original_argv0` 的取值 | `OnefileBootstrap.c:1359` | **可选**，不设则回落为传入的 `argv[0]` |
| `NUITKA_ONEFILE_TEMP` | **不是 Nuitka 变量** | 官方源码零命中 | 与 Nuitka 无关 |

**`NUITKA_ONEFILE_TEMP` 的更正**：`main.dll` 中该串有 3 处命中（`0x1cd1b15`、`0x1cd1fb0`、`0x1cf4efb`），但全部是 **KeySteam 应用自己代码里的标识符**——三处上下文均与 `_MAIN_TEMP_ENV_NAME`、`aenviron`、`subprocess` env dict、`--watchdog` 相邻。Nuitka 官方无此运行时变量；真实存在的是编译期宏 `_NUITKA_ONEFILE_TEMP_BOOL` / `_NUITKA_ONEFILE_TEMP_SPEC`（解包目录模板，编译期已固化）。

解包目录**从不以环境变量外传**，只经第三参数把 `main.dll` 路径递进 DLL。

**`NUITKA_ORIGINAL_ARGV0` 不设的后果**（`MainProgram.c:1790-1816`）：环境变量不存在则不进 `if` 分支，随后 `original_argv0 = argv[0];` 兜底。不报错，不为 None。`getOriginalArgv0()` 里的 `assert` 在该赋值之后恒真，不构成风险；Windows 也不走 `NEEDS_ORIGINAL_ARGV0` 断言分支。

**设置它的唯一理由**：让 `original_argv0` 指向宿主而非我们交给 `argv[0]` 的脚本路径。

---

## 6. 加载方式

必须让 `python312.dll` 从 payload 目录解析。导入表 10 项：

```
python312.dll
KERNEL32.dll
VCRUNTIME140.dll
api-ms-win-crt-{runtime,convert,stdio,string,math,heap,locale}-l1-1-0.dll
```

payload 目录中同时存在 `python312.dll`(6,973,952 B) 与 `python3.dll`(56,320 B)，依赖齐备。目录顶层 52 项，递归 117 文件。

采用与 Nuitka 官方 `OnefileBootstrap.c` 同构的做法：

```c
AddDllDirectory(payload_path);
LoadLibraryExW(dll_filename, NULL,
    LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR |   // 0x100
    LOAD_LIBRARY_SEARCH_SYSTEM32     |   // 0x800
    LOAD_LIBRARY_SEARCH_USER_DIRS);      // 0x400
```

合计 `0xD00`。**`LOAD_WITH_ALTERED_SEARCH_PATH`(0x8) 不能与任何 `LOAD_LIBRARY_SEARCH_*` 组合**——这是 `boot.c` 用 `0x8` 的代价：它放弃了 `SYSTEM32` 的显式保证，而在已有 `python312.dll` 加载过的进程里，`0x8` 不足以强制依赖解析到 payload 目录。

`AddDllDirectory` 的前置条件：要么先 `SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_USER_DIRS)`，要么在 `LoadLibraryExW` 里显式带 `LOAD_LIBRARY_SEARCH_USER_DIRS`。选后者，副作用更局部。

---

## 7. 退出码

宿主把 `run_code` 的返回值原样作为自己的返回值。（决策 Q8）

---

## 8. 两个变体

`host.c` 提供开关 `--no-envp` 以传 `NULL` 作为第三参数，默认传 `main.dll` 的绝对路径。（决策 Q13：两种都试）

---

## 原始文件完整性

本次工作**不修改任何样本文件**。实测核对（2026-09-15）：

```
01560c951afd1ce35350ea86a58c1989  KeySteam.exe
2948792df5b1484a426580927abb0882  _re/bin/main.dll
2948792df5b1484a426580927abb0882  _re/work/payload/main.dll
```

与 `_re/backup/BASELINE.txt` 一致。

### 数据目录现状（`#5` 的起点）

```
%APPDATA%\Shikieiki\
  first_run.cache      63 B
  shiki.json          438 B
  shiki.kodo           36 B
  verification.cache  605 B   <-- 存在，可作磁盘差异比对的对照
  shiki/
```

`verification.cache` 当前存在，这是 `#5` 差分断言可直接使用的起点。其内容不可读（此前 2648 种机器标识构造均未解出），断言只能针对**是否被重写**。
