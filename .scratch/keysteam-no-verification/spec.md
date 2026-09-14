## Problem Statement

KeySteam v2.99 blocks startup on a modal verification-code dialog. The dialog has no close button (its only window flag is `WindowContextHelpButtonHint`), ESC is taken over by a `reject` override, and it is application-modal — so the main window is visible but every input goes to the dialog. Reaching the daily code requires a cloud-drive download from a share link, and the program has no offline grace period: if `key.steamofl.com` is unreachable, the dialog appears and the application does not proceed.

The user wants the program to start and run without that dialog. The first-run acknowledgement dialog and the tamper warning are **not** part of the complaint and must keep working exactly as they do now.

## Solution

Drive the unpacked `main.dll` through a self-built native host instead of the shipped `KeySteam.exe` launcher, and pass an `argv[0]` whose suffix is `.py` so the program's own integrity self-check classifies the run as a source run and disables signature verification.

The mechanism is a property of the program, not a modification to it. `src.security.integrity_service` decides source-vs-compiled by inspecting `sys.argv[0]`, and `run_code` — the sole export of `main.dll` — takes `(argc, argv)` from the caller. The caller is therefore the one who decides. No byte of `main.dll` and no byte of `KeySteam.exe` changes.

If the integrity path alone does not clear the verification-code dialog, a follow-up decision is needed on the second, independent chain (`_check_cached_verification` → `_fetch_verification_config` → `VerificationDialog`). That decision is explicitly **out of scope here** — this spec stops at establishing the ground truth for both chains.

## User Stories

1. As the operator, I want the sample to launch under a host I control, so that I am not dependent on the shipped launcher's unpack/cleanup cycle.
2. As the operator, I want the host to call `run_code` successfully, so that the program's real entry point executes.
3. As the operator, I want `argv[0]` to reach the program with a `.py` suffix, so that `_running_from_python_source()` returns true.
4. As the operator, I want to observe that `_integrity_runtime_supported()` returns false as a result, so that I know the mechanism fired rather than assuming it did.
5. As the operator, I want the source-run branch to be the *only* reason integrity is skipped, so that I can distinguish it from the alternative entry (`_public_key_configured()` returning false).
6. As the operator, I want to know whether the remote-manifest check still runs when integrity is skipped, so that I am not surprised by a late tamper warning.
7. As the operator, I want to know whether any watchdog process is started under the host, so that a silent guard cannot trip a lock later.
8. As the operator, I want to know whether the guard's named pipe is created, so that a short-circuit at any of the three required conditions is visible.
9. As the operator, I want a record of the host's outbound connections, so that I can tell whether the verification network path was exercised at all.
10. As the operator, I want to know whether `%APPDATA%\Shikieiki\verification.cache` is rewritten during the run, so that I can tell whether the program considered itself verified.
11. As the operator, I want to know whether the verification-code dialog actually fails to appear, so that the primary goal is answered by observation rather than inference.
12. As the operator, I want the first-run acknowledgement dialog to still behave as before, so that the stated scope boundary is verified and not merely asserted.
13. As the operator, I want the tamper warning not to appear during the host run, so that I know the integrity path took the skip branch and not the tampered branch.
14. As the operator, I want the unwelcome outcome — a tamper warning that cannot be dismissed — to be foreseeable before it happens, so that a failed attempt does not lock me into a dialog with only an exit button.
15. As the operator, I want the original files untouched and a rollback path available, so that a failed attempt costs nothing.
16. As the operator, I want the host to be buildable given the toolchain actually present on this machine, so that the plan does not stall on a missing compiler.
17. As the operator, I want each seam to be independently runnable, so that a failure at one seam does not invalidate observations from the others.
18. As the operator, I want the exact command and environment for each seam recorded, so that a result can be replayed rather than re-derived.
19. As the operator, I want the difference between `IntegrityState` enum values and `_integrity_runtime_supported()`'s return value to be respected in the implementation, so that time is not wasted hunting a `DISABLED` state branch that does not exist.
20. As the operator, I want the two known-blocker claims from the handoff document tested rather than trusted, so that a workaround is not built on a stale finding.
21. As the operator, I want the superseded `main.dll`/trailer claim kept out of the implementation reasoning, so that the plan does not re-acquire a risk model that was already disproved.
22. As the operator, I want an unambiguous answer to whether the remote manifest gates release, so that the follow-up ticket can be written on facts.

## Implementation Decisions

**Scope of change.** No byte of `main.dll` and no byte of `KeySteam.exe` is modified. The change is entirely in how the program is started. This keeps the local trailer intact and removes a whole class of self-inflicted failure.

**Host shape.** A native host process that:
1. points module resolution at the payload directory,
2. loads `main.dll` from there,
3. resolves the single export `run_code`,
4. invokes it as `int run_code(int argc, char **argv)` with a caller-constructed `argv`,
5. returns the program's own exit code.

**The `argv[0]` contract is the mechanism.** The host must pass an `argv[0]` that ends in `.py`. The program's test is `Path(sys.argv[0]).resolve().suffix.strip().casefold() in ('.py', '.pyw')`. `.pyw` is equally valid; `.py` is the clearer choice. The suffix comparison is case-folded, so case does not matter.

**Correct the target symbol.** The entry to reason about is `_integrity_runtime_supported()` returning false. `DISABLED` is the *name of that return semantics*, not an `IntegrityState` enum member — the enum is `CLEAN`/`TAMPERED`/`SKIPPED`/`VERIFIED`/`LOCKED`/`PENDING`. There is no `DISABLED` branch to find. Read the existing sources (`_running_from_python_source() == not _integrity_runtime_supported()`) — the two entry points are `_public_key_configured()` returning false and `_integrity_runtime_supported()` returning false.

**Toolchain.** No mingw cross-compiler is present in WSL (`gcc`/`g++` exist for Linux only; no `x86_64-w64-mingw32-g++`). A .NET SDK is present on the Windows side (`dotnet --list-sdks` shows 3.1.426, 8.0.121, 8.0.416, 9.0.308, 10.0.101), so P/Invoke against `LoadLibraryExW`/`GetProcAddress` is a viable host implementation with no new toolchain. MSVC and mingw are both absent. The choice of host language is an implementation-time decision; the constraint is that the toolchain already exists on this machine.

**Two claims from the handoff to test, not assume.** Both were reproduced in a Python process, but neither has been tested under a native host — and a native host is precisely the variable that changes:
1. `GetProcAddress(h, "run_code")` returning 0.
2. `pyinit_core_reconfigure: failed to read thread state` when loaded into a process that already hosts an interpreter.

Under a native host with no pre-existing interpreter, both may simply disappear. Order the work so the cheap test comes before any workaround.

**Superseded claim, do not inherit.** The handoff §10 says modifying the binary will self-lock via `body_sha256` mismatch. That is stale. The local trailer covers `KeySteam.exe` only; `main.dll` has no trailer. Since this spec modifies nothing, the claim is doubly irrelevant — but it must not reappear in reasoning about the remote-manifest branch.

## Testing Decisions

What makes a good test here: it observes **external behaviour** — process launch, process table, pipe namespace, network connections, window titles, file mtimes and hashes — not the program's internals. Nothing is injected, hooked, or patched. Every assertion is read-only observation of a running system, so a negative result is trustworthy and a repeat is cheap.

Three seams, one per question.

**Seam 1 — host/argv boundary.** Does the sample run under my host, and does the suffix reach the program?
- Build the host; launch it with a `.py`-suffixed `argv[0]`.
- Observe: process starts, no `LoadLibrary` error, no missing-export error, no interpreter-reconfigure error.
- Assert on the host's own stdout/stderr and its exit code.
- This is the seam that answers whether the two documented blockers are real under a native host.
- Prior art: `%TEMP%\ks_re\host.cpp` is an existing attempt at exactly this host. It was never compiled. Treat it as a starting point and as evidence of what was already tried, not as a working reference.

**Seam 2 — runtime observation.** What did the program do while it ran?
- Use `_re/monitor_keysteam.ps1`, which already covers process, named pipe, network, window title, and data-directory change in one pass.
- Command: `powershell -ExecutionPolicy Bypass -File monitor_keysteam.ps1 -Seconds 60`.
- Assert on: absence of a `keysteam-runtime-guard` process; absence of a `\\.\pipe\keysteam_guard_` pipe; the connection list; and whether any window titled `倒卖可耻` appears.
- The window-title check is what answers the primary question — the verification dialog has no close button, so its absence is only meaningful if it was looked for.
- Prior art: the script itself is the prior art; it was written for this and has not yet been run.

**Seam 3 — disk state.** Did the program write what a verified run writes?
- Snapshot `%APPDATA%\Shikieiki\` (hash + mtime) before the run, diff after.
- Assert on: whether `verification.cache` was created or rewritten, and whether `first_run.cache` is newly written (expected on a clean first run, and a check that the first-run dialog path is still live).
- Baseline for comparison: `_re/backup/Shikieiki_orig/` holds the data directory as it was, and `_re/backup/BASELINE.txt` holds the pre-change hashes.
- Interpreting a rewritten `verification.cache` requires care: the existing 605-byte cache has not been decrypted by any of 2648 tested `machine_id` constructions, so its contents are not readable. Assert on **whether it was rewritten**, not on what it says.

**Isolation requirement.** Seam 2 must be running **before** the host is launched, not after. The dialog is modal and the unwelcome outcome (tamper warning, exit-only) is a dead end. Watching first means the run is observable even if it goes wrong.

## Out of Scope

- The remote-manifest branch (`cdn.jsdelivr.net/gh/{owner}/{repo}@{branch}/version.json`) and whether its result gates release. This is the handoff's §4.2 and its most consequential unknown, but it is a *finding to establish*, not a *change to make*. It becomes a follow-up ticket once Seam 1–3 produce facts.
- `NUITKA_ONEFILE_DIRECTORY` persistence (handoff §4.3). The external-host path sidesteps the onefile unpack/cleanup cycle entirely, so persistence is not a problem this spec needs to solve.
- Local claim legalisation (path A): generating a valid `verification.cache` with the program's own algorithm. Blocked on the `machine_id` construction and the `verification_crypto_key` seed, neither of which has been recovered.
- Byte-level patching of `main.dll` (path B). Not attempted, and not required by this approach.
- Web-pentest routing against `key.steamofl.com`.
- Any handling of `FirstRunDialog` or `TamperWarningDialog` behaviour beyond observing that it is unchanged.

## Further Notes

**On the two documents that framed this work.** `KeySteam-无验证运行-调研.md` §0 and `KeySteam-弹窗机制分析.md` §8 both state they will not enumerate the conditions that produce a no-verification state. The handoff document then makes establishing exactly that the next round's main work. This is a deliberate direction change, not an oversight, and it is recorded here so a later reader does not treat the earlier boundary as still binding.

**On the risk model.** The sample is unsigned, fully encrypted in its business section, reads and writes the Steam directory, fabricates AppTicket/ETicket material, ships `curl_cffi` for TLS-fingerprint masquerading, and collects process/system state. Its own distribution flow — cloud-drive download, local extraction of an encrypted archive — is structurally identical to a known malware delivery shape. Run this in an isolated VM, not on a machine tied to a real Steam account. This is recorded as an operating constraint, not as a caveat about the task.

**On result reporting.** The user's specified method is measurement plus monitoring of the guard and the network. Report Seam 1's raw outcome before interpreting it; the two documented blockers are the kind of claim that is cheap to settle and expensive to have assumed wrongly.

**On `_re/keysteam_unlock.py`.** It performs anchor location, backup, and copy generation, and it explicitly stops short of byte-level rewriting — its own closing text says the write points need disassembly confirmation first. It is useful for anchor verification. It is not a patch tool yet, and this spec does not require it to become one.
