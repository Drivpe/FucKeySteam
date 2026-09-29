# 「用户菜单尚未初始化」告警归因 —— 判定报告

**结论（一句话）**：**程序固有行为，补丁无责。** 该提示由「重启 Steam 到登录窗口」按钮的**用户点击**路径抛出，前置条件是 Steam 侧尚无真实登录用户菜单。它与 `_check_cached_verification` 验证绕过补丁在**不同函数、相距 0x1951b 字节**，字节层面从未被触碰。

**判定**：`程序固有行为` —— 不需要额外补丁。

---

## 1. 告警的真实来源（静态 + 运行期双证）

### 1.1 常量池归属（静态，磁盘实测）

`main.dll.orig` 的 `src.gui.main_window` 常量池 blob 中，三行**物理相邻**：

| 文件偏移 | 内容 | tag |
|---|---|---|
| `0x1cab367` | `MainWindow._on_restart_button_clicked.<locals>._action` | `u` 字符串 |
| `0x1cab39f` | `打开登录用户菜单失败` | `u` 字符串 |
| `0x1cab3bf` | `用户菜单尚未初始化` | `T\x01u` 类型包装 |
| `0x1cab3de` | `handle_restart_steam_to_login_window` | `a` 标识符 |
| `0x1cab404` | `handle_tanushiki_launch_for_user` | `a` |
| `0x1cab426` | `handle_tanushiki_launch` | `a` |

另一条同类文案 `TanuShiki 用户菜单尚未初始化`（`0x1cab4de`）紧邻 `MainWindow._on_tanushiki_launch_clicked.<locals>._action`（`0x1cab474`）。

**含义**：池内物理邻接即编译期常量发射顺序，两处告警分别属于 `_on_restart_button_clicked` 与 `_on_tanushiki_launch_clicked` 两个**按钮点击处理器**。

### 1.2 槽序号闭环（运行期，指针反查实证）

建立 `mod_consts`（`0x181dc7420`，BSS，运行期 = `base+0x1dc7420`）槽数组后，用**独立手段**验证编号公式：

对 `用户菜单尚未初始化` 的 Unicode 对象反查全部 8 字节指针，命中 `0x7ffc23708fe0`，而 `mc + 8*888` 逐位吻合；该地址所属槽的文本恰为**同池前一条** `打开登录用户菜单失败`。

⇒ 编号公式与归属**自洽且经独立命中验证**：

| 槽# | 内容 |
|---|---|
| `#886` | `handle_select_favorite_collection` |
| `#887` | `MainWindow._on_restart_button_clicked.<locals>._action` |
| `#888` | `打开登录用户菜单失败` |
| `#889` | `用户菜单尚未初始化`（T 包装） |
| `#890` | `handle_restart_steam_to_login_window` |
| `#891` | `handle_tanushiki_launch_for_user` |
| `#895` | `MainWindow._on_tanushiki_launch_clicked.<locals>._action` |

### 1.3 引用者定位（决定性）

全 `.text` 线性扫描 `mov reg,[rip+disp]` 落入槽区间的指令：

```
slot#888  ← MainWindow._on_restart_button_clicked.<locals>._action  @0x180fad14a
slot#889  ← MainWindow._on_restart_button_clicked.<locals>._action  @0x180fad623
slot#890  ← MainWindow._restart_steam_to_login_window               @0x180fadca1
```

`#889`（即 `用户菜单尚未初始化`）的**唯一引用点**是 `0x180fad623`：

```asm
0x180fad616  mov ebx, 0x9c1               ; 异常码 2497
0x180fad61e  mov dword ptr [r12+0x28], ebx
0x180fad623  mov r8,  [rip+0xe1b9be]      ; ★ 槽#889 = '用户菜单尚未初始化'
0x180fad62a  call 0x1814164f0             ; 构造异常 / 提示对象
```

### 1.4 触发条件（反汇编实证）

同一闭包内的前置条件检查：

```asm
0x180fad3ed  mov rdx, [r13+0xe0]      ; self.<属性>
0x180fad3f4  mov r8,  [rdx+0x10]      ; ★ 用户菜单对象槽
0x180fad3f8  test r8, r8
0x180fad3fb  jne  0x180fad463         ; 非空 → 正常路径（发 handle_restart_steam_to_login_window）
              ; 为空 → 落到 0x180fad623 抛「用户菜单尚未初始化」
```

**触发条件**：`self.<属性>[0xe0]` 的 `+0x10` 槽（Steam 用户菜单对象）为 **NULL**，即 **Steam 侧从未有过真实登录会话**。

### 1.5 功能链归属

```
用户点击「重启到登录窗口」按钮
  → MainWindow._on_restart_button_clicked          rva 0xfad040
  → <locals>._action 闭包                          0x180fad13a / 主体 0x180fad350
      ├─ [r13+0xe0][+0x10] == NULL → 抛「用户菜单尚未初始化」  ← 本告警
      └─ 非空 → 发 handle_restart_steam_to_login_window
               → MainWindow._restart_steam_to_login_window  rva 0xfadb00
               → Controller.handle_restart_steam_to_login_window rva 0x103c4c0
```

**属 `restart_to_login_window` 链，非 `TanuShiki`、非自动启动流程。入口是用户点击。**

---

## 2. 原版对照（决定性证据）

用**未打补丁的原版 exe**（`D:\03_Work\03_Develop\KeySteam v2.99\KeySteam.exe`，md5 `01560c951afd1ce35350ea86a58c1989`，只读、未修改）跑 45 秒全时程窗口枚举：

| 版本 | md5 | 可见窗口 | 含「验证」 | 含「用户菜单」 | 主窗口 enabled |
|---|---|---|---|---|---|
| **原版** | `01560c95` | `KeySteam 验证` ×58 + `KeySteam v2.99` ×58 | **1** | **0** | `False` |
| **补丁版** | `d0490ca1` | **仅** `KeySteam v2.99` ×38 | **0** | **0** | `True` |

**读法**：原版主窗口被模态验证弹窗**永久阻塞**（`en=False`），用户**根本点不到那个按钮**，因此原版永远看不到该菜单告警。补丁版主窗口可用（`en=True`），按钮变为可点，该前置条件提示才随之**可被触发**。

⇒ 原版「不出现该告警」的原因是**路径不可达**，而非「原版没有此逻辑」。这正是补丁的**暴露效应**（exposure effect），不是缺陷注入。

---

## 3. 用户菜单初始化链是否被补丁破坏

**未被破坏。** 四条独立证据：

**a. 字节层面零接触。** 三种 main.dll 副本字节比对：

| 副本 | md5 | 补丁位点 `0xF93500` | 告警文案 `0x1cab3c2` | 告警抛点对应字节 |
|---|---|---|---|---|
| `main.dll.orig`（基线） | `2948792d` | `4055535657415441` | **原样** | `488bd0` 原始 |
| 补丁 dll（launcher/instant/harness） | `afff50ee` | `488b05319a4a00c3` | **原样** | `488bd0` **原始** |
| 原版 exe | `01560c95` | — | 原样 | — |
| 补丁 exe | `d0490ca1` | — | 原样 | — |

补丁只改 `0xF93500` 起 8 字节；`0x1cab3c2` 文案与告警抛点 `0x180fad623` 所在闭包**逐字节未变**。

**b. 空间隔离。** 补丁位点 `VA 0x180F94108`（补丁尾）到告警抛点 `VA 0x180fad623` 距离 **`0x1951B`** 字节（103,707 B），属两个无调用关系的函数。

**c. `_continue_initialization` 未被切断。** 槽 `#515`=`verification_cache_accepted`、`#516`=`_continue_initialization` 的引用者实测为：

```
#515 ← MainWindow._check_cached_verification   @0x180f94609  (函数体内 emit 点)
#516 ← MainWindow._handle_verification_config_ready  @0x180f96703
     ← MainWindow._handle_verification_config_failed @0x180f96b29
```

补丁桩掉的是 `_check_cached_verification` **入口**，其函数体内的 emit 点不执行 —— 但 `_continue_initialization` 的**另一条合流**（`_handle_verification_config_ready/failed`，RVA `0xf963c0`/`0xf968c0`，均独立于补丁）完好。

**d. 运行期行为反证。** 补丁版主窗口 UI 完整（`BYPASS_CORE.md` §2.4 已实证：标题栏、`Steam APP ID` 输入框、`游戏搜索`、进度条、运行日志区齐全），且本次 60 秒采样全程 `en=True`、无崩溃 —— 主窗口初始化链（`start_initialization`）**确实跑通**。

**为什么用户菜单仍为空**：`_apply_users_menu`（rva `0xfc7ea0`）由 `users_menu_update` 信号驱动，发射者是 `MainWindowController._emit_users_menu`（rva `0xfed000`），其数据源是 **Steam 侧真实登录后的用户列表**。补丁解决的是「本机验证弹窗」，**不提供 Steam 账号登录**。所以菜单为空是**缺少真实登录**，与补丁正交。

---

## 4. 建议

**不需要额外补丁。** 该提示是产品设计的前置条件告知：想用「重启到登录窗口 / TanuShiki 用户菜单」功能，需先真实登录一次 Steam。

若用户坚持要屏蔽该提示，候选点如下（**仅记录，不推荐采用** —— 会掩盖真实前置条件、阉割功能语义）：

```
候选：0x180fad623
文件偏移 = 0x180fad623 - 0x180000000 - 0x1000 + 0x400 = 0xFACA23
原字节 = 48 8B 05 BE B9 E1 00     (mov r8, [rip+0xe1b9be])   ← 已从 main.dll.orig 回读校验
```

**不建议**改成桩：会把「前置条件未满足」静默降级为「无条件继续」，导致后续 `[r13+0xe0][+0x10]` 空指针解引用，风险高于告警本身。

---

## 5. 附带纠正（Lead 交接表的槽序号偏差）

Lead 表中两处槽坐标与本轮**运行期实测不符**，实测值如下（公式经指针命中独立验证）：

| 项 | Lead 表 | 本轮实测 |
|---|---|---|
| `_apply_users_menu` 槽 | 条目 #501，VA `0x181dc83c8` | **槽 #482**，VA `0x181dc8330` |
| `handle_restart_steam_to_login_window` 槽 | 条目 #928，VA `0x181dc9120` | **槽 #890**，VA `0x181dc8fd0` |
| `handle_restart_steam_to_login_window` RVA | `0x103c4c0`（表头）但正文给了 `0xfadb00` | RVA **`0x103c4c0`**（`0xfadb00` 实为 `MainWindow._restart_steam_to_login_window`） |

实测锚点（**与 Lead 的表交叉吻合**，证明编号公式正确）：`#515`=`verification_cache_accepted`、`#516`=`_continue_initialization`。差异源于 Lead 表混用了 `main_window` 与 `main_window_controller` 两个不同模块池的基址。

---

## 6. 复现步骤

```bash
# 原版对照（只读，不修改原始 exe）
python.exe D:\ks_debug\menuwork\run_exe_probe.py \
  "D:\03_Work\03_Develop\KeySteam v2.99\KeySteam.exe" 45 ORIG
# → 含「用户菜单」窗口数: 0；主窗口 en=False（被验证弹窗阻塞）

# 补丁版对照
python.exe D:\ks_debug\menuwork\run_exe_probe.py \
  "D:\ks_debug\KeySteam_patched.exe" 60 PATCHED2
# → 仅主窗口 en=True；含「用户菜单」0；含「验证」0

# 槽序号与文案归属（运行期）
python.exe D:\ks_debug\menuwork\menu_rng.py 880 900 D:\ks_debug\menuwork\slots_880_900.json
python.exe D:\ks_debug\menuwork\menu_link.py     # 指针反查 → slot#888 命中
```

## 7. 卡点与残留不确定性

- **未能实测「点击按钮」本身**：需要在补丁版 GUI 上模拟点击「重启到登录窗口」按钮才能观察到提示弹出。窗口枚举只能看到顶层窗口，无法捕获该提示的渲染（它可能是 Qt `QMessageBox`/toast，在本次 60 秒无交互采样中未出现）。**归因结论建立在静态反汇编的入口唯一性上**（槽 `#889` 全 `.text` 只有一个引用点 `0x180fad623`，位于按钮点击闭包内），该证据强度足以支撑结论，但缺少端到端点击复现。
- **原版无法提供「同一操作路径」对照**：原版主窗口被模态弹窗阻塞，按钮不可达，故只能证明「路径不可达」，不能证明「原版点击后行为一致」。这是对照的设计局限，非证据缺陷。
- 交互点击复现需要 GUI 自动化（`pyautogui` 或 Qt 事件注入），超出本轮 20 分钟时间盒。
