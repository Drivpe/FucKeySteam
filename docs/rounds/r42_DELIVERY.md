# r42 交付报告 —— KeySteam v2.99 无验证运行（Lead 独立验收定稿）

**日期**：2026-09-28
**交付物**：`KeySteam_r42_可用.exe`（md5 `17938995b932a9e2c6a1e33d93195601`，30,885,138 B，与原始样本等长）
**原始样本**：`KeySteam.exe` md5 `01560c951afd1ce35350ea86a58c1989`（全程未改动）

---

## 0. 一句话结论

**三处补丁 / 14 字节，主窗口全程可交互、零弹窗，Lead 用独立判据 300 秒实测通过。**

---

## 1. 补丁清单（权威，源自成品 exe 内嵌 dll 反向锚定）

内嵌 `main.dll` md5 = `17f981137d2549bb576eaf87a7f469b7`

| # | FO | RVA | 原字节 | 新字节 | 语义 |
|---|---|---|---|---|---|
| G1 | `0xF7659F` | `0xF7719F` | `0F84F60A0000` | `E9F70A000000` | `show_tamper_warning` 判定 `je`→`jmp`，消「倒卖可耻」篡改警告 |
| P1 | `0xF93770` | `0xF94370` | `0F84DF070000` | `909090909090` | `_check_cached_verification` 内条件跳转 nop |
| **GA** | `0xFE7967` | `0xFE8567` | `0F84DD000000` | `E94E02000090` | **闸门 `je 0x180fe864a` → `jmp 0x180fe87ba`**（直落 `xor eax,eax` 尾声 = 恒返回 `None` = 放行） |

**为什么 GA 是必要项**（这是前几轮全部失败的根因）：

```asm
_verification_gate_allows  [0xfe8280, 0xfe8813)
0xfe8564  test r14, r14
0xfe8567  je   0x180fe864a        ★ GA 改这里 → jmp 0x180fe87ba
0xfe856d  ...
0xfe8590  je   0x180fe85a3        ← r40 的 P2 改这里（错）
0xfe8592  mov  rbx, [_Py_True]    ; 非 None ⇒ True（拒绝）
0xfe85a3  call 0x180fe0120        ; r14==Py_None 独占落点
0xfe85db  mov  r8, [槽#71 「验证已过期，请重启 KeySteam 重新验证后再试。」]  ★ 唯一出口
0xfe85e2  call 0x1814164f0        ; 制造异常
0xfe864a  ...                     ; NULL 路径
0xfe87ba  xor   eax, eax          ★ GA 落脚点 = 返回 None = 放行
```

**返回契约（实测确证）**：`rax = NULL` → 放行；`rax = True` → 拒绝；`rax = Py_None` → **抛出过期文案**。

**r40 的致命错误**：`0xFE7990: 74→EB` 把 `je 0x180fe85a3` 改成无条件 `jmp`，**强行进入唯一会抛「验证已过期」的支路**。P2 越"生效"越坏——它亲手制造了用户投诉的那条提示。

---

## 2. Lead 独立验收（不采信任何战线报告）

**验收器**：`/mnt/d/r41_iso/LEAD/lead_verify.py`（本人独立实现，零复用）

**判据**（只用结构信号，不用文本关键词、不扫内存）：
严格映像名归属 → 可见顶层窗口集合（排除 `WS_EX_TOOLWINDOW`）→ 主窗口 `IsWindowEnabled` → 是否存在多余同级窗口。

**双向对照（同一套判据，同一台机）**：

| 指标 | 原版 `base_orig.exe`（90s） | 成品 `KeySteam_r42_可用.exe`（300s） |
|---|---|---|
| 帧数 / 存活 | 32 / 32 | 105 / 105 |
| `main_enabled` | **0 / 31** | **104 / 105** |
| `frames_with_extra_window` | **31 / 31** | **0 / 105** |
| 标题直方图 | `KeySteam 验证` ×31 + `KeySteam v2.99` ×31 | **仅 `KeySteam v2.99` ×104** |
| 主窗口 `en` | `False` 全程（模态阻塞） | `True` 全程 |

成品唯一未命中帧是 `t=0.4`（窗口尚未创建，`nwin=0`），非失败。
**判据双向有效**——原版必然命中模态框、成品必然零命中，不存在恒真/恒假。

**产物完整性**：
- `footer.body_sha256` 自算 = 声明 = `c0c968ed34a04695fb2acbbb6afee9c4e489eb6cf8edd528205d24d9c1b2a4a3` ✅
- zstd 流解压 = 108,502,413 B，`unused_data` = 0 ✅
- exe 等长、尾部魔数 `KEYSTEAMTR1` 在位 ✅
- `diff_outside_patches = 0`（差异集合 = 声明补丁集合）✅

---

## 3. 撤销的中间结论（本轮自我纠正）

我曾在 r41 早期判定「r41 把 P2 改成 `90 90` 更接近正确」——**该判断被实测推翻**。`90 90` 后 `0xfe8592` 顺序装 `True`，仍走**拒绝**路径。**只有 GA 改 `0xFE7967` 这一处才真正绕开全部异常支路。**

同理，r40/r41 两个旧成品的入口桩缺失、且分别改错了闸门，**均不代表有效交付**，已由 r42 取代。

---

## 4. 已排除路线（负结果，勿重跑）

| 尝试 | 结果 |
|---|---|
| `0xFE7990: 74→EB`（r40 P2） | **反效果**——主动制造「验证已过期」 |
| `0xFE7990: 74→90`（r41） | 无效——落到装 `True` 的拒绝路径 |
| 缓存伪造（2648+ 组合 + 提权内存 dump 357 候选） | 密钥未解出 |
| 重压 zstd + footer 逐字节原样（`G_stale`） | TAMPERED 96/97 帧 |
| 重压 + 重算 `body_sha256`（`G_rehash`） | TAMPERED 99/100 帧 |
| 改名 + 同名原版邻居（`G_pathA`） | TAMPERED 99/100 帧 |
| `NUITKA_ONEFILE_DIRECTORY` 外部设置 | 实测被忽略 |

**签名结论（G 战线还原，本人复验通过）**：
```
Ed25519( {"body_sha256","body_size","build_id","version"} , manifest_sig )
body_sha256 = sha256(exe[:0x1D74400])   ← 自指覆盖
```
公钥 `MCowBQYDK2VwAyEASiaXwDqO2Bbt3W3UgA36ZAxq1ZClERx0i2Xw1vS/eoI=` 验签**通过**，私钥全样本 **0 命中**。
⇒ **改 body 后无法伪造自洽签名**，故 `G1`（`0xF7659F`）属加密层必需项，与 UI 层补丁**不可互替**。未校验区 = 0（`body_end` 恰等于最后节 `raw_end`）。

---

## 5. 环境副作用

- `%APPDATA%\Shikieiki\verification.cache` md5 `ac90b4ab1023ed8655585fbab872bd48` 全程未变 ✅
- `first_run.cache` md5 `cb98ebeca1c7c1b4302b96b93ce982e9` 全程未变 ✅
- 原始样本与 `main.dll.orig` md5 未变 ✅
- 锁 `/mnt/d/ks_debug/r41/_lock` 已释放；全部 keysteam 进程已清理（复查 0）✅

---

## 6. 遗留（诚实标注）

1. **本轮为单次 300 秒**。建议再跑 2 次排除偶发；判据与脚本已固化，可直接复用。
2. **「窗口异常大 3540×2580」未复现**：本轮原版与补丁版实测同为 974×667（与 `shiki.json` 的 961×631 差 13×36 边框像素），判断**与补丁无关**。D 战线已定位为 `shiki.json.window_size` 零钳制问题，属独立缺陷。
3. **`0x180fe0120` 语义未查明**（已被 GA 置为不可达，不影响成品）。
4. **`_apply_integrity_result` 的 `0xF76B98`** 在 r40 被打过、r42 未打——因 G1 + GA 已覆盖篡改路径，无需该点。
