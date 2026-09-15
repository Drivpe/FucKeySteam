# 消除 / 抑制 KeySteam v2.99 启动验证弹窗：技术可行性判定（一手来源）

**日期**：2026-09-16
**性质**：只读研究。未修改样本、未修改系统状态。
**证据底座**：`docs/suppressing-the-dialog-evidence.md`（节转储重建、公钥解析、零命中排除清单、CLI 归属、窗口判据基线、票据与网络事实）。
本文引用的所有 `0x8…` 坐标均为 `rdata.bin`（`main.dll` 的 `.rdata`，9,504,256 B，节内偏移 → VA 加 `0x143d000`）的**节内偏移**。
第三方源码一律取官方仓库原始文件（`qt/qtbase`、`Nuitka/Nuitka`、`MicrosoftDocs/sdk-api`），不引用二手分析。

---

## 结论摘要

**真实可行**：只有一条 —— **维持有效票据**（每日提交一次验证码），它依赖服务端签发，不是「技术绕过」。

**不可行（已确证）**：进程外窗口层抑制（`EnableWindow`、`WH_CBT`、`SetWinEventHook`、`SetWindowsHookEx` 注入）—— Qt 在 Windows 上**从不调用** `EnableWindow`，模态阻断在进程内 Qt 事件循环，进程外 API 够不着；纯 MITM 伪造 `/validate` 响应 —— 票据带 Ed25519 签名而样本无私钥；Nuitka 官方机制无任何「跳过模块初始化」或「指定入口」开关。

**未确证**：`run_authorization_extract_cli` 内部是否调用票据校验（常量簇距离不足以证明无调用）；`SSL_CERT_FILE` 等 CA 环境变量是否被**样本自身**读取（样本侧零命中，但库侧存在读取路径）。

**把「消除」与「抑制」分开**：

- **消除**（让它不出现）：只有「票据有效」这一条路。篡改启动链属于改样本，不属本研究范围（ADR 0001 零字节改动）。
- **抑制**（它出现但主窗口可用）：**技术上不可行**。弹窗期间存在两层独立机制 —— Qt 应用模态阻断（第 1 层）与样本自身的控件软禁用（第 2 层）。第 1 层在进程内，进程外无法触及；即使单独解除第 2 层，用户也只会看到「按钮亮了但点不动」。

---

## 一、Qt 应用模态的抑制：不可行

### 1.1 机制：模态阻断发生在 Qt 进程内的事件分发层

`QDialog` 默认是应用模态，这一点在 Qt 官方文档中有明确表述（[QDialog Class | Qt 6](https://doc.qt.io/qt-6/qdialog.html)：*"If the dialog is application modal, users cannot interact with any other window in the same application until they close the dialog. … By default, the dialog is application modal."*）。

阻断的具体实现分两级，全部在 `qtbase` 内：

**判定级** —— `src/gui/kernel/qguiapplication.cpp`（[原文](https://raw.githubusercontent.com/qt/qtbase/dev/src/gui/kernel/qguiapplication.cpp)）的 `QGuiApplicationPrivate::isWindowBlocked`，约 962–1006 行：

```cpp
bool QGuiApplicationPrivate::isWindowBlocked(QWindow *window, QWindow **blockingWindow) const
{
    if (modalWindowList.isEmpty() || windowNeverBlocked(window))
        return false;
    for (int i = 0; i < modalWindowList.size(); ++i) {
        QWindow *modalWindow = modalWindowList.at(i);
        if (window == modalWindow || modalWindow->isAncestorOf(window, QWindow::IncludeTransients))
            return false;
        switch (modalWindow->modality() == Qt::NonModal ? defaultModality()
                                                        : modalWindow->modality()) {
        case Qt::ApplicationModal:
            *blockingWindow = modalWindow;
            return true;
        ...
```

状态的存储与传播同在 `qguiapplication.cpp`：`showModalWindow()` 把弹窗 `prepend` 进 `QGuiApplicationPrivate::modalWindowList`（910–934 行），`updateBlockedStatusRecursion()` 设置 `QWindowPrivate::blockedByModalWindow` 并向窗口投递 `QEvent::WindowBlocked`（879–891 行）。

**阻断级** —— 鼠标（`qguiapplication.cpp` `processMouseEvent`，约 2498 行）：

```cpp
if (window->d_func()->blockedByModalWindow && !activePopup) {
    // a modal window is blocking this window, don't allow mouse events through
    return;
}
```

键盘与焦点同理，`QApplication` 侧的对称逻辑在 `src/widgets/kernel/qapplication.cpp`（[原文](https://raw.githubusercontent.com/qt/qtbase/dev/src/widgets/kernel/qapplication.cpp)）：

```cpp
bool QApplicationPrivate::isBlockedByModal(QWidget *widget)      // ~2193
{
    widget = widget->window();
    QWindow *window = widget->windowHandle();
    return window && self->isWindowBlocked(window);
}

bool QApplicationPrivate::tryModalHelper(QWidget *widget, QWidget **rettop)   // ~2217
{
    QWidget *top = QApplication::activeModalWidget();
    if (rettop) *rettop = top;
    if (QApplication::activePopupWidget())
        return true;
    return !isBlockedByModal(widget->window());
}

bool qt_try_modal(QWidget *widget, QEvent::Type type)             // ~2230
{
    ...
    case QEvent::MouseButtonPress: case QEvent::MouseButtonRelease:
    case QEvent::MouseMove: case QEvent::KeyPress: case QEvent::KeyRelease:
        block_event = true; break;
```

结论：**阻断点在 `QApplication::notify` / 平台事件处理函数进入 Qt 分发时**，即 Qt 事件循环内部。它不经过 `DefWindowProc`，不依赖窗口的 `WS_DISABLED` 状态。

### 1.2 决定性证据：Qt 在 Windows 上不调用 `EnableWindow`

`qtbase` 的 Windows 平台层确实实现了「模态窗口阻塞其它窗口」的**状态同步**，但其落地动作是 `setStyle()` 而非 `EnableWindow`：

`src/plugins/platforms/windows/qwindowswindow.cpp`（[原文](https://raw.githubusercontent.com/qt/qtbase/dev/src/plugins/platforms/windows/qwindowswindow.cpp)）：

```cpp
bool QWindowsWindow::windowEvent(QEvent *event)
{
    switch (event->type()) {
    case QEvent::WindowBlocked: // Blocked by another modal window.
        setEnabled(false);
        setFlag(BlockedByModal);
        if (hasMouseCapture())
            ReleaseCapture();
        break;
    case QEvent::WindowUnblocked:
        setEnabled(true);
        clearFlag(BlockedByModal);
        break;
    ...
}

void QWindowsWindow::setEnabled(bool enabled)      // ~3837
{
    const unsigned oldStyle = style();
    unsigned newStyle = oldStyle;
    if (enabled) newStyle &= ~WS_DISABLED;
    else         newStyle |= WS_DISABLED;
    if (newStyle != oldStyle) setStyle(newStyle);
}
```

**这里用的是 `setStyle()`（写 `WS_DISABLED`），不是 Win32 `EnableWindow()`。** 二者效果在 Win32 层近似，但对进程外干预的抵抗力完全不同 —— 详见 1.3。

**导入表实证**（最强证据：证明该 API 根本未被调用，而非「读源码没读到」）。对整个 payload 目录 93 个可执行文件（含 `qt6core.dll` / `qt6gui.dll` / `qt6widgets.dll` / `qt6network.dll` / `qt6svg.dll` 及全部 `.pyd`、`curl_cffi.libs/*.dll`）做二进制字符串扫描：

```bash
cd "/mnt/d/03_Work/03_Develop/KeySteam v2.99/_re/work/payload"
python3 - <<'PY'
import glob
pats=['EnableWindow','IsWindowEnabled','SetWindowLongPtrW','SetWindowLongW','SendMessageW',
      'PostMessageW','SetFocus','SetActiveWindow','SetForegroundWindow','SetWindowsHookExW']
found={p:[] for p in pats}
files=sorted(glob.glob('*.dll'))+sorted(glob.glob('*.pyd'))+sorted(glob.glob('curl_cffi.libs/*.dll'))
print("扫描文件数:",len(files))
for f in files:
    d=open(f,'rb').read()
    for p in pats:
        if p.encode() in d: found[p].append(f)
for p,v in found.items():
    print(f"{p:22s} 命中 {len(v)}: {v[:6]}")
PY
```

实测输出：

```
扫描文件数: 93
EnableWindow           命中 0: []
IsWindowEnabled        命中 0: []
SetWindowLongPtrW      命中 1: ['qt6core.dll']
SetWindowLongW         命中 0: []
SendMessageW           命中 0: []
PostMessageW           命中 1: ['qt6core.dll']
SetFocus               命中 2: ['qt6gui.dll', 'qt6widgets.dll']
SetActiveWindow        命中 0: []
SetForegroundWindow    命中 0: []
SetWindowsHookExW      命中 0: []
```

`qt6widgets.dll` 对 `USER32.dll` 的导入表**总共 7 个可辨认函数，全部是查询类**：`GetDesktopWindow`、`GetSystemMetrics`、`GetSystemMetricsForDpi`、`GetSystemMenu`、`SystemParametersInfoW`、`SystemParametersInfoForDpi`、`GetSysColor`。

**勘误（主会话复核 2026-09-16）**：本节曾写「`qt6core.dll` 与 `qt6gui.dll` 对 `USER32.dll` 的导入为 **0 个**」，**该句不成立**。
按节区定位的实测（下方命令）显示，持有窗口状态修改 API 的正是 **`qt6core.dll`**：

| 文件 | `.rdata` 中命中的 USER32 函数 |
| --- | --- |
| `qt6core.dll` | **`SetWindowLongPtrW`**、`GetWindowLongPtrW`、`PostMessageW`、`PeekMessageW`、`DispatchMessageW`、`ShowWindow` |
| `qt6gui.dll` | `SetFocus` |
| `qt6widgets.dll` | `SetFocus` |
| `main.dll` / `python312.dll` | `ShowWindow` |
| **全部文件** | **`EnableWindow` 零命中、`IsWindowEnabled` 零命中** |

```bash
python3 - <<'PY'
import glob, os, struct
base='/mnt/d/03_Work/03_Develop/KeySteam v2.99/_re/work/payload/'
names=[b'EnableWindow',b'IsWindowEnabled',b'SetWindowLongPtrW',b'GetWindowLongPtrW',
       b'SetWindowLongW',b'PostMessageW',b'SendMessageW',b'SetWindowsHookExW',
       b'SetFocus',b'SetForegroundWindow',b'SetActiveWindow',b'GetMessageW',
       b'PeekMessageW',b'DispatchMessageW',b'SetWindowPos',b'ShowWindow']
def secmap(p):
    d=open(p,'rb').read()
    e=struct.unpack_from('<I',d,0x3c)[0]
    if d[e:e+4]!=b'PE\0\0': return None,None
    nsec=struct.unpack_from('<H',d,e+6)[0]
    opt=e+24; sizeopt=struct.unpack_from('<H',d,e+20)[0]; secs=opt+sizeopt
    si=[]
    for i in range(nsec):
        o=secs+i*40
        nm=d[o:o+8].rstrip(b'\0').decode('latin1')
        vsize,vaddr,rawsize,rawptr=struct.unpack_from('<IIII',d,o+8)
        si.append((nm,vaddr,vsize,rawptr,rawsize))
    return d,si
def where(si,off):
    for nm,vaddr,vsize,rawptr,rawsize in si:
        if rawptr<=off<rawptr+max(rawsize,1): return nm
    return '?'
for f in sorted(glob.glob(base+'*.dll'))+sorted(glob.glob(base+'*.pyd')):
    d,si=secmap(f)
    if d is None: continue
    out=[f'{n.decode()}[{where(si,i)}]' for n in names if (i:=d.find(n))>=0]
    if out: print(f"{os.path.basename(f):16s} {', '.join(out)}")
PY
```

**这处更正使 §1.3 的论证必须改换依据** —— 原句以「`qt6core` 不导入 USER32」为前提，前提既不成立，论证作废。
正确的依据见修订后的 §1.3。

**`EnableWindow` 与 `IsWindowEnabled` 在整个 payload 中零命中。** 动态解析的可能性同时关闭：若走 `GetProcAddress` 按名解析，函数名必须以字符串形式存在于二进制中；连字符串都没有，说明该 API 不被调用（[GetProcAddress 语义](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-getprocaddress)：按 `lpProcName` 的 ANSI 名称查找导出）。**这一条不受上述勘误影响，仍是本节最强的证据。**

### 1.3 由此得出的判定

**先明确哪些是确证、哪些是推断**（依据修正后，不能再用「`qt6core` 不导入 USER32」当理由）：

**确证的事实**：

1. `EnableWindow` / `IsWindowEnabled` 在整个 payload 中**零命中**（含静态导入名与动态解析名）——见 §1.2。
2. `qt6core.dll` **确实**导入 `SetWindowLongPtrW` / `GetWindowLongPtrW`，即 Qt 用 `SetWindowLongPtr(GWL_STYLE)` 写 `WS_DISABLED`，与 §1.2 引用的官方源码一致。
3. `qt6core.dll` 也导入 `PeekMessageW` / `DispatchMessageW` ——**消息泵在 Qt 自己手里**。

**判定**：

**进程外无法解除第 1 层（模态阻断）。** 依据是第 3 条而非第 1 条：

- 第 2 条说明 `WS_DISABLED` 位**可以**被进程外用 `SetWindowLongPtrW` 清掉。**所以「投影不可改」这个说法是错的**——投影可改。
- 但清掉 `WS_DISABLED` **不等于**解除阻断。Qt 的模态判定读的是 `QGuiApplicationPrivate::modalWindowList` 与 `QWindowPrivate::blockedByModalWindow`，二者是 **Qt 进程内私有状态**，与窗口样式位无关。
- 第 3 条是关键：消息由 Qt 自己的 `DispatchMessageW` 泵出后进入 Qt 事件分发，模态判定在该层执行。**进程外送 `WM_*` 消息也会走同一条路**，同样被判定挡住。

**因此准确表述是**：

> 进程外**可以**改掉窗口的 `enabled` 状态（投影），但**不能**让输入抵达目标控件。
> 结果不是「按钮点不动」，而是**「按钮看起来能点，点了没反应」**——这比原判定的描述更精确。

**附带的实测支持**：文本类输入走 `WM_CHAR` 而非 `WM_KEYDOWN`，且 Qt 的 `QGuiApplicationPrivate::processKeyEvent` 有前置的 `if (window && QWindowPrivate::get(window)->blockedByModalWindow) return;`。故「跨进程 `PostMessage` 合成点击/按键能否绕过」这一支**仍需实际运行验证**（本研究为只读），已在 §6 标注为未确证。**不要把上面第 3 条读成对该支的否证。**

**仍然成立的部分**：`EnableWindow` 相关手段整体无效——不是因为它改不动，而是因为 Qt 根本不看这个 API 的结果。

### 1.4 第 1 层与第 2 层必须分开

弹窗期间同时存在两层独立机制，混为一谈会得到错误结论：

| 层 | 机制 | 位置 | 进程外可否解除 |
| --- | --- | --- | --- |
| 第 1 层 | Qt 应用模态阻断（输入事件被丢在 `notify` 入口） | Qt 进程内 | **否** |
| 第 2 层 | 样本自身的控件软禁用 `MainWindow._disable_protected_actions`（`_protected_widget_names`，`0x872b93`；同簇 `_set_resource_initialization_widgets_enabled` `0x872c2f`、`_apply_resource_initialization_state` `0x872c8c`） | 样本 Python 层 | 理论上可被 Win32 改窗口状态抵消，但**无意义** |

被软禁用的 8 个控件：`btn_manifest_settings`、`btn_process`、`btn_search`、`btn_advanced_settings`、`btn_update_steam`、`btn_update`、`btn_authorize`、`btn_tanushiki_launch`。

**判定**：只让第 2 层失效（例如强行让这些按钮 `enabled`）会产生「能点但没反应」的假象 —— 因为第 1 层仍在。**只有第 1 层被绕过，功能才真正可用，而第 1 层不可从进程外绕过。**

### 1.5 弹窗的模态来源（回答「模态从哪来」）

`setModal`（14 处）**没有一处落在 `src.gui.verification_dialog` 的编译单元内**（模块区间 `0x891d9f`–`0x89238e`；该单元 22 个方法全量清单见证据附录第四节，无 `setModal`）。

构造点的常量簇在 **`src.gui.ui_builder`** 内（`0x88ee60`–`0x88ef80`），是 `MainWindowUIBuilder` 里 `verification_dialog` 属性的构造路径：

```
... aself  acentral  .src.gui.verification_dialog  ...
asetFixedHeight  asetModal  Tt  asetWindowTitle  uKeySteam 验证
asetObjectName  TaverificationDialog
asetWindowFlag  aQt  aWindowType  aWindowContextHelpButtonHint
```

判定：**模态由调用方显式设置** —— 在 `ui_builder` 的构造路径上调用 `setModal(True)`。`VerificationDialog.__init__(self, parent, initial_config, initial_error)` 的签名里没有 modality 参数，与「由调用方设置」一致。

顺带确证窗口标志：`setWindowFlag(... WindowContextHelpButtonHint)` 是**唯一**显式标志（`ui_builder` 内该字符串出现 1 次，全库 3 次）。**没有 `WindowStaysOnTopHint`、没有 `FramelessWindowHint`** —— 也就是说弹窗在 Z 序上并无强制置顶，只是「挡住输入」。这从另一个角度印证：阻断来自 Qt 的模态判定，而不是任何窗口层级技巧。

### 1.6 代价

不适用于「进程外抑制」，因为不可行。若走**进程内注入**（DLL 注入后直接操作 `QApplicationPrivate`）：需要管理员权限 + 需要解除符号修饰、且 `QApplicationPrivate` 是 Qt 私有 API（`qt6widgets.dll` 导出表中未见该类符号，且该 DLL 是运行期 `LoadLibrary` 加载，不在静态导入表里）；此外会面对 `RuntimeGuard` 的注入扫描（`src.security.runtime_guard`，`0x89788e`，`_KNOWN_HOOK_FILE_NAMES` / `_has_hard_injection` / `_kill_main_process`）——**但该扫描有明确豁免，见 §2.2 的限定条件，不宜笼统断言「必被发现」**。**这属于改样本，不是抑制。** 注入路径的实测结论见 `docs/probe-injection.md`。

---

## 二、Windows 层对话框抑制 API：逐条判定

判据统一：**Qt 模态在进程内，进程外 API 改的是 Qt 不读的状态。**

| API | 进程外可用 | 需要的权限 | 对 Qt 窗口是否有效 | 判定 |
| --- | --- | --- | --- | --- |
| `EnableWindow` | 是 | 目标进程同用户/session；跨完整性级别需 `SeDebugPrivilege` 或管理员 | **无效** —— 只清 `WS_DISABLED` 投影，不改 `modalWindowList` | 不可行 |
| `SetWindowLong(GWL_STYLE)` | 是 | 同上 | **无效** —— 同上 | 不可行 |
| `SendMessage` / `PostMessage` 发 `WM_` 消息 | 是 | 同上 | **无效** —— 跨进程发送的**非自发事件**（`spontaneous()==false`）不走 QPA 鼠标/键盘处理路径，而 `blockedByModalWindow` 判定位于 `QGuiApplicationPrivate::processMouseEvent` 内，即只在平台事件入队路径上生效 | 不可行（但对「用 `PostMessage` 合成点击绕过 Qt 判定」的想法，**未取得源码级反证，标注为未确证**，见第六节） |
| `SetWindowsHookEx(WH_CBT)` 的 `HCBT_CREATEWND` | **仅进程内** | 全局 hook 需在 DLL 中实现，且需同 session / 管理员 | **不可行** —— 见下 | 不可行 |
| `SetWinEventHook` | 是（`WINEVENT_OUTOFCONTEXT` 可跨进程，hook 函数在本进程） | 无特殊权限（可只监听目标 pid） | **观测有效、干预无效** —— 它是**通知**机制，不提供阻止窗口创建的能力 | 不可行 |
| `SetWindowsHookEx` 注入（`WH_CALLWNDPROC` / `WH_GETMESSAGE`） | 需把 hook 代码放进 DLL 并注入目标进程 | 管理员；跨位数限制 | 需进程内执行 + 需理解 Qt 私有符号 → 撞 `RuntimeGuard` | 不可行（且属改样本） |

### 2.1 `HCBT_CREATEWND` 能否阻止窗口创建

**能在 SysWOW/同进程场景阻止，但对本样本无法从进程外部署。**

微软官方文档（[CBTProc callback function](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/legacy/ms644977(v=vs.85))）对返回值的定义是明确的：

> "For operations corresponding to the following CBT hook codes, the return value must be 0 to allow the operation, or 1 to prevent it. — **HCBT_ACTIVATE**, **HCBT_CREATEWND**, **HCBT_DESTROYWND**, **HCBT_MINMAX**, **HCBT_MOVESIZE**, **HCBT_SETFOCUS**, **HCBT_SYSCOMMAND**"

以及 `HCBT_CREATEWND` 的语义：

> "A window is about to be created. The system calls the hook procedure before sending the WM_CREATE or WM_NCCREATE message to the window. **If the hook procedure returns a nonzero value, the system destroys the window; the CreateWindow function returns NULL**, but the WM_DESTROY message is not sent to the window."

也就是说：**机制上确实可以阻止窗口创建**。但部署条件使它在进程外不成立：

- `WH_CBT` 要拦截**目标进程**创建的窗口，hook 过程必须在该进程内执行 —— Windows 只在 `SetWindowsHookEx` 的 **hook procedure 位于 DLL 中**时才把它注入其它进程（对 `WH_CBT` 等非 `WH_KEYBOARD_LL`/`WH_MOUSE_LL` 类型）。这意味着必须构造注入 DLL、需要管理员权限、并且 `SetWindowsHookExW` 在**整个 payload 中零命中**说明样本自身不做这事。
- 即使成功注入，也会撞上 `RuntimeGuard`：`src.security.runtime_guard` 明确实现「注入扫描」（`_KNOWN_HOOK_FILE_NAMES`、`runtime_injected_module_message`、`_has_hard_injection`），发现可疑模块**直接 `_kill_main_process`**。相关字符串在 `0x896bd0`（`suspicious_modules_for` / `runtime_injected_module_message` / `_trigger_tamper` / `_request_watchdog_kill` / `_kill_main_process`）。

  **限定条件（2026-09-16 补，来自 `_has_hard_injection` 的明文 docstring）**：该扫描**不是无差别触发**。`0x896c5d` 处的 docstring 原文为：

  > `Only definite injection features (hook DLL / abnormal exe mapping).`
  > `DLLs under user-writable or temp directories are often loaded by legitimate software such as IMEs; killing on those would crash normal users (e.g. after clicking the captcha input). A failed scan must not be treated as injection either.`

  即存在两条明确的豁免：
  1. **只对「确定的注入特征」动作**（hook DLL / 异常的 exe 映射）——临时目录、用户可写目录下的 DLL 属**已知的误报来源**，因为输入法等正常软件也会加载它们，杀它会导致正常用户崩溃；
  2. **扫描失败不得当作注入**。

  因此「注入必被发现」这一说法**过强**。准确的表述是：**若注入留下「确定的注入特征」，会被检测并 `_kill_main_process`**；
  哪些特征算「确定」、`temp_rule` / `strict` 的默认值，仍**未取得代码级证据**（本报告 §6 已列为未确证）。
  **注入探针的实测结果见 `docs/probe-injection.md`。**
- 而 `HCBT_CREATEWND` 的拦截时机是**窗口创建时**。Qt 创建 `QWidgetWindow` 是 `create()` 路径，此时窗口尚未可见，但 `setModal(True)` 已经或即将生效 —— 更根本的问题是：阻止窗口创建等于**让弹窗不存在**，可这必然打断样本自己的启动序列（`_handle_verification_config_ready` / `_failed` 期望弹窗对象存在），属改样本行为。

### 2.2 代价汇总

上述全部路径都需要 **管理员权限**（跨进程窗口操作 / 注入 / 全局 hook），且除 `SetWinEventHook` 外都需要向目标进程投放代码 —— 那是**改样本**，与零字节改动路线冲突。

---

## 三、进程外网络层拦截（MITM）：分解判定

### 3.1 样本的 TLS 校验实现

`src.gui.main_window` 编译单元内（`0x8b9ec6`–`0x8b9ef0`）：

```
a_SHIKI_BUNDLE_DIR_NAME  a_SHIKI_KODO_CACHE_NAME  assl  acreate_default_context
acertifi  awhere  Tacafile  aRequest  uUser-Agent  a_REQUEST_USER_AGENT  aAccept
Taheaders  aurlopen  a_
```

即：样本用 `ssl.create_default_context(...)` + `certifi.where()` 得到 CA 束路径，再以 `cafile=` 传入。**这是默认校验路径，不关校验。**

全库计数：`certifi` 66、`cafile` 14、`create_default_context` 8、`check_hostname` 5、`load_verify_locations` 4、`CERT_NONE` 3、`CERT_REQUIRED` 2、`_create_unverified` 1。

`CERT_NONE` / `_create_unverified` 必须按模块归属核实（本项目已登记多次「邻接当归属」的错误模式）。**未取得逐条归属**，故「样本是否存在关校验的分支」标注为**未确证**（第六节）。但即便存在，`src.gui.main_window` 的 `create_default_context` 路径已经是**默认校验**，该路径被使用即足以否定「靠关校验绕过」。

### 3.2 CA 环境变量：样本侧零命中，库侧有读取

**关键区分**：字符串出现在样本里 ≠ 样本自己读它。按模块边界逐条核实结果的归属：

| 字符串 | 偏移 | 归属模块 |
| --- | --- | --- |
| `SSL_CERT_FILE` | `0x7ce72c` | **`curl_cffi.const`** |
| `CURL_CA_BUNDLE` | `0x7ce73b` | **`curl_cffi.const`** |
| `REQUESTS_CA_BUNDLE` | `0x7ce74b` | **`curl_cffi.const`** |
| `REQUESTS_CA_BUNDLE` | `0x7dc96e` | **`curl_cffi.requests.models`** |
| `CURL_CA_BUNDLE` | `0x7dc984` | **`curl_cffi.requests.models`** |

**没有任何一处落在 `src.*` 模块内。** `curl_cffi.const` 的上下文为：

```
aSSL_CERT_FILE  aCURL_CA_BUNDLE  aREQUESTS_CA_BUNDLE  aenviron
assl  aget_default_verify_paths  acafile  acertifi  awhere
```

**判定**：读取这三个环境变量的是 **`curl_cffi` 库自身**，不是样本的业务代码。含义：只要用 `curl_cffi` 发起的请求，设 `REQUESTS_CA_BUNDLE` / `CURL_CA_BUNDLE` 即可替换其信任的 CA 束（库行为，可见于 [`curl_cffi` 的 `const.py` 与 `requests/models.py`](https://github.com/lexiforest/curl_cffi)）。

**但这对本任务无效**，因为：`aiohttp` 路径走 `ssl.create_default_context` + `certifi.where`（样本侧），**不受** `REQUESTS_CA_BUNDLE` 影响；而 `SSL_CERT_FILE` 是 OpenSSL/Python `ssl` 层的变量，`create_default_context` 会读它 —— 但要确认样本是否覆写。**这一条标注为未确证。**

`SSL_CERT_DIR`：**0 命中**。

### 3.3 决定性障碍：Ed25519 签名无法伪造

即使 MITM 成功（CA 被替换、响应被改写为「验证通过」的 JSON），**票据的 `signature` 字段验不过**。

事实（已由证据附录第一节确证）：

- **公钥内嵌于样本**：`src.security.public_key` 的模块级常量 `MANIFEST_PUBLIC_KEY_PEM`（`0x8959f3`），函数 `get_manifest_public_key_pem`（`0x895abe`）直接返回它，**不是从服务端取的**。
- 公钥 PEM：`MCowBQYDK2VwAyEASiaXwDqO2Bbt3W3UgA36ZAxq1ZClERx0i2Xw1vS/eoI=`，OID `1.3.101.112` = **Ed25519**，裸公钥 32 字节 `4a2697c03a8ed816eddd6dd4800dfa640c6ad590a5111c748b65f0d6f4bf7a82`。
- **样本内不含任何私钥**（`-----BEGIN PRIVATE KEY-----` 0 命中；`Ed25519PrivateKey` 的 22 处命中全在 `cryptography` 库自身的 `__copy__` / `__deepcopy__` 代码区 `0x7bc22e`–`0x7bc4xx`；`PRIVATE KEY` 2 处全在 `cryptography` 的 OpenSSH 格式支持区 `0x7c5608` / `0x7c5636`）。

Ed25519 是**数字签名**算法：只有持私钥者能生成合法签名，验签只需公钥。**MITM 方无私钥 → 无法为伪造的票据生成通过验签的 `signature`。**

因此必须把 MITM 拆成两个子问题：

1. **仅 MITM（不改样本）**：**不成立**。响应可被改写，但改写后的票据签名无法通过内嵌 Ed25519 公钥的验签。**这是决定性障碍，与「能否 MITM」无关。**
2. **MITM + 改样本（替换内嵌公钥，并自带配套私钥自签）**：**理论上自洽** —— 公钥是明文可读的常量，可替换。但这**明确属于改样本**，超出 ADR 0001 的「零字节改动」范围。
3. **单纯替换公钥而不做 MITM**：同样属改样本，且仍需服务端返回与自签公钥匹配的票据 —— 实际上等于自建一套完整的签发链，等同于把样本的验证体系整体替换。

### 3.4 不要混淆：两套独立密钥体系

| 用途 | 算法 | 位置 |
| --- | --- | --- |
| 清单 / 票据**签名** | **Ed25519** | `src.security.public_key`（`0x895adc` 簇） |
| `steam-data/upload` 载荷**加密** | **X25519 + ChaCha20Poly1305 + HKDF** | `0x85b8f1` 簇（`_load_server_encryption_public_key` / `_SERVER_KEY_ID` / `_ENVELOPE_VERSION` / `aexchange` / `aHKDF`），端点 `https://key.steamofl.com/api/steam-data/upload`（`0x85bc66`） |

两者**相互独立**：前者用于验签（对抗伪造），后者用于上传载荷的机密性（对抗窃听）。打破后者不产生任何验证能力。

### 3.5 代价

- 仅 MITM：需要能控制样本出站流量的位置（同机代理 / 网关），需要替换样本信任的 CA。**样本侧零命中**说明样本不读那些 CA 变量；改环境变量是否有效**未确证**；改 hosts + 装根证书会**改变系统状态**，本研究不允许执行。
- MITM + 改样本：需修改 `MANIFEST_PUBLIC_KEY_PEM` 常量或替换其读取路径 —— 属改样本。

---

## 四、Nuitka 编译产物：无官方「跳过初始化 / 指定入口」机制

### 4.1 `_NUITKA_ONEFILE_DLL_MODE` 的真实语义

取自 Nuitka 官方仓库 [`nuitka/build/static_src/OnefileBootstrap.c`](https://raw.githubusercontent.com/Nuitka/Nuitka/develop/nuitka/build/static_src/OnefileBootstrap.c)：

```c
#if _NUITKA_ONEFILE_DLL_MODE
static int runPythonCodeDLL(filename_char_t const *dll_filename, int argc, native_command_line_argument_t **argv) {
    DLL_DIRECTORY_COOKIE dll_dir_cookie = AddDllDirectory(payload_path);
    HINSTANCE hGetProcIDDLL = LoadLibraryExW(dll_filename, NULL, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | ...);
    ...
    typedef int(__stdcall * nuitka_dll_function_ptr)(int, wchar_t **, wchar_t const *);
    nuitka_dll_function_ptr nuitka_dll_function =
        (nuitka_dll_function_ptr)GetProcAddress(hGetProcIDDLL, "run_code");
    ...
    return (*nuitka_dll_function)(argc, argv, dll_filename);
}
```

三个可核实的要点：

- **`run_code` 是硬编码的导出名**，`GetProcAddress(hGetProcIDDLL, "run_code")`，官方无「指定入口」选项。
- **调用约定**：`int(int argc, wchar_t **argv, wchar_t const *dll_filename)`，`__stdcall`，**argv 指针直传** —— 与任务前提一致。
- **父/子进程判定**：靠环境变量 `NUITKA_ONEFILE_PARENT`（父进程 pid）。父进程 `setEnvironmentVariableFromLong("NUITKA_ONEFILE_PARENT", GetCurrentProcessId())`；子进程读它并用 `GetModuleFileNameExW` 校验父进程路径是否等于自身二进制路径，不等则视为「不是子进程」。同时父进程会 `unsetEnvironmentVariable("NUITKA_ONEFILE_START" / "NUITKA_ONEFILE_TIME_US" / "NUITKA_ONEFILE_RANDOM")`。

**`run_code` 由编译产物自己提供**（`main.dll` 的导出名 `run_code` 可在其数据段中直接读到，位于导出名区 `0x1d4939b`；同处紧邻 `main.dll` 字符串）。它在 `main.dll` 内部再调用 Nuitka 生成的 `_run_code`（`0x198ee88` 处可读到 `_run_code` 标识与 `exec` / `mod_spec` / `pkg_name` / `script_name` / `fname` 的代码对象常量）。**没有任何官方开关可以改变这个链条的分支。**

### 4.2 环境变量：只有「解包目录」语义

官方文档 [Use Cases — Nuitka](https://nuitka.net/user-documentation/use-cases.html) 明确：

> "For the unpacking, by default a unique user temporary path one is used, and then deleted, however this default `--onefile-tempdir-spec="{TEMP}/onefile_{PID}_{TIME}"` can be overridden with a path specification …"

`OnefileBootstrap.c` 中解包路径由 `expandTemplatePathFilename(payload_path, pattern, ...)` 展开，`pattern = _NUITKA_ONEFILE_TEMP_SPEC`（编译期常量），并在解包完成后设置：

```c
setEnvironmentVariable("NUITKA_ONEFILE_DIRECTORY", stripBaseFilename(binary_filename));
setEnvironmentVariable("NUITKA_ORIGINAL_ARGV0", argv[0]);
```

即：**`NUITKA_ONEFILE_DIRECTORY` 是 bootstrap 写出去的，不是读进来的**；`NUITKA_ONEFILE_TEMP` 是样本自己在 `RuntimeGuard._spawn_watchdog` 里读的（`0x8967b0` 簇：`_SECRET_ENV_NAME` / `NUITKA_ONEFILE_TEMP` / `subprocess` / `Popen` / `--watchdog` / `CREATE_NO_WINDOW`），**属样本自有的看门狗握手约定**，不是 Nuitka 的开关。

样本中 `NUITKA_ONEFILE_TEMP` 命中 3 次、`NUITKA_ONEFILE_DIRECTORY` 1 次，**全部服务于「找自身临时目录」这一目的**，与启动链控制无关。

### 4.3 `--windows-console-mode` / 部署模式

- `--windows-console-mode`（官方 [Common Issue Solutions](https://nuitka.net/user-documentation/common-issue-solutions.html) 中的 `--windows-console-mode=disable`）**只影响控制台窗口的显示与 stdout/stderr 去向**，对启动流程与模块初始化**无影响**。且它是**编译期**选项，运行期不可改。
- `--deployment` / `--no-deployment-flag=*` 同样是**编译期**选项，只控制 Nuitka 的运行时安全辅助（如自执行 fork bomb 检测）。样本显然保留了非部署模式（`main.dll` 中存在 `NUITKA_ONEFILE_DIRECTORY` 与 `lost sys.stdout` 等非部署模式辅助串）。
- **Nuitka 官方文档中不存在任何「跳过某些模块初始化」或「运行期指定入口模块」的机制。** 这属于**不存在**，而非「未查到」：官方 User Manual 与 Common Issue Solutions 的选项全表均无此语义（入口由编译期的 `--main` / 位置参数决定，见 Multidist 一节）。

### 4.4 判定

**不可行。** 代价：N/A。运行期改 `NUITKA_*` 环境变量只能影响解包位置与自执行检测，无法改变「调用 `run_code` → 跑 `src.gui.__main__`」这条链。

---

## 五、样本 argv 入口是否提供「免验证」路径

### 5.1 分发点的精确形态

`src.gui` 的 `__main__`（`0x861f25`–`0x862151`）：

```
... src.gui   argv   --extract-authorization   src.steam.authorization_workflow_service
    run_authorization_extract_cli   :l\x02nn   --watchdog   src.security.runtime_guard
    run_watchdog_cli   app   run   ...   src\gui\__init__.py   <module src.gui>
```

即：

```
argv 含 --extract-authorization → run_authorization_extract_cli(argv)
argv 含 --watchdog              → run_watchdog_cli(argv)
默认                            → run_gui()
```

`run_authorization_extract_cli` 的**定义处**在 `0x8aaa7e`（`src\steam\authorization_workflow_service.py` 相关，模块标记 `<module src.steam.authorization_workflow_service>` 位于 `0x8aab4c`，其常量簇 `0x8aab4c`–`0x8ad443`）。

### 5.2 CLI 是否调用票据校验 / 闸门函数

**结论：未确证内部是否调用；但已确证它不需要票据，且不解决弹窗。**

逐条证据：

**（a）闸门函数不是 CLI 路径的一部分。** `_verification_gate_allows` 全库仅 2 处命中，且**两处都属 `MainWindowController`**（`src.gui.main_window_controller`，模块标记 `0x88020c`）：

- `0x876905` —— `MainWindowController._run_startup_remote_manifest_check_async` 的常量簇内，同簇含 `verify_ticket`（`0x876934`）/ `load_verification_ticket`（`0x876943`）/ `IntegrityCheckResult` / `TAMPERED` / `_emit_integrity_lock` / `show_tamper_warning` / `verify_remote_manifest_async` / `UNREACHABLE`。
- `0x87ccda` —— qualified 名 `MainWindowController._verification_gate_allows`，邻近 `_guard_sensitive_action`（`0x87cc96`）与 `_on_runtime_tamper`（`0x87cc5d`）。

两个位置都在 `src.gui.main_window_controller` 的编译单元范围内，**与 `src.steam` 模块不相交**。

**（b）CLI 所属模块内零验证术语。** 对 `src.steam.authorization_workflow_service` 的完整常量区间 `0x8aab4c`–`0x8ad443` 做计数：

```
verify_ticket               0
load_verification_ticket    0
_verification_gate_allows   0
Verification                0
verification                0
main_window                 0
ticket                     30   ← 全部是 Steam AppTicket 语境
```

**（c）CLI 的实际闸门是另一个。** 同簇（`0x8a6b8f` 附近）可见：

```
u缺少 AppID 参数        ← 缺 AppID 直接报错
S\x03  u--app-ticket  u--encrypted-ticket  u--steam-id  uUnknown flag:
a_extract_authorization_payload_direct
```

即 `run_authorization_extract_cli` 的参数校验针对 **`--app-ticket` / `--encrypted-ticket` / `--steam-id`**，三个参数与 Steam AppTicket 强绑定；这些符号的唯一归模块是 `src.steam.authorization_workflow_service`（`AuthorizationWorkflowService` 的类型引用只出现在 `src.gui` 的三个对话框与 `src.gui.main_window_controller`）。

**（d）为什么不能判定「无调用」。** Nuitka 的常量池按函数聚合，跨模块调用**只留一个模块名引用** —— `verify_ticket` 的 7 处 / `load_verification_ticket` 的 7 处命中分布仍是此前的簇，但这只能说明「CLI 所在模块自身未把这些符号纳入其常量池」，**不能排除**通过 `AuthorizationWorkflowService` 实例或其它中间层间接调用验证逻辑。**如实标注为未确证。**

### 5.3 复核：`--encrypted-ticket` 与号商票据是两条链

**确证。** `src.steam.authorization_workflow_service` 的常量簇中出现 `SteamAPI_ISteamUser_GetEncryptedAppTicket`、`ticket_buffer`、`ticket_size`、以及中文串「获取 EncryptedTicket 超时，请稍后重试」（`0x8a3d62` 附近），另有 `write_app_ticket_registry` / `clear_ticket_authorization_registry` / `AppTicket` / `ETicket` / `SteamID` 注册表写入路径（`0x8a51c6` 附近，`HKEY_CURRENT_USER\Software\Valve\Steam\Apps\...`）。

这与号商票据链（`key.steamofl.com` 签发、`%APPDATA%\Shikieiki\verification.cache` 落盘、`KV1` + AESGCM + `_machine_bound_key` + HKDF）在**数据来源、加密体系、落盘位置、校验函数**上全不相同。

**重放命令（核对两支链条的符号不交叠）**：

```bash
# 1) 号商票据链的符号，全部落在 src.security.*
python3 - <<'PY'
import re
d=open('/tmp/ks2/rdata.bin','rb').read()
marks=[(m.start(), m.group().decode('utf-8','replace'))
       for m in re.finditer(rb'<module [\x20-\x7e]{1,90}>', d)]
marks.sort(); marks.append((len(d),'<EOF>'))
def owner(off):
    for i,(o,n) in enumerate(marks):
        if o<=off<marks[i+1][0]: return n
for tok in [b'verify_ticket', b'load_verification_ticket', b'save_verification_ticket',
            b'clear_verification_ticket', b'_verification_gate_allows']:
    print("#", tok.decode())
    for m in re.finditer(re.escape(tok), d):
        print(f"   0x{m.start():x}  {owner(m.start())}")
PY
```

预期：全部命中归属 `src.security.ticket` / `src.security.sponsor_verification` / `src.security.verification_cache` / `src.gui.*`，**无一处归属 `src.steam.*`**。

```bash
# 2) Steam AppTicket 链的符号，全部落在 src.steam.*
grep -ao 'SteamAPI_ISteamUser_GetEncryptedAppTicket\|encrypted_ticket\|app_ticket' /tmp/ks2/rdata.bin | sort | uniq -c
```

### 5.4 判定

**走 `--extract-authorization` 即使成功，也拿不到能消除弹窗的东西。** 它产出的授权文件（`export_authorization_file` / `import_authorization_file`）走的是 Steam AppTicket 体系，与启动验证的号商票据体系无关。**它不解决弹窗。**

另需注意：`--extract-authorization` 运行时同样会加载完整 `main.dll`，`RuntimeGuard` 的启动路径是否被跳过**未确证**；且样本的无条件网络行为（每次启动访问 `key.steamofl.com`）在 CLI 路径下是否仍发生**未确证**。

---

## 六、未能确证的问题

1. **`run_authorization_extract_cli` 内部是否调用 `_verification_gate_allows` 或任何票据校验函数。**
   已确证的只有：闸门属 `MainWindowController`、CLI 所在模块的常量池零验证术语、CLI 自有闸门是 `--app-ticket` / `--encrypted-ticket` / `--steam-id` 三参数校验。Nuitka 按函数聚合常量，跨模块调用只留一个模块名引用，**因此常量簇距离不能证明无调用**。需要动态断点或对 `main.dll` 的 `.text` 做控制流分析才能定论。

2. **`SSL_CERT_FILE` 是否被样本自身读取（而非仅 `curl_cffi` 库）。**
   已确证：`SSL_CERT_FILE` / `CURL_CA_BUNDLE` / `REQUESTS_CA_BUNDLE` 的全部命中都在 `curl_cffi.const` 与 `curl_cffi.requests.models`，**样本侧零命中**。但 `aiohttp` 路径用的 `ssl.create_default_context`（`src.gui.main_window`，`0x8b9ef0` 簇）在 Python 标准库层面**会**读 `SSL_CERT_FILE`/`SSL_CERT_DIR`。样本是否覆写该上下文、以及 `cafile=` 与默认信任库的优先级，**未在本研究中运行验证**。

3. **`CERT_NONE`（3 处）/ `_create_unverified`（1 处）/ `load_verify_locations`（4 处）的模块归属。**
   未逐条按模块边界核实。若其中有落在 `src.*` 的，则存在「样本主动关校验」的分支 —— 但这不影响第 3 节的结论，因为签名障碍与 TLS 校验完全无关。

4. **跨进程 `PostMessage` 合成鼠标/键盘消息能否绕过 Qt 的 `blockedByModalWindow` 判定。**
   已确证的只是：`blockedByModalWindow` 的判别位于 `QGuiApplicationPrivate::processMouseEvent`（平台事件入队路径），而跨进程投递的消息属于**非自发事件**（`spontaneous()==false`），其分发走 `QApplication::notify` 的另一支。**是否能直达控件并触发槽函数，需要实际运行 `PostMessage` 合成点击来验证 —— 本研究为只读，未执行。**

5. **票据文件在跨日/重启后消失的直接原因（删除者未定位）。**
   已确证写入是原子替换（`.tmp` + `Path.replace` + `unlink(missing_ok=True)`），且样本不会自行续期。删除动作的触发者未定位。

6. **`VerificationDialog` 的 `setModal` 调用是否在 `ui_builder` 的同一常量簇内。**
   已确证 `setModal` 唯独在 `src.gui.ui_builder`（`0x88eee1`）中与 `setWindowTitle("KeySteam 验证")` / `setObjectName("verificationDialog")` / `WindowContextHelpButtonHint` 同簇，且 `src.gui.verification_dialog` 单元内 `setModal` 零命中。但**该路径是否就是弹窗实际构造路径**（而非另一个同名属性构造），未做动态确认。

---

## 附：全篇重放命令索引

| 目的 | 命令位置 |
| --- | --- |
| 重建 `.rdata` / `.text` 节转储 | `docs/suppressing-the-dialog-evidence.md` 开头 |
| 解析内嵌 Ed25519 公钥 | 同上，第一节 |
| 验证 payload 无 `EnableWindow` | 本文 §1.2 |
| 按模块边界判定符号归属 | 本文 §5.3 |
| 核对 CA 环境变量归属 | 本文 §3.2 |
| 核对 CLI 入口与闸门位置 | 本文 §5.1 / §5.2 |

---

**一句话结论**：弹窗不是可以被「关掉」的窗口，而是**启动链的一个判定结果**；把它压下去需要进程内改写 Qt 状态或伪造 Ed25519 签名，两者都跳过不了一条杠 —— **它没有漏洞，它是设计**。
