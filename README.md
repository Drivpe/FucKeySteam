# FucKeySteam

`KeySteam v2.99` 的逆向工程工作区（私有）。

**目标**：让样本在**不弹验证码对话框**的情况下启动并可用。

---

## 目录

| 路径 | 内容 |
|---|---|
| `docs/` | 2026-09-16 三条探针批次（注入 / 重打包 / 票据删除）的完整报告 |
| `docs/rounds/` | **2026-09-27 ~ 09-29 交付轮次**，从 r40 到 r59 —— **先读 `docs/rounds/INDEX.md`** |
| `docs/tools/` | 重打包器、PE 分析、UIA 运行时观测脚本 |
| `host/` | 外部宿主源码（C + 构建脚本） |
| `scripts/` | 运行时监控脚本 |
| `.scratch/` | 议题规格与一次性实验脚本 |

---

## 当前状态

**已达成**：交付物 `KeySteam_r59_可用.exe`（md5 `a0d5da91fbfa8c72126084153c615baf`，
30,885,138 B，与原版等长）。

- 验证弹窗消除，完整初始化，无刷屏
- 受保护动作真实执行
- 「更新选中Lua」修复（服务端库改版的等长 owner 替换）

**样本本体不入库**（见 `.gitignore`），留在工作区原地
`/mnt/d/03_Work/03_Develop/KeySteam v2.99/`。

---

## 阅读顺序建议

1. `docs/rounds/INDEX.md` —— 轮次脉络、关键教训、未解清单
2. `docs/rounds/r59_DELIVERY.md` —— 最新交付（含内核链路澄清）
3. `docs/rounds/r53_DELIVERY.md` —— 崩溃根因与测试方法论（UIA 纪律）
4. `docs/probe-index.md` —— 上游三条探针的否定结论
5. `docs/CONTEXT.md` —— 术语表（验证码 / 票据 / AppTicket 三者区别）

---

## 环境约束

测试宿主为 **Windows + WSL 混合**：样本与 Steam 在 `/mnt/d/`，
分析工具在 WSL 侧，运行时观测通过 Windows PowerShell 的 UIA 接口。

**运行时观测必须遵守 UIA 纪律**（违反则测试全部无效），详见
`docs/rounds/INDEX.md` 第 5 节。
