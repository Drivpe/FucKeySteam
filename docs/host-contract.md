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
int run_code(int argc, wchar_t **argv, wchar_t **envp);
```

**证据一——`main.dll` 入口反汇编**（RVA `0x143b380`，ImageBase `0x180000000`）：

```
0x180143b380: sub  rsp,0x28
0x180143b384: mov  eax,ecx        ; arg1 -> argc 使用
0x180143b386: test r8,r8          ; arg3 判空
0x180143b389: je   +8
0x180143b38e: call 0x18014135e0   ; 处理 arg3 = envp
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
0xc006: lea  r8,[0x141d5d720]    ; arg3 = envp
0xc00d: mov  rdx,r13             ; arg2 = argv
0xc010: mov  ecx,r12d            ; arg1 = argc
0xc013: call rax                 ; run_code(argc, argv, envp)
```

三寄存器齐填后才 `call`。参数**必须是宽字符** `wchar_t**`（UTF-16LE），不是 `char**`。

### 为什么不照 `boot.c` 写

外部参照实现 `nuitka-dll-bootloader/boot.c` 用的是**两参数**形式：

```c
typedef const wchar_t filename_char_t;
typedef wchar_t native_command_line_argument_t;
typedef int(__stdcall *nuitka_dll_function_ptr)(int, native_command_line_argument_t **);
```

它只填 `rcx`/`rdx`，`r8` 未设。在 x64 调用约定下 `r8` 读到调用者栈上的残留值，而入口的 `test r8,r8; je +8` 在 `r8==0` 时恰好跳过 envp 处理——**这是踩了运气，不是正确调用**。

后果：`boot.c` 路线会静默丢掉 `envp` 注入。而实测字符串证据显示 `NUITKA_ONEFILE_DIRECTORY` / `NUITKA_ONEFILE_TEMP` 正是经此途径传递（见下节）。丢掉它们的行为未经检验。

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

## 5. `envp` 的内容

第三个参数**不可省略**。

需要包含的变量（外层 `KeySteam.exe` 用 `SetEnvironmentVariableW` 写入，两字符串在文件中相邻）：

| 变量 | 文件偏移 | 值 |
|---|---|---|
| `NUITKA_ONEFILE_DIRECTORY` | `0x1d54d10` | payload 目录全限定路径 |
| `NUITKA_ORIGINAL_ARGV0` | `0x1d54d30` | 原始 `argv[0]` |

构造方式：取当前进程环境块（`GetEnvironmentStringsW`），转为 `wchar_t**` 数组后追加/覆盖上述两项，末尾补 NULL。

**待查证**（子代理进行中）：`envp` 究竟是 `NAME=VALUE\0` 扁平块还是 `wchar_t**` 指针数组。反汇编显示外层把同一个缓冲 `0x141d5d720` 既用于 `lpFileName` 又作为第三参数传出，这一细节需要澄清。**在此之前不要假定格式**——`host.c` 应把该构造隔离在单独函数里，便于两种格式切换。

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

`host.c` 提供开关（如 `--no-envp`）以传 `NULL` 作为第三参数，默认走完整 `envp`。（决策 Q13：两种都试）

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
