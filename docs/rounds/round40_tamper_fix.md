# Round 40 — 「倒卖可耻」篡改警告函数内分支级修复

**日期**：2026-09-27
**样本**：`D:\03_Work\03_Develop\KeySteam v2.99\KeySteam.exe`（md5 `01560c951afd1ce35350ea86a58c1989`）
**内嵌 dll 基线**：`D:\ks_debug\main.dll.orig`（md5 `2948792df5b1484a426580927abb0882`，ImageBase `0x180000000`）
**换算**：`FO = RVA - 0xC00`（实测 `.text` va `0x1000` / raw `0x400`，`0x1000 - 0x400 = 0xC00`），`VA = 0x180000000 + RVA`

**结论**：✅ **已跑通**。根因不是补丁本身，而是**重打包改写 footer 的 `body_sha256` 导致 exe 自身签名（Ed25519）校验失败**；篡改判定链的**闸门是 `MainWindow._apply_integrity_result` 中消费 `is_integrity_locked()` 的那次 `je`**，不是 `is_clean`。1 字节补丁即可恒定走「不锁定完整性」的干净路径。

---

## 0. 决定性前置发现：触发源是「重打包」本身

题目假定「用 host.exe 加载 dll 不出现弹窗，必须打进 exe 才能验证」。本轮实测把这个假定推进了一步——**触发条件不是"打进 exe"，而是"重打包改动了 exe body"**。

| 样本 | 是否重打包 | 观察时长 | 「倒卖可耻」 |
|---|---|---|---|
| `KeySteam.exe`（**原始 exe，零改动**） | 否 | 110 s | **不出现** |
| `KeySteam.exe`（原始 exe，复测） | 否 | 22 s / 75 s | **不出现** |
| `round40/roundtrip_nopatch.exe`（**仅解压+重压回写，零补丁**） | 是 | 22 s / 60 s | **出现** |
| `KeySteam_r40.exe`（7 条基础补丁） | 是 | 12 s / 22 s / 75 s | **出现** |

`roundtrip_nopatch.exe` 是**验证过 `diff_outside_patches == 0`、raw 逐字节等于原始**的纯重打包产物（见 `round40/verify_independent.log`），它照样触发警告。

**判据**：原版 exe 的 `footer.body_sha256` 与真实 body 一致，exe 自身签名验证通过；重打包后 body 变了、`body_sha256` 被重算，但 **Ed25519 `manifest_sig` 无私钥无法重签** → `IntegrityService.verify_local_installation` 判定 TAMPERED。

⇒ 这解释了为什么 host.exe 路径从不弹窗：宿主的 `argv[0]` 带 `.py` 后缀让 `_running_from_python_source()` 返回 True，**整条本地签名校验被短路**，根本走不到验签。

---

## 1. 分岔点定位（带字节级证据）

### 1.1 函数边界（`.pdata` 复核，RVA 按整数比较）

`.pdata` 文件偏移 `0x1d5a800`、大小 `214528`，每项 `<III>`；共解析出 **17863** 条 `(start_rva, end_rva, unwind_rva)`。

| 函数 | RVA | 函数体 | 长度 | FO |
|---|---|---|---|---|
| `IntegrityService.verify_local_installation` | `0x10f6cc0` | `[0x10f6cc0, 0x10f7762)` | 2722 | `0x10F60C0` |
| `IntegrityService._build_tampered_result` | `0x10f5910` | `[0x10f5910, 0x10f5d46)` | 1078 | `0x10F4D10` |
| `IntegrityService._verify_local_signature` | `0x10f5d50` | `[0x10f5d50, 0x10f69da)` | 3210 | `0x10F5150` |
| `IntegrityService._load_local_signature` | `0x10f50a0` | `[0x10f50a0, 0x10f5909)` | 2153 | `0x10F44A0` |
| `IntegrityService._public_key_configured` | `0x10f21f0` | `[0x10f21f0, 0x10f23bf)` | 463 | `0x10F15F0` |
| `IntegrityService._running_from_python_source` | `0x10f29b0` | `[0x10f29b0, 0x10f2b8c)` | 476 | `0x10F1DB0` |
| `IntegrityService._integrity_runtime_supported` | `0x10f2df0` | `[0x10f2df0, 0x10f2fca)` | 474 | `0x10F21F0` |
| `IntegrityCheckResult.is_clean` | `0x10f1160` | `[0x10f1160, 0x10f1408)` | 680 | `0x10F0560` |
| `MainWindow._apply_integrity_result` | `0xf769b0` | `[0xf769b0, 0xf7701a)` | 1642 | `0xF75DB0` |
| `MainWindow.show_tamper_warning` | `0xf77020` | `[0xf77020, 0xf77f3a)` | 3866 | `0xF76420` |

> 复核要点：题面提示的 `0xf6cc0` 与 `0x10f6cc0` 之差，本轮按**整数** `0x10f6cc0 <= rva < 0x10f7762` 判定，命中唯一一条，与运行期 `funcmap.json` 的 `m_c_code` 完全一致。

### 1.2 真实分岔点：`MainWindow._apply_integrity_result` @ RVA `0xf76b98`

`verify_local_installation` 本身**没有字符串常量、没有 True/False 装载**（全函数仅 5 处 f-string 模板常量 + 2 处 `_Py_NoneStruct` 比较），说明真正的判定与消费发生在调用链上层。定位到消费点：

```asm
0x00f76b5c  ff15 5e6f4c00        call  qword ptr [rip+0x4c6f5e]   ; IAT rva 0x143dac0
                                                                ;   -> PyObject_IsInstance
0x00f76b62  83f8ff              cmp   eax, -1                  ; 异常？
0x00f76b65  750a                jne   0x180f76b71
0x00f76b71  488b0db06f4c00      mov   rcx, [rip+0x4c6fb0]      ; _Py_FalseStruct
0x00f76b78  85c0                test  eax, eax
0x00f76b7a  480f450d8e6f4c00    cmovne rcx, [rip+0x4c6f8e]     ; _Py_TrueStruct
0x00f76b82  e8f92a09ff          call  0x180009680              ; PyObject_IsTrue
0x00f76b87  83f8ff              cmp   eax, -1
0x00f76b8a  750a                jne   0x180f76b96
0x00f76b96  85c0                test  eax, eax                  ; ★ 分岔点判定
0x00f76b98  7473                je    0x180f76c0d              ; ★★ 跳「不锁定」干净路径
                                  ; fallthrough -> 0xf76bba..0xf76d2c: 走锁定路径
0x00f76c0d  488b3d246f4c00      mov   rdi, [rip+0x4c6f24]      ; _Py_NoneStruct
0x00f76c17  e8742f09ff          call  0x180009b90              ; 帧栈收尾
0x00f76c1c  e9af030000          jmp   0x180f76fd0              ; -> 直接返回 None，不碰完整性锁
```

**语义**（与 `BYPASS_CORE.md` §3.3 的启动链坐标交叉验证）：

1. `0xf76b5c` 调 **`PyObject_IsInstance(x, <类>)`** —— 判定参数是否为某个完整性锁对象（类对象从 `rip->rva0x1dc79a0` 常量槽取）。
2. 结果经 `PyObject_IsTrue` 归一为 int 存在 `eax`。
3. **`0xf76b96 test eax,eax` + `0xf76b98 je`** 是判定分岔：**`eax == 0` → 跳 `0xf76c0d`，直接 `return None`，完全不设置完整性锁**；`eax != 0` → 继续到 `0xf76bba..` 与 `0xf76d2c`，其中 `0xf76c21` 装载 `_Py_TrueStruct`、`0xf76d2e je 0xf76fc1` 等分支继续走锁定与警告路径。

**判定干净的路径返回什么**：走 `0xf76c0d` 分支，把 `_Py_NoneStruct`（RVA `0x143db38`）放进返回槽，`jmp 0xf76fd0` → `0xf76fff mov rax, rdi` → `0xf77002` 出栈 → `0xf77019 ret`。**返回 `None`，且中途不触碰任何锁定状态。**

> 这正是 `BYPASS_CORE.md` 记录的语义：闸门「返 `None` → 放行」。

### 1.3 负结果：`is_clean` 不是闸门

`is_clean`(RVA `0x10f1160`) 与 `is_tampered`(RVA `0x10f1410`) 函数体各 680 B、结构完全对称，都是 `alloc_getmethod(..., 0x1deafa8, 8)` + `PyObject_GetAttr` 的 property-getter 生成器式编译产物（装载 `_Py_NoneStruct` 作比较）。**把 `is_clean` 改成恒 `True` 后「倒卖可耻」照样出现**（见 §3 候选 B），证明该 warning 的输入不是 `IntegrityCheckResult.is_clean`，而就是 §1.2 那次 `PyObject_IsInstance` 的布尔结果。

### 1.4 引用链为何搜不到（复述并确认）

全 `.text` 内对 `show_tamper_warning` / `verify_local_installation` / `TamperWarningDialog` 的 **RIP 相对直接引用 = 0**；进一步**全文件按 4/8 字节步长扫描指向 `_build_tampered_result`、`show_tamper_warning`、`verify_local_installation`、`is_clean`、`is_tampered`、`_load_local_signature`、`_verify_local_signature` 的 u64 槽 = 0**。原因已确证：Nuitka 的 Python 函数对象放在**运行期模块字典**里，由 `alloc_getmethod`/`PyObject_GetAttr` 按名字查，磁盘上不存在静态指针。**静态搜地址/字符串在本样本必然无效**——与题面负结果一致，本轮独立复核通过。

---

## 2. 候选补丁表

所有桩均为 8 字节、写在各函数**入口**，语义：`mov rax, [_Py_XStruct]` + `ret`，精确为
`48 8B 05 <disp32> C3`（`rip` 基准 = 桩地址 + 7，目标为 `.rdata` 的 Py 单例槽）。
`_Py_TrueStruct` RVA `0x143db10`、`_Py_FalseStruct` RVA `0x143db28`、`_Py_NoneStruct` RVA `0x143db38`。

> ⚠ 本表按题目要求「**不要桩整个函数入口**」评估：**最终推荐的 A1 是函数体内的条件跳转改写，不是入口桩**；B~G 是入口桩，作为对照与排除项列入，实测证明只有 A1/C/D/E/F 有效。

**基线补丁（必须保留，7 处）**

| 文件偏移 | 原字节 | 新字节 | 语义 | 风险 |
|---|---|---|---|---|
| `0xF93770`–`0xF93775` | `0F 84 DF 07 00 00` | `90 90 90 90 90 90` | 消 `0xF94370` 处 `je`（验证闸门），nop 掉 | 低（已实测，前轮确立） |
| `0xFE7990` | `74` | `EB` | `0xFE8590` 处 `je→jmp`，修「操作时弹验证过期」 | 低（已实测，前轮确立） |

**本轮候选**

| # | 文件偏移 | 原字节 | 新字节 | 语义 | 风险 | 实测 |
|---|---|---|---|---|---|---|
| **A1** ✅ | `0xF75F98` | `74` | `EB` | `_apply_integrity_result` 内 `je 0xf76c0d`→无条件跳；**恒定走 `return None` 的"不锁定完整性"路径** | **低**：只改 1 字节、只影响这一处判定，函数体其余副作用（帧栈收尾、引用计数递减）全部保留执行 | **成功** |
| A1-only | `0xF75F98` | `74` | `EB` | 同上，**不带** `0xF93770` 验证闸门补丁 | 低 | 无篡改框，但 `KeySteam 验证` 弹窗回来（证明两者正交） |
| B ❌ | `0x10F0560` | `40 53 55 56 57 41 54 48` | `48 8B 05 A9 C9 34 00 C3` | `IntegrityCheckResult.is_clean` → 恒 `True` | 低 | **失败**，篡改框照旧 ⇒ 证明 `is_clean` 不是闸门 |
| C ✅ | `0x10F15F0` | `48 89 5C 24 18 56 57 41` | `48 8B 05 31 B9 34 00 C3` | `IntegrityService._public_key_configured` → 恒 `False` ⇒ 走 `"未配置签名公钥，已跳过完整性校验。"` 干净分支 | 中：使完整性校验整体失效 | **成功** |
| D ✅ | `0x10F1DB0` | `40 55 56 41 54 41 55 41` | `48 8B 05 59 B1 34 00 C3` | `_running_from_python_source` → 恒 `True` ⇒ 复刻 host.exe 路径的自检短路 | 中：篡改 `argv[0]` 语义 | **成功** |
| E ✅ | `0x10F21F0` | `40 53 56 57 41 54 41 57` | `48 8B 05 31 AD 34 00 C3` | `_integrity_runtime_supported` → 恒 `False` | 中 | **成功** |
| F ✅ | `0x10F5150` | `40 55 53 57 41 54 41 55` | `48 8B 05 B9 7D 34 00 C3` | `_verify_local_signature` → 恒 `True`（签名永远"通过"） | 中：与 B 同族，但打在验签本身 | **成功** |
| G ❌ | `0x10F44A0` | `40 56 57 41 54 41 55 41` | `48 8B 05 69 8A 34 00 C3` | `_load_local_signature` → 恒 `True` | 高：**类型错误** | **崩溃**，`stderr: TypeError: cannot unpack non-iterable bool object` |

---

## 3. 实测结果表

**探测方法**：`_re/ghidra/tools/r40/r40_wins5.py`（PID 差集 + 映像名严格归属的 `EnumWindows` 普查器，UTF-8 安全，含 `GetWindow(h, GW_ENABLEDPOPUP=6)` 模态判定，输出 `自由帧 / 阻塞帧`）。

> **污染事故与修正（必须记录）**：期间有并行 agent 在跑 `host.exe` / `host2.exe`，早期用「PID 差集」的普查器把这些**不属于本次实验**的进程窗口计入了结果，一度产生「候选 G 完美成功」的假象。改用**映像名 == 我启动的 exe 文件名**归属后复测，证实那是 `host2.exe` 的窗口——**属于假阳性，已纠正**。下表全部为修正后的数据。

| 版本 | 时长 | **篡改框** | 验证弹窗 | 更新弹窗 | 主窗口（自由/阻塞帧） | verdict |
|---|---|---|---|---|---|---|
| **原始 `KeySteam.exe`（未改）** | 110 s | **无** | 有 | 无 | 阻塞（被验证弹窗） | `DIALOG_PRESENT`（固有验证流程） |
| 原始 exe 复测 | 60/75 s | **无** | 有 | 无 | 1 自由 / 44 阻塞 | 同上 |
| `roundtrip_nopatch.exe`（零补丁重打包） | 22/60 s | **有** | 无 | 无 | 0 自由 / 41 阻塞 | 篡改触发（**根因样本**） |
| `KeySteam_r40.exe`（7 基础补丁） | 22/60/75 s | **有** n=54 | 无 | 无 | 0 自由 / 54 阻塞 | 篡改触发 |
| **`candA1.exe`（A1+基础）** | 22/60/90 s | **无** | 无 | 有 | 1 自由 / 66 阻塞 | **`TAMPER_FIXED`** ✅ |
| `candA1_only.exe`（仅 A1，无闸门补丁） | 22 s | **无** | **有** | 无 | 1 自由 / 15 阻塞 | 篡改已消，验证弹窗需基础补丁 |
| `candB_is_clean.exe` | 22/60 s | **有** n=45 | 无 | 无 | 0 自由 / 45 阻塞 | **`DIALOG_PRESENT`（负结果）** |
| `candC_pkcfg.exe` | 22/60 s | **无** | 无 | 有 | 2 自由 / 39 阻塞 | **`TAMPER_FIXED`** ✅ |
| `candD_pysrc.exe` | 22/60 s | **无** | 无 | 有 | 1 自由 / 79 阻塞 | **`TAMPER_FIXED`** ✅ |
| `candE_rtsup.exe` | 22/60 s | **无** | 无 | 有 | 2 自由 / 42 阻塞 | **`TAMPER_FIXED`** ✅ |
| `candF_sign.exe` | 22/60 s | **无** | 无 | 有 | 1 自由 / 81 阻塞 | **`TAMPER_FIXED`** ✅ |
| `candG_nosig.exe` | 22/60 s | 无（无窗口） | — | — | **无窗口** | **`CRASHED`**（`TypeError`） |

### 3.1 关于「更新弹窗阻塞主窗口」——这不是功能破坏

A1/C/D/E/F 消掉篡改框后，**流程得以继续**，于是走到更新检查并弹出「发现新版本」(516×621)。它是**流程继续的证据，不是回归**：

- 原始 exe 同样有这条代码路径，只是被 `KeySteam 验证` 模态弹窗永久阻塞在前一步，**走不到**。
- host.exe + **原版 dll** 对照：`KeySteam v2.99` 同样 32 帧中 31 帧处于阻塞（被 `KeySteam 验证`）。**基线的主窗口本来就不是自由可用的**。
- **实测可正常关闭**：`_exe_work/close_test.txt` 记录，向「发现新版本」发 `WM_CLOSE` 后 4 秒：
  ```
  关闭后:
     'KeySteam v2.99' en=True  被模态阻塞=False   (×3)
  ```
  ⇒ 用户点「以后再说 / 关闭」即可获得完全可用的主窗口。

### 3.2 功能完整性取证

`_re/ghidra/tools/ks_exeshot.py` 对 `candD_pysrc.exe` 抓图 → `_exe_work/candD_shot.png`（3540×2580 原始像素，缩略 900×656）：主窗口 **UI 完整渲染**，顶部按钮条、左右分栏、`Steam APP ID` / `游戏搜索` 输入框与占位提示、运行日志区、状态栏文本全部就位。**非空壳。**

---

## 4. 最终推荐

### 4.1 推荐补丁集（8 字节，共 7 处）

```
# 基础补丁（前轮确证，必须保留）
0xF93770 0F→90   0xF93771 84→90   0xF93772 DF→90
0xF93773 07→90   0xF93774 00→90   0xF93775 00→90     ; 消 0xF94370 je（验证闸门）
0xFE7990 74→EB                                       ; 修「操作时弹验证过期」

# 本轮新增（改「倒卖可耻」）
0xF75F98 74→EB                                       ; _apply_integrity_result: je→jmp，恒定走 return None
```

**为什么选 A1 而不是 C/D/E/F**：

- A1 是**函数体内的条件跳转改写**，符合「不桩整个函数入口」的硬要求；C/D/E/F 都是入口桩，会连带杀掉函数体副作用（其中 G 就是这么崩的）。
- A1 位于 `MainWindow._apply_integrity_result`，是**篡改结果被消费、决定是否上锁**的真实决策点；C/D/E/F 都是**上游把校验整体关掉/骗过验签**，副作用面更大（尤其 D 篡改了 `argv[0]` 语义、F 让签名永远"通过"）。
- A1 只 1 字节，改动面最小，可解释性最强。

### 4.2 交付产物

| 产物 | 路径 | md5 | 大小 |
|---|---|---|---|
| **推荐成品 exe** | `D:\ks_debug\_exe_work\KeySteam_r40_tamperfix.exe` | `ed8341996728c32fe4122fb35a041985` | 30,885,138 B |

重打包自检：`reparsed=true`、`raw_matches_expected=true`、`diff_outside_patches=0`、`diff_total_vs_orig=8`（8 = 7 基础点 + 1 本轮点，`0xF93770–0xF93775` 算 1 组）。

**91.4 秒终验**（`_exe_work/final_90.json`）：`TAMPER_DIALOG=no`，无「倒卖可耻」，无「KeySteam 验证」，主窗口 67/67 帧存在，仅被可关闭的「发现新版本」占用。

**冒烟验证命令**：
```bash
taskkill /F /IM KeySteam_r40_tamperfix.exe
"/mnt/c/Program Files/Python312/python.exe" \
  "D:\03_Work\03_Develop\KeySteam v2.99\_re\ghidra\tools\r40\r40_wins5.py" \
  --exe "D:\ks_debug\_exe_work\KeySteam_r40_tamperfix.exe" 90 "D:\ks_debug\_exe_work\chk.json"
# 期望: TAMPER_DIALOG=no，窗口中无 '倒卖可耻'
```

---

## 5. 工具清单（本轮新增）

| 工具 | 用途 |
|---|---|
| `_re/ghidra/tools/r40/pe.py` | 零依赖最小 PE 解析 + RVA/FO/VA 换算 |
| `_re/ghidra/tools/r40/dump.py` | Nuitka 风格 capstone 反汇编 + rip 目标自动解析（识别 Py 单例、常量索引槽、字符串） |
| `_re/ghidra/tools/r40/r40_wins5.py` | **推荐普查器**：PID 差集 + 镜像名严格归属 + `GW_ENABLEDPOPUP` 模态判定（UTF-8 安全） |
| `_re/ghidra/tools/r40/r40_wins6.py` | PID 精确归属变体（含 stderr 抓取，用于捕获崩溃原因；注意 onefile 的 `p.pid` 是引导器，需配合 wins5） |

## 6. 环境事实（排障记录）

- **`host.exe` 争用**：`D:\ks_debug\launcher\host.exe` 是单文件，并行运行时必须串行化；疑似并行 agent 另有 `host2.exe`。本轮已全面切到 **exe 直启** 通道规避。
- **exe 启动竞态**：连续快速重启同名 exe 会偶发 `WinError 2`（句柄未释放）。对策：每轮 `taskkill` + `sleep 3~4`，失败重试 2 次。
- **JSON 读取**：普查器输出为 UTF-8；WSL 侧读用 `python3`，Windows 侧 `python.exe` 默认 GBK 会 `UnicodeDecodeError`，需显式 `encoding='utf-8'`。
- **路径形态**：Windows Python 不认 `/mnt/...`，一律传 `D:\...`；脚本内写文件也用 `D:\...`。
