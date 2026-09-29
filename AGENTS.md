# FucKeySteam

Reverse-engineering spike workspace for `KeySteam v2.99` (a Steam "fake-ownership" tool, second-hand OpenSteamTool derivative). The goal is narrow and single: **make the sample start without showing the verification-code dialog.**

## Layout

This repo is **not** the same directory as the sample workspace.

- **This repo** — `/mnt/d/03_Work/03_Develop/FucKeySteam`. Docs, scripts, native host source.
- **Workspace** — `/mnt/d/03_Work/03_Develop/KeySteam v2.99`. The sample, the unpacked `main.dll`, the onefile payload copy, the data-directory backup, and the four analysis documents.

Sample artifacts are excluded by `.gitignore` and must stay out. Read the workspace; write here.

## Security posture

The sample is an unsigned, fully-encrypted Nuitka onefile self-extractor that reads and writes the Steam directory, fabricates AppTicket/ETicket material, ships `curl_cffi` for TLS-fingerprint masquerading, and collects process/system state via `psutil`/`_wmi`. It runs a watchdog process and a named pipe.

### What is actually at stake on this machine (measured 2026-09-15)

The old wording here said "Work in an isolated VM. Do not run it on a machine whose Steam account matters." That is the right instinct but it states a slogan, not a fact, and this machine is *not* isolated — it already runs this class of tool. Replace the slogan with the inventory:

| Asset | Size | Why it matters |
| --- | --- | --- |
| `userdata/<main-id>/` (account `<main-account>`, the **main account**, currently logged out) | 9.4 M | Contains `ugcmsgcache` (7.0 M) and a game save under `1868140` (1.3 M). This is the only account holding real progress, and the part that cannot be rebuilt from the cloud. |
| `userdata/<alt-id>/` (account `<alt-account>`, the throwaway account, currently logged in) | 816 K | Current active session; small. |
| `userdata/<third-id>/` (account `<third-account>`, logged out) | 68 K | Negligible. |
| `config/` and `config.vdf` | 64 M / 41,830 B | All three accounts have `RememberPassword=1`, and there are **zero** `ssfn*` token files. Session credentials live here — reading or rewriting it exposes all three accounts at once. |
| `steamapps/` | 385 G, 26 titles, single library | High replacement cost, but recoverable by re-verifying files. |

**Restore points and shadow copies are an unknown, not a known-good.** `Get-ComputerRestorePoint`, `Win32_ShadowCopy` and `vssadmin list shadowstorage` all fail with access-denied from a non-elevated session. Treat rollback as unavailable unless you re-check elevated.

### The Steam directory has already been modified by this tool class

Measured, not inferred:

```
steam.exe              5,775,512 B  2025-09-03   b71018f404b569832bf62f280dcde935
steam.exe.old          5,774,488 B  2025-07-25   dbc0570e201d61cc224c6bd8d92eec54
steamclient64.dll     26,328,216 B  2025-09-03   2cee3ac29ba905bfb30c3a760dcf1366
steamclient64.dll.old 26,223,256 B  2025-07-25   22fc5d945cf594edf356a0bc33a6e3f5
KeySteamTool.dll       6,619,136 B  2025-09-13
cloud_redirect.dll     1,726,976 B  2025-09-12
cloud_redirect.log       289,397 B  2025-09-15   (written today)
```

Hashes and dates both differ, so the running `steam.exe` is **not** the Valve original. Restoring `.old` is therefore not a clean rollback: it also invalidates the pattern files this tool depends on —

```
keysteamtool/ipc/steamclient/caba4826...toml        934 B
keysteamtool/pattern/steamclient/caba4826...toml  3,000 B
keysteamtool/pattern/steamui/cb387ade...toml      1,307 B
```

The filenames are 64-hex-digit hashes — this is a version-hash-matched pattern framework, not a blind binary patch. Rolling back `steam.exe`/`steamclient64.dll` makes those hashes miss, which disables the existing tooling along with it. The two decisions are coupled; do not treat `.old` as a safety net without accounting for that.

### The sample terminates Steam and cleans the plugin directory

Static evidence in `main.dll` (string constants, `src/steam/cleanup_service.py`):

```
0x8b2c95  terminate_all
0x8acc31  即将关闭 Steam 相关进程喵~
0x8acb79  清理会干扰初始化的旧插件文件
0x8ad337  .ks      0x8ad33f  .lua      0x8ad345  .ks
```

It kills Steam processes and cleans startup plugin files as defined behaviour, not as a possible side effect. Existing `config/stplug-in/*.lua` and `*.ks` scripts are in scope for that cleanup.

## Main-account protection: why no ACL is applied

The operating constraint for this work is "do not touch `userdata/<main-id>/`" (the main account). That is met by evidence, not by a filesystem ACL. Measured facts:

- `<main-id>` has **zero** hits anywhere in `main.dll` (all ASCII and integer encodings) — there is no hardcoded, account-targeted write path.
- Account selection is single-valued: `HKCU\Software\Valve\Steam\ActiveProcess\ActiveUser`, with `loginusers.vdf` as a secondary source. There is no loop that walks all three account directories and writes each.
- The only directory enumeration is a diff, not a traversal: `_list_numeric_files` polls `userdata/` for *newly created* numeric directories after launching a game.
- `userdata/` is a **read-only source** for this sample (`source_userdata_dir`). Writes go to an authorization **output** directory, `target_userdata_dir = output_dir/userdata/<user_id>/`, and the `rmtree` found at `0x8a0fbd` removes same-named copies *in that output directory*.
- Measured at decision time: `ActiveUser = 0x0` (invalid) and `loginusers.vdf` has **no `MostRecent` field** at all, so both account sources currently resolve to the logged-in throwaway account, never the main one.

An ACL `DENY` was considered and deliberately rejected. Its failure mode is worse than the risk it covers: forgetting to remove it leaves Steam silently unable to write that directory, and the damage surfaces weeks later as unsynced saves. The evidence above is not instruction-level complete — `_STEAM_ID_BASE`'s numeric value is not present as a literal, the precedence between the two account sources is not proven down to instructions, and `userdata` appears as a path template in three modules — so the substitute safeguard is **observation**: `_re/monitor_keysteam.ps1` records data-directory changes during any run.


## Agent skills

### Issue tracker

Issues and specs live in this repo's private GitHub Issues (Drivpe/FucKeySteam). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary, unchanged. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context, with the glossary living in the behavioural spec inside the workspace rather than a `CONTEXT.md`. See `docs/agents/domain.md`.

That file also carries a **drift register** — a table of claims that were once written down here and later found wrong, with where each lived and what the correct position is. This project has produced seven of them, several in a single day. Check it before reasoning from any older document, and add a row whenever you correct a claim. The related convention: correct an issue by **appending a comment**, then bring the body into line — do not silently rewrite history.

