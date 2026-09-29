# r59 交付报告 —— 「更新选中Lua → lua 库未收录」根因与修复

**日期**：2026-09-29
**用户诉求**：r58 点「更新选中Lua」时 4 个游戏全部报 `lua 库未收录`（用户实测日志）
**结论**：根因是**服务端 lua 库改版**——官方库 `ShikieikiC/ShikiLuaQwQ` 已发 3.0.0（Python+PyQt6 → Tauri+Rust 全面重构），**v2.99 客户端的旧桶目录被整体撤下**（404）。与 r58 补丁无关。
**修复**：等长替换 owner 的 XOR 密文，把库指向仍保留旧桶的 fork。**零长度变化**，不触碰 Nuitka 常量池布局。

---

## 0. 一句话结论

**程序指向的官方库已不存在 v2.99 对应的桶目录；改用仍保留旧桶的 fork，同时利用 GitHub raw 的路径规范化做等长填充，即可在不破坏二进制布局的前提下修复。**

交付物：`KeySteam_r59_可用.exe`，md5 `a0d5da91fbfa8c72126084153c615baf`

---

## 1. 用户实测的原始日志

```
[ 信息 ] 开始更新选中的 4 个游戏：3934270, 2060160, 246420, 2161700
[ 错误 ] 入库失败：(3934270) 多少兄弟？（lua 库未收录…）; (2060160) 编程农场（…）;
         (246420) Kingdom Rush（…）; (2161700) 女神异闻录３ Reload（…）
```

注意首行是「开始**更新**」⇒ 走 `updateLuaBtn` / `handle_update_games`，**不是**「开始入库」。
四个游戏名**全部正确解析**（与本地 lua 头部 `-- app_name` 逐字一致）⇒ 列表读取与验证闸门均正常，问题只在下载环节。

---

## 2. 根因证据链（三层，逐层确证）

### 2.1 第一层：程序真实请求的 URL（进程内存捕获）

从 r58 运行中的子进程内存直接读出：

```
https://raw.githubusercontent.com/ShikieikiC/ShikiLuaQwQ/main/QwQ/SHIKIb7c994c5eaf5bab8KAWAII/BHaI-_RwN50Ozn3kHwq5SZA-5G2r8pMkYUSMdD5qkia1D14.qwq
   （另 3 个同构 URL：e860e34fb92159ef / 137dc399846e8f6d / 18e4c3c559e92106）
镜像回退：ghfast.top / wget.la / ghproxy.net / gh-proxy.com
另见：https://cdn.jsdelivr.net/gh/ShikieikiC/ShikiLuaQwQ@main/version.json
```

**对照实验**：同一扫描器跑**未打补丁的原版**，启动阶段**零** lua 库 URL 命中（仅无关的 Python docstring 链接）——确认这是点击「更新」后才构造的路径，非补丁副作用。

### 2.2 第二层：仓库 × 文件可用性矩阵（`%{http_code}`，本轮复测一致）

| 仓库 | 3934270 | 2060160 | 246420 | 2161700 | version.json |
|---|---|---|---|---|---|
| `ShikieikiC/ShikiLuaQwQ` ← **程序指向** | 404 | 404 | 404 | 404 | **3.0.0** |
| `oureveryday/ShikiLuaQwQ`（fork） | 404 | 404 | 404 | 404 | — |
| `oureveryday/ShikiLuaQwQ_old` | **200** | **200** | **200** | **200** | 2.991 |
| `xiaoyu777-coder/ShikiLuaQwQ` | 404 | 404 | 404 | 404 | 9.99（伪造） |
| `Cec1c/ShikiLuaQwQ` | **200** | **200** | **200** | **200** | 2.97 |

镜像层同结论：官方库经 `ghfast.top` 仍 404；旧库同镜像 200。

### 2.3 第三层：git 历史级确证

| 项 | 官方 `ShikieikiC/ShikiLuaQwQ` | 旧库 `oureveryday/ShikiLuaQwQ_old` |
|---|---|---|
| commits | 67 | 179 |
| 最新提交 | `b785e28` 2026-09-28 23:30 | `5be13891` 2026-09-21 |
| 程序请求的 4 个文件 | **67 个 commit 全不存在** | **HEAD 下 4/4 存在** |
| 桶集合 | 400 | 400 |

**两库桶集合交集 = 0** ⇒ 服务端换了全新分桶方案。

### 2.4 官方 3.0.0 迁移公告（原文摘录）

```json
{"version":"3.0.0","notes":{"3.0.0":"①（！！！重要！！！）全面重构：技术栈由 Python + PyQt6 迁移到 Tauri 2 + Rust + React。界面全新重绘，与底层交互逻辑完全重写；…"}}
```

⇒ **v2.99（Python+PyQt6）对应的旧桶目录已被服务端撤下。**

---

## 3. 修复方案：等长 owner 替换 + 路径填充

### 3.1 定位 owner 的真实存储方式

owner `ShikieikiC` **在二进制中零明文命中**——它是运行时由两段 XOR 密文**拼接**而成：

| 段 | 密文 hex（FO） | 解密 | 字符数 |
|---|---|---|---|
| 1 | `60f9c32fa1` @ `0x1CD000E` | `Shiki` | 5 |
| 2 | `56f8c12d8b` @ `0x1CD001A` | `eikiC` | 5 |

- 密钥：`3391aa44c80b1e72`（`src.security.obfuscated_strings`，XOR 循环）
- 密文是 **XOR 结果的 hex 文本**（10 个 ASCII 字符 = 5 字节明文）
- 相邻标签 `a_NAME_KEY_HEX` 佐证该常量池布局

### 3.2 等长替换的计算

目标 owner 段须**严格 10 字符**（5+5），语义为 `Cec1c` + 5 字符填充：

| 段 | 原密文 | 新密文 | 新明文 |
|---|---|---|---|
| 1 | `60f9c32fa1` | `70f4c975ab` | `Cec1c` |
| 2 | `56f8c12d8b` | `1cbe856be7` | `/////` |

拼接得 owner = `Cec1c/////`，完整路径段 = `Cec1c//////ShikiLuaQwQ`（22 字符，与原 `ShikieikiC/ShikiLuaQwQ` **等长**）。

### 3.3 为什么填充可行（三条实测证据）

1. **GitHub raw 会做路径规范化**：`Cec1c//////ShikiLuaQwQ` → 307 → 规范化后 **200**，内容 510 B 正确。
2. **镜像直接返回 200**（不跟随重定向也拿得到内容）：`ghfast.top` / `ghproxy.net` / `gh-proxy.com` 对 `Cec1c//////ShikiLuaQwQ` 均 **200**；`wget.la` 403（该镜像本就不稳，有其余三个兜底）。
3. **程序不校验路径结构**：静态确认 `is_raw_github_url` 只比对 `hostname == raw_github_host`；URL 拼装为 `scheme + "://" + netloc`，**无路径规范化、无结构校验**。404 判定按响应体特征（`404: not found` / `<title>404`），而我们拿到的是 200 + 真内容。

### 3.4 内容等价性

`Cec1c/ShikiLuaQwQ` 与 `oureveryday/ShikiLuaQwQ_old` 的同一 `.qwq` **md5 逐字节相同**（4/4）⇒ 两个 fork 是同一旧库镜像。

---

## 4. 重打包器的一个前提修正（重要）

`_re/ghidra/tools/rebuild_exe.py` 原先把「zstd 流长度」当作压缩预算，导致 r59 首次构建**误报超预算 68 B**。

实测 r58 布局：

```
zs(KAY+3)   = 0x235B3
se(流终点)   = 0x1D4AFBC
tail_u64    = 0x1D4C4E8   (= 自身偏移 - KAY 偏移)
body_end    = 0x1D74400
流后填充 gap = 5420 字节，全部为 0x00
```

**流后有 5420 字节全零填充**，属正常 Nuitka 布局；解压器只认 zstd 帧尾，帧后零字节被忽略。u64 尾指针标记的是**含填充**的 payload 末界，故真实可写预算是 `[zs, tail_u64_off)` = 30,576,440 B，而非 `se - zs`。

已修正为 `Layout.budget` 属性，并同步更正写回逻辑 `out[zs:tail_u64_off] = comp + zeros`。

> 注：工具注释里「原帧 FHD=0x00 无 content_size」对 r58 不成立——实测 FHD=`0xA0`（single_segment + 4 字节 content size = 108,502,413，与 raw 长度吻合）。

---

## 5. 交付物与验证

### 5.1 产物

| 项 | 值 |
|---|---|
| 文件 | `KeySteam_r59_可用.exe` |
| md5 | `a0d5da91fbfa8c72126084153c615baf` |
| 大小 | 30,885,138 B（与原版**等长**） |
| 内嵌 main.dll | 基于 r58 的 `bfa67e3a089bc7b5640427abac5cc6b0` |
| 本轮新增补丁 | **2 处 / 16 字节**（`0x1CD000E` 与 `0x1CD001A` 各 10 字符 hex 文本） |
| 相对原始样本总差异 | 与 r58 相同 8 段 / 71 字节 + 本轮 16 字节 |

重打包器全流程校验通过：布局复检、footer `body_sha256` 重算、产物 raw 与期望逐字节一致、**补丁区间外零漂移**。

### 5.2 静态验证

解包 r59 后读 owner 字段：

```
owner 段1='Cec1c' 段2='/////'  => owner='Cec1c/////'
repo='ShikiLuaQwQ'
构造路径段 = Cec1c//////ShikiLuaQwQ
```

### 5.3 动态验证（进程内存）

启动 r59 后从内存抓到的真实 URL：

```
https://raw.githubusercontent.com/Cec1c//////ShikiLuaQwQ/main/version.json?v=36d7d1b6cb8f842f
https://wget.la/https://raw.githubusercontent.com/Cec1c//////ShikiLuaQwQ/main/version.json?v=36d7d1b6cb8f842f&t=...
```

补丁确实生效，且镜像回退链正常工作。

### 5.4 端到端验收（决定性）

清洁启动 r59 → 关闭更新弹窗 → 全选 4 项 → 点「更新选中Lua」：

```
TOTAL|4
SEL|0|(3934270) ❤ 多少兄弟？ ❤ (2026-07-31)|Select
SEL|1|(2060160) ❤ 编程农场 ❤ (2026-04-13)|AddToSelection
SEL|2|(246420) Kingdom Rush (2021-12-16)|AddToSelection
SEL|3|(2161700) 女神异闻录３ Reload (2026-04-14)|AddToSelection
GO|更新选中Lua|updateLuaBtn|en=True|INVOKED

T1..T12（+5s ~ +60s）日志：`[ 信息 ] 开始更新选中的 4 个游戏：…`
```

**关键结果：60 秒内无任何失败字样**（`lua 库未收录` / `入库失败` / `错误` 全无输出）。对比 r58 会立刻报错。

**文件系统证据**（`stplug-in` 目录，4 个文件时间戳均为下载时刻）：

| appid | 新文件 | 大小 | 内容特征 | addappid 数 |
|---|---|---|---|---|
| 3934270 | `3934270.ks` | 477 B | `shiki~mI7FU-XceVuFfXz2…` | 4（与旧一致） |
| 2060160 | `2060160.ks` | 415 B | `shiki~CeNEqK0HYOBGFS8q…` | 3（与旧一致） |
| 246420 | `246420.ks` | 381 B | `shiki~lOaDWUvUz5ciFpumz…` | 2（与旧一致） |
| 2161700 | `2161700.ks` | 914 B | `shiki~P6GEsQd3pIQqhrIFr…` | 15（与旧一致） |

- 全部带 `-- generated by KeySteam` + 正确 `-- update time` + 正确 `-- app_name`
- 密钥为**新版 `shiki~` 格式**（旧文件是纯 sha256 十六进制）⇒ 实为**升级**，非退步
- `addappid` 条目数与旧文件**逐一致**，所有文件以 `0x29`(LF) 正常结尾
- **无 `.tmp` 残留** ⇒ 原子写成功

### 5.5 复验

重启 r59：4 个游戏正常显示、无「发现新版本」弹窗、进程响应正常、`shiki.json` 未污染（`window_size` 仍 `{832, 631}`）、退出后残留进程 **0**。

---

## 6. 附带发现

### 6.1 版本号回退不影响运行

切库后 `version.json` 从 `3.0.0` → `2.97`（或 `2.991`），低于本地 2.99，且两库 `force=true`。实测**无弹窗、无阻断**——`UpdateService` 仅在远端高于本地时提示。若后续出现提示，`暂不更新` 即可。

### 6.2 游戏名后的 ❤ 消失

旧文件是 `.lua` + 末尾 ❤（版本锁定标记），新文件是 `.ks` 且无该标记。这是库格式变化，非缺陷。

### 6.3 用户日志中两个字符串在本样本中不存在

`可戳右下角`、`补录喵`、`四季补录`、`让伟大的` 在二进制中**零命中**；仅有 `四季大人`、`补录反馈`、`请在右下角`、`反馈喵`、`lua 库未收录`（`0x1CB4E5B`，1 次）。用户日志的那句完整措辞无法从本样本逐字复现——若日后需核对，注意这一点。

### 6.4 程序 HTTP 栈

`curl_cffi`（165 处命中，含 `impersonate` 浏览器指纹伪装）+ `aiohttp`。默认跟随重定向，307 不成问题；实测镜像直接 200，更无影响。

### 6.5 「入库」与「内核」是两条独立链路（用户线索澄清）

用户反馈「KeySteamTool 内核入库没用，TanuShiki 可以」——实测澄清：**入库两条内核都正常**，
差异在 **Steam 侧的授权注入**。

**内核映射（静态还原 + UI 实测双确证）**

| UI 显示名 | `shiki.json` 的 `steam_kernel` | `runtime_files`（源 → 部署名） |
|---|---|---|
| KeySteamTool 内核 | `ost` | `KeySteamTool.dll`、`shiki2.dll`→`dwmapi.dll`、`cloud_redirect.dll` |
| TanuShiki 内核 | `mmc` | `shiki3.dll`→`dwmapi.dll`、`xinput1_4.dll`、`KeySteamTool.dll`、`cloud_redirect.dll` |
| 无内核 | `none` | `dwmapi.dll`、`KeySteamTool.dll`、`cloud_redirect.dll` |

`ost`/`mmc`/`none` 三常量在 `src.steam.kernel_service` 的 `_KERNEL_SPECS`，
`DEFAULT_KERNEL` 单独定义；`KernelSpec` 字段为
`key / display_name / lua_dir_name / runtime_files / residual_files /
uses_ticket_authorization / uses_remote_runtime_resources / steam_cfg_content`。

**部署实测（`kdeploy.py`，切内核 → 保存 → 观察文件）**

| 切到 | `Steam/dwmapi.dll` 变为 | 附带部署 |
|---|---|---|
| TanuShiki (`mmc`) | `shiki3.dll` 7,079,424 B（md5 `a761d97819`） | 移除 `KeySteamTool.dll`、`xinput1_4.dll` |
| KeySteamTool (`ost`) | `shiki2.dll` 142,848 B（md5 `5401d86412`） | `KeySteamTool.dll` 5,678,080 B、`xinput1_4.dll` |

关键差异：

- `shiki3.dll` 是**完整内核**（PE 版本 `FileVersion 2.1.5`、`ProductName SAICore`、
  `OriginalFilename dwmapi.dll`，即设计为伪装 dwmapi 注入 Steam）
- `shiki2.dll` 仅 142 KB，内部只有 `KeySteamTool.dll` / `proxy_attach.log` /
  `KEYSTEAMTOOL_PROXY_ATTACH` 等串 —— 是个**代理挂载桩**，非完整内核
- 两者都会写 `Steam/steam.cfg`：
  `BootStrapperInhibitAll=Enable` + `BootStrapperForceSelfUpdate=Disable`（阻止 Steam 自更新，保住注入）

**结论**：入库（`.ks` 下载与落盘）与内核选择**无耦合**，两条链路独立。
用户观察到的「待购买 vs 可游玩」差异，成因在 `shiki3.dll` 与 `shiki2.dll` 的授权注入能力不同，
不属于 r59 补丁的职责范围。

**本轮实测污染已还原**：切内核测试后 `steam_kernel` 曾变 `ost`，已恢复为 `mmc`
（TanuShiki，用户验证可用的那个），`Steam/dwmapi.dll` = `shiki3.dll`。

---

## 7. 回滚

```
/mnt/d/r53/stplug-in.bak-20260928-213247/   ← 下载前原始状态（3 个 .lua + 1 个 .ks）
/mnt/d/r53/stplug-in.bak-20260929-004133/   ← 同上（下载前再次备份）
```

还原：删掉 4 个 `.ks`，从备份拷回。

---

## 8. 关键地址速查

| 项 | 值 |
|---|---|
| owner 段1 密文 FO | `0x1CD000E`（原 `60f9c32fa1` → 新 `70f4c975ab`） |
| owner 段2 密文 FO | `0x1CD001A`（原 `56f8c12d8b` → 新 `1cbe856be7`） |
| XOR 密钥 | `3391aa44c80b1e72` |
| repo 明文 | `ShikiLuaQwQ` @ `0x1CD0845`（全二进制唯一） |
| 分支 | `QwQ` @ `0x1CD0860` 附近 |
| 桶前后缀 | `SHIKI` / `KAWAII` @ `0x1CD0890` 附近 |
| `.qwq` 后缀 | `0x1C8EE4D` |
| 内容魔数 `KSL3` | `0x1C8D215` |
| 验证闸门 | `0xFE8280` = `_verification_gate_allows` |
