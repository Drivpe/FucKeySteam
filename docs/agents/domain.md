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

There are no ADRs. The equivalent obligation here is **documentation drift**, which this project has produced repeatedly. The drift register below is the mechanism — add to it whenever you correct a claim, rather than relying on the next reader's memory.

### Drift register

| Claim | Where it lived | Status | Correct position |
| --- | --- | --- | --- |
| Modifying `main.dll` mismatches `body_sha256` and trips `TAMPERED` | `KeySteam-无验证运行-落地方案.md` §4 (line ~96); handoff §10 (line ~163) | **Superseded 2026-09-15** | The local trailer covers **`KeySteam.exe` only**. `main.dll` has no trailer (last 64 bytes are `0x00`); its integrity travels the remote-manifest branch plus a process-module scan. See `_re/signature_facts.md`. |
| The `.py`-suffix check that disables the integrity self-check is part of Nuitka's C runtime | `host/host.c` comments (two sites); implicit in `docs/run-plan.md`'s observation table | **Corrected 2026-09-15** | Nuitka's runtime has **no** suffix branch — `grep -rn 'pyw\|\.py"'` across `MainProgram.c`, `OnefileBootstrap.c`, `HelpersFilesystemPaths.c` returns zero matches. The check lives in the **sample's own compiled Python code** (constant tuple `P\x02u.py\0u.pyw\0`, VA `0x01cd04d0`). `docs/host-contract.md:143-151` already recorded this correctly. |
| The current verification ticket is expired ("two-day-old cache cannot still be fresh") | `#3` comment `5672996712` | **Retracted 23 seconds later by `#4` comment `5672999531`** — both comments stand, the issue bodies were corrected 2026-09-15 | Ticket validity is **unknown**, not known-expired. `expires_at` duration is not evidenced; "daily rotation" refers to the server-side code version (`published_at`), which is a different thing. Treat it as an uncontrolled variable. |
| `[host] run_code returned N` proves the call completed | `docs/run-plan.md` observation table; handoff §3.3 | **Corrected 2026-09-15** | Unreachable on the normal path. `run_code` → `Nuitka_Main` → `EXECUTE_MAIN_MODULE` → `Py_Exit` (`MainProgram.c:2355`) terminates the process; the line prints only on *abnormal* exit. |
| Host exit code `5` = environment variable setting failure | handoff §3.3 | **Corrected 2026-09-15** | No `return 5` exists in `host.c`. `LoadLibraryExW` failure yields **`3`**; the handoff omitted that row. See `host/README.md`. |
| The host runs against an isolated environment | `AGENTS.md`; `docs/run-plan.md` checklist | **Corrected 2026-09-15** | This machine already runs this class of tool (`KeySteamTool.dll`, `cloud_redirect.dll`, `cloud_redirect.log` written today, modified `steam.exe`). The checklist now records measured state instead. See `AGENTS.md`. |
| `gh issue view <n> --comments` is how you read an issue | `docs/agents/issue-tracker.md` | **Corrected 2026-09-15** | Fails outright on gh 2.46.0 (GraphQL requests the deprecated `repository.issue.projectCards`). Use the REST API via `gh api`; the doc now shows the working commands. |
| The `.gitignore` is "whitelist-shaped", so a sample can never be staged by accident | `docs/agents/issue-tracker.md` | **Corrected 2026-09-15** | It is deny-list shaped — an enumeration of excluded patterns. The claim's consequence was real: sample-side plugin scripts (`*.lua`, `*.ks`) were not on the list, so `git add -A` would have committed them. Patterns added; the rule is now "check `git status` before `git add -A`". |
| Absence of the `倒卖可耻` window is positive evidence that the integrity path took the skip branch | `#3` run report comment `5673943406`; still implied by `docs/run-plan.md`'s observation table | **Corrected 2026-09-15** by `#3` comment `5674141885` and `docs/integrity-runtime-observability.md` | The window needs **three** conditions together: integrity did *not* take the source-run branch, **and** local Ed25519 verification failed, **and** the remote manifest check also judged TAMPERED. So a missing window cannot distinguish (i) the argv approach worked from (ii) the signature happened to verify from (iii) the remote check landed in its own `unreachable`/`invalid` branch. The observation is real but its attribution is weaker than the original wording claimed. |
| `_integrity_runtime_supported()`'s return value can be observed from outside the process | Implied by `#3`'s corrected acceptance criterion ("whether the integrity self-check entered the source-run branch") | **Disproved 2026-09-15** — see `docs/integrity-runtime-observability.md` | It is a pure predicate: no side effects, no logging, no I/O. Five candidate channels (disk writes, module set, network, UI gating, process guarding) were each checked against the constant tables and **all five are decoupled**. The branch is not externally observable; do not design an observation that assumes otherwise. |
| Abbreviated line citations (`host.c:438`) are safe to quote forward | This repo, repeatedly — `host/README.md` return-code table (stale twice), `docs/run-plan.md`, `scripts/README.md` | **Corrected 2026-09-15** | `host.c` is rewritten each round, so every bare line number went stale (eight at once on the last sweep). Cite a **re-derivation command** (`grep -n 'return status' host/host.c`) instead of a number, or re-verify the number in the same change that touches the file. |
| `RuntimeGuard._frozen_runtime_supported` is a predicate whose value can be inferred by observing whether the watchdog subprocess starts | `#7` body, "问题二 / 候选 A"; `docs/integrity-runtime-observability.md` §5.3 (old) | **Disproved 2026-09-15** | It is an **instance attribute**, not a method: absent from `RuntimeGuard`'s 14 qualified method names, and appears **exactly once** in the whole `.rdata` section (the assignment, with no read site). `_spawn_watchdog`'s own docstring (`VA 0x181cd385f`) states an **unconditional** semantic: "创建监听管道并启动看门狗子进程，失败时清理资源。" So `start()` cannot early-return on it. Candidate B falls with A. See §3.2/§3.3/§5.3 of the observability doc. |
| A missing watchdog process would prove the `.py`-suffix branch was taken | `#7` body, "问题二 / 候选 A" | **Disproved 2026-09-15** | Two independent reasons. (1) The mechanism it depends on (above) does not exist. (2) Even if it did, the sample defines its own **"降级为仅自检模式"** state, entered by `_watchdog_failed` / `_restart_watchdog` when watchdog spawn fails or restarts are exhausted — so an absent watchdog has a second, unrelated cause. A negative observation with two live explanations attributes nothing. |
| VA citations in `docs/integrity-runtime-observability.md` are internally consistent | That doc, header block | **Corrected 2026-09-15** | The header said `VA = rdata.bin 偏移 + 0x143d000`, **omitting ImageBase**, so the early `0x1cd....`-style values are RVAs, not VAs; and the `.rdata`-internal `0x8...`-style values are a third, unexplained scale. The header now lists all three conversions and warns against mixing them. Re-derive from the binary rather than quoting a number. |
| The `runtime_guard` constant block contains no readable semantics | Implied by the reliance on "constant-table adjacency" for candidate A | **Corrected 2026-09-15** | The block carries **unobfuscated Chinese docstrings**, including `_spawn_watchdog`'s ("创建监听管道并启动看门狗子进程，失败时清理资源。") and the class docstring describing the heartbeat/watchdog/kill chain. Eight are now tabulated at §3.3 with re-derived VAs. Reading docstrings is faster and stronger than disassembling, and would have settled candidate A before it was written into a ticket. |
| A `timeout`-wrapped call is enough to bound a host run | Implicit in the 2026-09-15 switch-verification commands (four runs, all `rc=0`) | **Corrected 2026-09-15** | `timeout` kills only the PowerShell caller; **`host.exe` survives**. Four orphaned hosts ran for 40+ minutes, each holding a `KeySteam v2.99` window. Damage this time was zero (they sat at the modal dialog, so no cleanup fired) but that was luck. Check `Get-Process host` before every run and kill leftovers. This is the same root cause as the "host must be run by hand" rule: an outer timeout cannot kill a process that owns a modal window. |
| `src.utils.resources` writes resource files to disk | Reading the module's I/O table without checking module boundaries | **Corrected 2026-09-15** | Strict re-check by module boundary (`0x181cf66d4`–`0x181cf6e61`) shows `write_text`/`write_bytes`/`mkdir`/`unlink` **all zero-hit** inside it. The I/O symbols I first attributed to it belong to an **adjacent** module. It only assembles an in-memory candidate list. Same error shape as `#7` candidate A — adjacency read as ownership. |
| `NUITKA_ONEFILE_DIRECTORY` is a consumption point for this sample | `#7` body, "问题二 / 候选三"; the `#4` "third evidence" idea | **Corrected 2026-09-15** | The string exists in `main.dll` (1 hit) but sits in the **Nuitka C runtime pool** (`0x181d1b910`, `.data`) next to `compiled_module` / `__nuitka_binary_dir` — not sample Python code. The variable the sample actually reads is **`NUITKA_ONEFILE_TEMP`**, consumed by `candidate_resource_dirs` in `src.utils.resources`. So the "third evidence" as framed names the wrong variable, and the right one still has no externally observable side effect. |
| `Get-Process \| MainWindowTitle` enumerates the sample's windows | `scripts/monitor_keysteam.ps1` window-observation section (until 2026-09-15) | **Corrected 2026-09-15** | It reports **one main window per process**. The verification dialog is a Qt modal dialog inside the *same* process, so it was missed entirely: the 12:26 run logged only `KeySteam v2.99` while the operator watched the verification dialog appear and dismissed it manually. Use `user32 EnumWindows` (now in the script) and log **class + enabled** — the modal pair is `KeySteam 验证` (Enabled=True) alongside `KeySteam v2.99` (Enabled=False). Never trust a "no such window" conclusion drawn from `MainWindowTitle`. |
| `catch { }` is a safe way to skip an optional observation | `scripts/monitor_keysteam.ps1`, every observation block | **Corrected 2026-09-15** | A `catch {}` around the window block hid a field-level exception and rendered it as `窗口数=0` — i.e. the absence of a window, not the failure to look. Same error family as everything else in this table: **missing rendered as nonexistent**. Log the exception (`catch { W "WARN: ..." }`) instead of swallowing it. |

### On correcting an issue

When a claim in an issue comment turns out to be wrong, **append a correcting comment rather than silently editing the body**, and edit the body as well so the two agree. Appending preserves the reasoning trail — a reader can see *why* a conclusion was once drawn — while the body edit keeps the authoritative text clean for anyone who reads only the top of the ticket. The `#3`/`#4` ticket-validity retraction is the worked example: the retraction lived only in a comment for a day, and any reader who stopped at `#3`'s body would have taken the withdrawn claim as settled.


