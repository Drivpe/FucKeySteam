# 交付轮次索引：从「静态判定不可行」到 r59 可用产物

**时间跨度**：2026-09-27 ~ 2026-09-29
**上游文档**：本仓库 `docs/`（2026-09-16 三条探针批次）
**本轮目标**：把「消除验证弹窗」从**判定**推进到**可交付产物**

---

## 0. 与上游探针批次的关系

上游 `docs/probe-index.md` 的三条探针给出了三个否定结论：

| 探针 | 结论 |
|---|---|
| `probe-injection.md` | 进程内注入**不能**——三重障碍，GUI 进程定向 DACL 精确拒绝 |
| `probe-repack.md` | 重打包**未能确证**，但确证外部宿主是最轻路径 |
| `probe-ticket-deletion.md` | 票据删除者**已锁定**并可阻止 |

**本轮把「重打包」这条路走通了。** 上游判定的两条「已知阻碍」双双被证伪，
`rebuild_exe.py` 现在能对 Nuitka onefile + 单帧 zstd 的 payload 打任意偏移补丁，
产出与原 exe 等长、可重新解析的副本。

**与上游的关系**：上游是「路在这，但走不通」；本轮是「路走通了，产物能用」。
上游的注入与票据结论**未被推翻**，只是不再是唯一路径。

---

## 1. 轮次脉络

| 轮次 | 文档 | 核心问题 | 结论 |
|---|---|---|---|
| r40 | `round40_*.md`（4 篇） | 起始破题：定位弹窗、运行时守卫、篡改检测 | 建立地址映射与函数边界 |
| r41 | `round41_F_patch_and_accept.md` | F 补丁方案与验收 | 确定补丁骨架 |
| r42 | `r42_DELIVERY.md` | 首轮交付 | 弹窗消除的初步可行 |
| r43 | `r43_DELIVERY.md` | 补丁点收敛 | 收窄候选 |
| r44 | `r44_DELIVERY.md` | 稳定性 | 排除崩溃路径 |
| r46 | `r46_DELIVERY.md` | 完整初始化 | 无刷屏、受保护动作执行 |
| **r53** | `r53_DELIVERY.md` | **「点击即闪退」根因** | **GA 补丁是崩溃充要条件，删除它** |
| **r59** | `r59_DELIVERY.md` | **「更新选中Lua → lua 库未收录」** | **服务端库改版，等长替换 owner** |

### r53 的关键教训（测试方法论）

r53 之前**所有点击测试都是空转**。两个叠加缺陷：

1. 主窗口 `1690x1333` 超出屏幕 `1920x1080`，底部按钮在屏幕外，`SetCursorPos` 静默失败
2. 模态弹窗未关时主窗 `IsWindowEnabled=False`，点击被 Windows 丢弃

脚本报告「完成 N 次点击，未崩溃」，实际**一次都没生效**。
修正：改用 UIA `InvokePattern.Invoke()` + 断言 `en=True`。

### r59 的关键教训（根因归属）

用户报「lua 库未收录」，第一直觉是补丁打坏了。实际是**服务端库改版**：

- 官方库 `ShikieikiC/ShikiLuaQwQ` 已发 3.0.0（Python+PyQt6 → Tauri 2 + Rust + React 重构）
- v2.99 对应的旧桶目录被整体撤下，程序请求的 4 个文件在 67 个历史提交中**全不存在**
- 旧库 fork `Cec1c/ShikiLuaQwQ` / `oureveryday/ShikiLuaQwQ_old` 仍保留，**4/4 全部 200**

**证伪补丁嫌疑的方法**：扫描**未打补丁的原版**启动阶段内存，**零** lua 库 URL 命中
——该路径只在点击「更新」后才构造，非补丁副作用。

---

## 2. r59 修复要点（本轮交付）

### 2.1 owner 的存储方式

`ShikieikiC` 在二进制中**零明文命中**，是运行时由两段 XOR 密文拼接：

| 段 | 密文（hex 文本，FO） | 解密 |
|---|---|---|
| 1 | `60f9c32fa1` @ `0x1CD000E` | `Shiki` |
| 2 | `56f8c12d8b` @ `0x1CD001A` | `eikiC` |

- 密钥 `3391aa44c80b1e72`（`src.security.obfuscated_strings`）
- 密文是 **XOR 结果的 hex 文本**（10 个 ASCII 字符 = 5 字节明文）

### 2.2 等长替换 + 路径填充

目标路径段须**严格 10 字符**（5+5），语义为 `Cec1c` + 5 字符填充：

| 段 | 新密文 | 新明文 |
|---|---|---|
| 1 | `70f4c975ab` | `Cec1c` |
| 2 | `1cbe856be7` | `/////` |

拼接 → `Cec1c/////`，完整路径段 = `Cec1c//////ShikiLuaQwQ`（22 字符，**与原 owner 等长**）。

**填充可行的三条实测依据**：

1. GitHub raw 做路径规范化：`Cec1c//////ShikiLuaQwQ` → 307 → **200**，内容 510 B 正确
2. 镜像直接返回 200（不跟随重定向也拿到内容）：`ghfast.top` / `ghproxy.net` / `gh-proxy.com`
3. 程序不校验路径结构：`is_raw_github_url` 只比对 `hostname == raw_github_host`；
   URL 拼装为 `scheme + "://" + netloc`，无规范化、无结构校验

### 2.3 重打包器的一个前提修正

`rebuild_exe.py` 原把「zstd 流长度」当压缩预算，导致首次构建**误报超预算 68 B**。

实测 r58 布局：

```
zs(KAY+3)    = 0x235B3
se(流终点)    = 0x1D4AFBC
tail_u64     = 0x1D4C4E8   (= 自身偏移 - KAY 偏移)
body_end     = 0x1D74400
流后填充 gap  = 5420 字节，全 0x00
```

**流后有 5420 字节全零填充属正常 Nuitka 布局**；解压器只认 zstd 帧尾，
帧后零字节被忽略。u64 尾指针标记的是**含填充**的 payload 末界，
真实可写预算是 `[zs, tail_u64_off)` = 30,576,440 B。

已修正为 `Layout.budget` 属性并同步写回逻辑。

---

## 3. 内核链路（r59 补充发现）

用户反馈「KeySteamTool 内核入库没用，TanuShiki 可以」——实测澄清：
**入库与内核是两条独立链路**，差异在 Steam 侧授权注入。

| UI 显示名 | `shiki.json` 值 | 部署到 `Steam/dwmapi.dll` 的源文件 |
|---|---|---|
| KeySteamTool 内核 | `ost` | `shiki2.dll` — 142,848 B |
| TanuShiki 内核 | `mmc` | `shiki3.dll` — 7,079,424 B |
| 无内核 | `none` | 不部署 |

`shiki3.dll` 的 PE 版本信息：`FileVersion 2.1.5`、`ProductName SAICore`、
`OriginalFilename dwmapi.dll` —— 本就是为伪装 `dwmapi` 注入 Steam 而设计的**完整内核**。

`shiki2.dll` 整个文件只有 `KeySteamTool.dll` / `proxy_attach.log` /
`KEYSTEAMTOOL_PROXY_ATTACH` 三个串，是**代理挂载桩**，不具备完整授权注入能力。

两者都会写 `Steam/steam.cfg`（`BootStrapperInhibitAll=Enable` +
`BootStrapperForceSelfUpdate=Disable`）抑制 Steam 自更新以保住注入。

**结论**：r59 修的是入库链路，内核差异不属其职责范围。

---

## 4. `docs/tools/` 说明

### 重打包与补丁

- `rebuild_exe.py` —— **主力工具**。Nuitka onefile + 单帧 zstd 通用重打包器。
  支持 `--patch FO:ORIGHEX:NEWHEX`（等长、强制原字节校验）、`--dry-run`。
  全流程校验：布局复检、footer `body_sha256` 重算、产物逐字节比对、区间外零漂移断言。
- `exe_repack.py` / `mkpatch.py` / `patchpoint.py` / `try_patch.py` / `modconsts.py`
  —— 早期重打包与补丁尝试（历史沿革，保留备查）

### PE 与静态分析

- `binlib.py` / `rvarefs.py` / `nuitka_pool_decode.py` / `rederive.py`

### 运行时观测与 UIA（`r53` 轮建立，纪律严格）

- `invoke.ps1` —— 按名字点按钮，**只用 `InvokePattern`**，无屏幕坐标
- `uia_edit.ps1` / `uia.ps1` —— 读控件值 / dump 控件树
- `dump.ps1` / `dump2.ps1` —— 全窗口树 dump（`dump2` 支持按 PID 过滤）
- `sel.ps1` / `sel2.ps1` / `selone.ps1` —— ListItem 选择（`sel2` 多选，`selone` 按 AppID 单选）
- `gobtn.ps1` —— 带 `en=True` 断言的按钮点击
- `radio.ps1` —— RadioButton 选择
- `ab_url.py` / `urlscan.py` / `mmcurl.py` —— 进程内存 URL 扫描（A/B 对照）
- `own.py` / `ctx.py` / `memslot.py` —— 内存串定位

### 本轮验收脚本

- `e2e2.py` —— 端到端：启动 → 关弹窗 → 全选 → 点更新 → 读日志
- `reverify.py` —— 复验：无弹窗、列表正常、配置未污染
- `kdeploy.py` —— 内核部署验证（切内核 → 观察 `Steam/dwmapi.dll`）
- `kcmp.py` —— 哨兵法内核 A/B 对照
- `mmcurl.py` —— 指定内核下抓真实 URL

---

## 5. UIA 纪律（违反则全部测试无效）

1. **只可用 `InvokePattern.Invoke()`**，禁止屏幕坐标
2. 每次动作前**断言 `en=True`**
3. **禁止**用 `SetWindowPos` 改尺寸（会写入 `shiki.json.window_size`，污染像素判据）
4. UIA 枚举**必须排除标题含 `Explorer` / `文件资源管理器` 的窗口**
   （曾误操作同名 Explorer 窗口，导致 `_re/` 被改名）

---

## 6. 交付物

| 项 | 值 |
|---|---|
| 文件 | `KeySteam_r59_可用.exe` |
| md5 | `a0d5da91fbfa8c72126084153c615baf` |
| 大小 | 30,885,138 B（与原版**等长**） |
| 相对原始样本 | 8 段 / 71 字节（含 r58 既有）+ 本轮 2 处 / 16 字节 |

**样本本体不入库**，见 `.gitignore`；留在工作区原地
`/mnt/d/03_Work/03_Develop/KeySteam v2.99/`。

---

## 7. 未解与后续

| # | 项 | 状态 |
|---|---|---|
| H2 | 桶名算法（`bucket_name_for_app`）依赖的额外状态 | 未解。暴力枚举 ~2352 组合全 0 命中 |
| H4 | `CONTENT_KEY_CONTEXT` 字面值 | 未解。`KSL3` 解密链已通到 ChaCha20Poly1305，卡在该常量 |
| — | 内核授权链路差异（`shiki3.dll` vs `shiki2.dll`） | 已定位机制，未深入 |
| — | `1943950.ks` 自行落盘行为 | 观察到（非选中项也入库），未深究 |
