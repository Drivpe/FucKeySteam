# ADR 0001：从「消除弹窗」转向「取得合法票据以命中缓存」

- **状态**：已接受
- **日期**：2026-09-15
- **决策轮次**：第 5 轮

## 背景

样本 `KeySteam v2.99` 启动时会出现「验证码弹窗」（`VerificationDialog`），
阻断主窗口的日常使用。第 1–4 轮的工作目标是**消除这个弹窗**，
第 5 轮转向**绕过 GUI 直接调用业务模块**。

第 5 轮的静态确证（详见 `docs/bypass-gui-entrypoints.md`）与运行期观测
（`.scratch/run-20260915-125400/`）共同确立了三组事实：

1. 弹窗由票据校验链触发，且触发点是**联网**：`#7` 实测显示弹窗在
   `host → key.steamofl.com:443` 连接建立后 **94 毫秒**出现，主窗口随即被模态禁用。
2. 票据是**签过名的密文块**，以每条票据一次性的 X25519 ECDH 封装，并有服务端轮换的
   `published_at` 参与比对。本地无伪造路径。
3. 缓存命中时，`_start_initialization` 直接进入 `_continue_initialization`
   与 `_preload_memory_images`，**不经过** `_fetch_verification_config`
   与 `_handle_verification_config_*` 两个分支。

第 3 条是转折点：它与第 1 条互为反面 —— 有连接才有弹窗，则无连接即无弹窗。
而「不弹窗」所需的，只是一张**真实有效**的票据。

## 决策

**放弃「消除弹窗」路线，转为「取得一张合法票据以命中缓存」。**

具体地：

- 不再尝试伪造、编辑、重签 `verification.cache`，也不再尝试注入或改写校验逻辑。
  这些方向与第 2 条事实正面冲突，已被证伪。
- 使用样本自身的正常链路取得票据：提交验证码 → 服务端换发 → 样本落盘缓存。
  这条链在 `_check_cached_verification` 内与 `save_verification_ticket` 同作用域，
  是样本设计中的正向路径。
- 目标状态定义为：**提交一次验证码后，后续启动命中缓存，不联网、不弹窗。**

## 被否决的备选

**备选 A：绕过 GUI，直接调用 `AuthorizationWorkflowService`。**
样本确实自带非图形入口（`--extract-authorization` → `run_authorization_extract_cli`），
且参数透传路径已确证（`_NUITKA_ONEFILE_DLL_MODE`，argv 指针直传）。
否决理由：该入口的入参 `--encrypted-ticket` 要求的是 **Steam 客户端签发的
Encrypted AppTicket**，与号商票据是两条互不相干的链。绕过 GUI **不解决票据问题**，
只是把「弹窗」换成「入参从哪来」。

**备选 B：寻找「不靠票据产出授权产物」的业务模块。**
全库检索 `test_kernel` / `require_encrypted_ticket` / `uses_ticket_authorization` 等，
**未发现任何免票分支**。测试内核（`_extract_test_kernel_ticket_payload`）的入参
明写 `require_encrypted_ticket`；`KERNEL_NONE.uses_ticket_authorization=false`
的语义是「不做运行时替换」，不是「免票产出授权」。否决理由：与实测不符。

**备选 C：持久化每日验证码本身，跨日复用。**
否决理由：验证码绑当日，服务端轮换 `published_at`，跨日复用必被拒。这不是技术障碍，
是服务端的设计意图。

## 后果

**正面**：本路线**不触碰任何密码学假设**，不需要破解 ECDH、不需要伪造签名、
不需要修改样本。所有动作都使用样本自身的公开功能，因此不受完整性自检、
运行时守卫、远程清单任何一条的威胁 —— 没有任何东西被改动。

**负面**：票据带 `expires_at`，且服务端轮换 `published_at`，因此**存在周期性成本**：
票据过期后需要重新提交验证码。这是设计上的持续成本，无法通过本地手段消除。
若用户要求「一次改造永久免验证」，那与已确证的 per-ticket ECDH 正面冲突，
属于另一个决策。

**未决**：
1. 票据的实际有效期（`expires_at` 时长）**无证据**。此前「两天缓存」的推断已被撤回
   （见 drift 表），当前视为不受控变量。
2. `published_at` 轮换是否会让一张未过期的票据失效，**未验证**。
3. 明文验证码到 `KSP1` 提交格式的编码方式，**未确证**：
   `_validate_encrypted_code` 的存在暗示存在「明文 → 加密 → KSP1」两段，
   但两段的边界未定位。

## 证据索引

| 事实 | 证据 |
| --- | --- |
| 弹窗由连接触发（94ms） | `.scratch/run-20260915-125400/findings.md` |
| 缓存命中不经过弹窗分支 | `docs/bypass-gui-entrypoints.md` §1、§6；本 ADR 背景第 3 条 |
| 票据为 per-ticket X25519 ECDH | `docs/bypass-gui-entrypoints.md` §4（`rdata.bin` `0x85bfd7`） |
| 非图形入口与 CLI 参数 | `docs/bypass-gui-entrypoints.md` §1、§2 |
| AppTicket 由 Steam 客户端签发 | `rdata.bin` `0x8a3b1f`–`0x8a3d19`（`RequestEncryptedAppTicket` 簇） |
| onefile 为 DLL 模式、argv 直传 | 本 ADR 背景；`OnefileBootstrap.c:1134`、`MainProgram.c:1811/1825/1943` |
