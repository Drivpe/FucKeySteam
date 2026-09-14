# Domain Docs

How the engineering skills should consume this project's domain documentation when exploring the workspace.

## Before exploring, read these

- **`KeySteam-弹窗-完整行为规格.md`** in the workspace at `/mnt/d/03_Work/03_Develop/KeySteam v2.99/` — canonical behavioural spec for the sample: the three dialogs, startup ordering, the gate decision chain, ticket/cache formats, the exe footer signature structure, the network contract, and an explicitly-marked list of open unknowns. **This is the glossary**, in effect.
- **`_re/dialog_facts.md`** — offset-level evidence for dialog behaviour (Q1–Q8).
- **`_re/signature_facts.md`** — the signature mechanism, including independent Ed25519 verification.
- **`KeySteam-无验证运行-落地方案.md`** — the change-path document. Its §5.4/§5.6 were corrected; §4 still carries a superseded claim (see "Known doc drift").
- **`KeySteam-无验证运行-调研.md`** — Nuitka onefile mechanism and supply-chain risk research.

There is no `CONTEXT.md` and no `docs/adr/` here. That is deliberate, not a gap: the behavioural spec already defines this project's vocabulary at a level of rigour a glossary rewrite would only dilute. Don't create `CONTEXT.md` unless a term genuinely needs defining that the spec doesn't already cover — and if you do, define it *once*, in the spec, and point at it.

## Where the docs live

They live in the **workspace**, not in this repository.

```
/mnt/d/03_Work/03_Develop/
├── KeySteam v2.99/              ← workspace: sample + analysis docs (not a git repo)
│   ├── KeySteam.exe
│   ├── KeySteam-弹窗-完整行为规格.md      ← canonical spec / glossary
│   ├── KeySteam-无验证运行-落地方案.md
│   ├── KeySteam-无验证运行-调研.md
│   ├── KeySteam-弹窗机制分析.md
│   └── _re/                     ← evidence, scripts, backups, payload copy
└── keysteam-unlock-spike/       ← this repo: docs, scripts, host source
    ├── docs/agents/
    └── .scratch/
```

## Use the glossary's vocabulary

When your output names a domain concept — in an issue title, a spec heading, a test name, a hypothesis — use the term as the behavioural spec uses it. The pairs below are the ones that get confused most often; the left column is correct.

| Use | Not | Why it matters |
| --- | --- | --- |
| 验证码弹窗 / `VerificationDialog` | 「倒卖可耻」弹窗 | 「倒卖可耻」is the *tamper warning* title. Different dialog, different trigger, different handling. Conflating them misreads the whole task. |
| 篡改警告 / `TamperWarningDialog` | 验证弹窗 | As above, inverted. |
| 闸门 / `_verification_gate_allows` | 完整性校验 | The gate *consults* integrity state; they are not the same mechanism. |
| 完整性自检 / `IntegrityService` | 签名校验 | Signature verification is one branch inside integrity checking. |
| 本地 trailer | 签名文件 | The signature is not a separate file. It is a trailer on `KeySteam.exe`. |
| 远程清单 / `version.json` | trailer | `main.dll` integrity goes through the remote manifest, *not* the local trailer. This distinction decides whether a patch trips detection. |

## Flag ADR conflicts

There are no ADRs. The equivalent obligation here is **documentation drift**, which this project has already produced once — see below.

## Known doc drift — correct it, don't inherit it

`KeySteam-无验证运行-落地方案.md` §4 (line ~96) and the handoff document's §10 (line ~163) both claim that modifying `main.dll` mismatches `body_sha256` and therefore triggers `TAMPERED`. **That claim was superseded on 2026-09-15** by the same document's own §5.4 correction, and by `_re/signature_facts.md`.

The corrected position: the local trailer covers **`KeySteam.exe` only**. `main.dll` has no trailer (its last 64 bytes are `0x00`). `main.dll`'s integrity travels the **remote manifest** branch plus a process-module scan.

When you find yourself reasoning from the superseded claim, stop and re-read `_re/signature_facts.md`. If an issue or spec touches this area, surface the drift explicitly rather than silently picking a side.
