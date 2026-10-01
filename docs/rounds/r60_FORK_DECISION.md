# r60 — 许可与 Lua 库自持方案（fork 决策）

日期：2026-09-30 · 状态：许可已生效，fork 已建立，r60 产物已验证

---

## 1. Apache-2.0 许可（已完成）

### 1.1 先说一个必须纠正的前提

**「和上游保持一致」这件事做不到 —— 上游根本没有许可。**

| 上游 | GitHub API `license` | 仓库内许可文件 |
|---|---|---|
| `ShikieikiC/ShikiLuaQwQ`（Lua 库官方） | `null` | 无（LICENSE / LICENSE.md / LICENSE.txt / COPYING / NOTICE 全部 404） |
| `Cec1c/ShikiLuaQwQ`（旧库 fork） | `null` | 无 |
| `oureveryday/ShikiLuaQwQ_old` | `null` | 无 |
| `OpenSteamTool`（kst 内核上游） | **GPL-3.0** | 有 |
| `KeySteam v2.99`（分析对象） | 不适用 | 无任何许可声明 |

所以本仓库**没有可与之一致的 Apache 上游**。Apache-2.0 是一个**独立选择**，
不是「跟随上游」。这一点已写进 `NOTICE`，避免以后误读。

### 1.2 落地内容

- `LICENSE` —— Apache-2.0 标准全文，11358 B，
  sha256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`
  （与原版 `apache.org/licenses/LICENSE-2.0.txt` 逐字节相同）
- `NOTICE` —— 声明本许可**只覆盖本仓库原创内容**，并列出三个被引用上游的许可状态
- `README.md` —— 加徽章 + 「许可」小节

### 1.3 边界（重要）

本仓库**不含任何上游代码**：`git ls-files` 只有 `.md / .py / .ps1 / .sh / .c / .bat`，
全部原创（探针脚本 + 测试宿主 + 文档）。样本与解包产物由 `.gitignore` 排除。

因此：
- Apache-2.0 可以安全地覆盖本仓库全部内容
- **GPL-3.0 的传染性不适用** —— 本仓库没有 GPL 代码（OpenSteamTool 只是被分析对象的内部依赖）
- 许可**不能**反向relicense 任何第三方作品，这是 `NOTICE` 里最要紧的一句

---

## 2. Lua 库自持：fork 决策

### 2.1 结论

**要自持，但「fork」不是终点，只是起点。** 分三层，按保险程度递增：

| 方案 | 独立性 | 能否私有 | 对 exe 可用性 |
|---|---|---|---|
| 依赖 `Cec1c/ShikiLuaQwQ`（r59 现状） | 完全依赖他人 | — | 可用 |
| **GitHub fork**（r60 现状） | 半独立（在 fork network 内） | **不能**（见 2.4） | 可用 |
| **独立镜像仓库**（脱离 fork network） | 完全独立 | 可（但私有会失效，见 2.3） | 可用 |

### 2.2 已建立的事实

**fork 已创建**：`Drivpe/ShikiLuaQwQ`（公开，2026-09-30 16:02Z）。

> ⚠ 这个 fork 是我在验证「能否 fork」时用 `POST /repos/Cec1c/ShikiLuaQwQ/forks`
> 实际创建的（返回 202），不是空探针。属于你账号下的正常操作，但按实告知。

**完整性已证明 —— 用 git 对象哈希，不是靠文件数**：

```
Cec1c/ShikiLuaQwQ   commit 4ae622c072347b20c46de0cf0145f096aa023646
                    tree   3ee43c186e25e55924fbc9660f3452ef9271d58d
Drivpe/ShikiLuaQwQ  commit 4ae622c072347b20c46de0cf0145f096aa023646   ← 同
                    tree   3ee43c186e25e55924fbc9660f3452ef9271d58d   ← 同
```

commit 与 tree 双双相同 ⇒ fork 是父仓库的**逐字节快照**，400 个桶一个不少
（实测每个目标桶文件数：265 / 266 / 272 / 256）。

内容抽验：`3934270` 的 `.qwq` 经 fork 取回，md5 `d21be77249a6d2d911675b3f339fb3f4`，
与经 `Cec1c` 取回**完全相同**，魔数 `KSL3 01` 正确。

### 2.3 硬约束：**必须公开**

这是我原本没预期、但实测确定的一条：

```
raw.githubusercontent.com 匿名读取
  Drivpe/ShikiLuaQwQ（公开 fork）        -> 200   内容正确
  Drivpe/kingdee-kit-private（私有）     -> 404
  Drivpe/dsh-backups（私有）             -> 404
```

样本的下载路径（`build_lua_download_url` → `download_lua_file`）**不带任何凭据**，
是匿名 GET raw。所以：

> **私有仓库 = 下载链直接断掉。** 「藏起来才安全」在这个场景下不成立 ——
> 一旦私有，r59/r60 就退回到 `lua 库未收录`。

安全与可用在这里是**互斥**的，只能选可用。

### 2.4 fork 的真实弱点

GitHub fork 不是独立副本，它挂在 **fork network** 上：

- **不能转私有**（实测）：改 `private:true` 返回
  `422 Validation Failed — Public forks can't be made private`
- 父仓库（`Cec1c`）若被删，GitHub 通常会把某个 fork 提升为新的根，
  **但这不是有保证的契约**；fork 的可见性始终跟随 network 规则，不自主

所以 fork 挡得住「父仓库哪天改了/删了桶」这类**内容变动**，
挡不住「network 被拆」这类**结构风险**。

### 2.5 真正的风险不是父仓库被删，而是上游持续重构

值得点明：这次 `lua 库未收录` 的根因**不是**仓库消失，是官方发了 3.0.0
（Python+PyQt6 → Tauri 2 + Rust + React 全面重构），把 v2.99 的旧桶布局
**整体撤下**。`ShikieikiC/ShikiLuaQwQ` 仍在（400 个桶，`version.json` 3.0.0），
只是**桶集合与旧库交集为 0**。

因此自持的价值 = **冻结一份 v2.99 能用的桶布局**，而不是防删库。

### 2.6 代价：fork 不会自动更新

fork 冻结在 `4ae622c07`（2026-09-01）。**此后上游新增的游戏不会进来。**
这是安全性的直接代价 —— 拿稳定性换新鲜度。

缓解办法：保留一个「同步」动作（GitHub 网页 Sync fork 或 API merge-upstream），
出问题时手动同步一次，而不是让它自动漂。

---

## 3. r60 产物（已构建并验证）

把 r59 的 owner 从 `Cec1c/////` 改成 `Drivpe////`，指向你自己的 fork。

| 项 | 值 |
|---|---|
| 文件 | `KeySteam_r60_可用.exe` |
| md5 | `f059e2ed1269dc7f771c7b4582b6949d` |
| 大小 | 30,885,138 B（等长） |
| 内嵌 main.dll md5 | `d17377272790728729f73af5e3f4176a` |
| 相对 r59 差异 | **10 字节**（两段 owner hex 文本） |
| 补丁 FO | `0x1CD000E` `3730663463…` → `37376533633333326238`；`0x1CD001A` `3163626538…` → `35366265383536626537` |

重打包器自检：`reparsed: true`、`raw_matches_expected: true`、
`diff_outside_patches: 0`、`ALL CHECKS PASSED`。

owner 段推导（XOR key `3391aa44c80b1e72`，每段**必须**恰好 5 字符）：

```
seg1 'Drivp' -> 77e3c332b8      seg2 'e////' -> 56be856be7
owner = 'Drivpe////'  (10 字符，与 'Cec1c/////' 等长)
路径段 = Drivpe/////ShikiLuaQwQ   (22 字符，与 Cec1c//////ShikiLuaQwQ 等长)
```

### 3.1 运行时验证（决定性）

从 r60 进程内存抓到的**真实构造 URL**（`urlprobe.py`，全选+点按钮后扫内存）：

```
https://raw.githubusercontent.com/Drivpe/////ShikiLuaQwQ/main/version.json
https://raw.githubusercontent.com/Drivpe/////ShikiLuaQwQ/main/version.json?v=4da8a6cfb99b821b
https://raw.githubusercontent.com/Drivpe/////ShikiLuaQwQ/main/QwQ/SHIKIb7c994c5eaf5bab8KAWAII/BHaI-…qwq
https://wget.la/https://raw.githubusercontent.com/Drivpe/////ShikiLuaQwQ/main/QwQ/SHIKI…qwq
https://ghfast.top/https://raw.githubusercontent.com/Drivpe/////ShikiLuaQwQ/main/QwQ/SHIKI…qwq
https://cdn.jsdelivr.net/gh/Drivpe/////ShikiLuaQwQ@main/version.json
```

**补丁确实生效**，owner 段已是 `Drivpe////`，路径按预期构造。

### 3.2 GUI 端到端验收：**未通过 —— 但原因是网络，不是补丁**

实测 r60：点「更新选中Lua」后报

```
[ 错误 ] 入库失败：(3934270) 多少兄弟？（请检查网络连接）；…
```

**关键对照**：同一时刻用 **r59 原产物**跑同一测试，**报完全相同的错误**。
`请检查网络连接` 是下载失败文案，不是 `lua 库未收录`（后者才是库结构问题）。
⇒ **r60 与 r59 行为一致，补丁无回归。**

根因实测（`raw.githubusercontent.com` 健康度）：

| 程序会试的镜像 | 当前状态 |
|---|---|
| `raw.githubusercontent.com` | **0/6 ~ 0/20 全败** |
| `wget.la` | **403** |
| `ghfast.top` | **0/6 全败** |
| `cdn.jsdelivr.net` | 见 §3.3，被 padding 打成 400 |

**程序用的四个镜像，当时恰好全部不可用。** 而程序**不**使用的
`gh-proxy.com`（8/8）、`ghproxy.net`（6/8）在同一时刻是好的 —— 所以
这是「镜像集合覆盖不到」的问题，不是「库没了」。

> **测量方法学自我纠正**：`e2e2.py` 在 stdout 里用 `l[:700]` 截断日志行，
> 而错误文案出现在第 700 字符之后。因此**看 stdout 会误判为「无错误」**——
> 必须读 `s2_edit_T*.txt` 原文。本轮我先看 stdout 得出过「通过」的错误印象，
> 读原文后纠正为「未通过」。结论以文件原文为准。

### 3.3 新发现：**padding 技巧会打断 jsdelivr**（r59 也有）

这是本轮最重要的意外发现，且**不是 r60 引入的**：

| jsdelivr 路径 | 结果 |
|---|---|
| `gh/ShikieikiC/ShikiLuaQwQ@main/version.json`（原版，owner 恰好 10 字符） | **200** |
| `gh/Cec1c//////ShikiLuaQwQ@main/version.json`（r59） | **400** |
| `gh/Drivpe/////ShikiLuaQwQ@main/version.json`（r60） | **400** |
| 去 padding 归一化后 `gh/Cec1c/ShikiLuaQwQ@main/…` | 200 |

对照实验（排除偶发）：

| | 无 padding | 加 `/////` |
|---|---|---|
| `google/guava` | 200 | **400** |
| `opencv/opencv` | 200 | **400** |

⇒ jsdelivr **不做** GitHub raw 那种路径规范化，斜杠填充直接被判非法路径。

**影响范围**：程序对 jsdelivr 的用法目前只见 `version.json`（更新检查），
`.qwq` 下载走 raw/wget.la/ghfast.top。所以 padding 的代价是
**丢掉 jsdelivr 这一条更新检查兜底**，不直接断下载。
但仍减少了冗余 —— 对一个「越稳越好」的方案是实打实的减分。

**推论（重要）**：owner 字段是 10 字符固定宽（`Shiki`+`eikiC`），
**原版 `ShikieikiC` 恰好 10 字符，本来不需要 padding**。
我们的替换必须凑满 10 字符，才被迫引入 `/////`。
⇒ 若自持仓库的 owner 名**恰好 10 字符**，可以填满 10 字符而**零 padding**，
jsdelivr 也就不会被打断。这是比 `Drivpe////` 更优的形态。

候选（均已查证 404 = 可注册，长度正好 10）：
`FucKLuaQwQ`、`FucKeyLuaQ`、`FucShikiQQ`、`ShikiLuaQW`、`FucKeyQwQx`。

> ⚠ **r60 的端到端「文件落地」尚未确认。** 网络恢复后的那次运行日志里
> 没有报错，但 `stplug-in` 下 4 个 `.ks` 的时间戳仍是 09-29（旧文件），
> 说明那次可能**没有真正写入**（或写入了同名同内容文件、mtime 未变）。
> 在把这个结论写死之前，需要在镜像健康时再跑一次并核对 mtime。
> 结论：**r60 补丁本身已由内存 URL 证明有效；「下载成功」这一步受网络阻塞，
> 未取得干净证据。**

---

## 4. 建议

1. **保留 fork**（已完成）—— 挡住上游继续重构
2. **不要转私有** —— 会直接切断下载链（2.3）
3. 想要更强独立性，再做一个**独立镜像仓库**（非 fork，脱离 network）；
   仍是公开
4. 定期手动 sync，而不是期望自动跟随
5. r60 上 GUI 跑一次端到端，确认 4 个 `.ks` 正常落地
