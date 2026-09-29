# scripts/

## `monitor_keysteam.ps1`

Runtime observation script for the two runs described in `docs/run-plan.md`.

**This file exists in two places, and the repo copy is the tracked one:**

| Location | Tracked? | Role |
| --- | --- | --- |
| `scripts/monitor_keysteam.ps1` (here, in the repo) | yes | The version under version control. Edit this one. |
| `/mnt/d/03_Work/03_Develop/KeySteam-v2.99/_re/monitor_keysteam.ps1` | no — the workspace is not a git repo | The copy the run commands actually invoke. |

After editing here, copy it to the workspace path so the run commands pick up the change:

```bash
cp scripts/monitor_keysteam.ps1 \
   "/mnt/d/03_Work/03_Develop/KeySteam-v2.99/_re/monitor_keysteam.ps1"
```

### What it observes

Seven things, all read-only:

- Processes matching `Test-Watched`: exact (case-insensitive) membership in the list `host`, `keysteam`, `keysteam-runtime-guard`, `guard`, `watchdog`, `kst`, `python`, `python312`, `steam` — **or** a `^python3\d+$` regex match, so a versioned interpreter name (`python313`) is caught without listing every version.
- Named pipes matching `keysteam`
- TCP connections **from watched processes only** (see below)
- Window titles — critical patterns unconditionally, others only from watched processes
- `%APPDATA%\Shikieiki\` file additions and modifications
- `config\stplug-in\` — by **hash**, so deletions and rewrites are both legible (`mtime` cannot distinguish them, and the sample deletes files here)
- `userdata\<main-id>\` — main-account write detection; any hit is logged with a `!!!` prefix

### Two matching bugs fixed on 2026-09-15

Both were the same error, and both were live in the previous revision:

- **Substring matching used as exact matching.** The process and network filters used `-like "*$_*"`, so `svchost` and `StartMenuExperienceHost` matched `host`, and `nutstore_watchdog` matched `watchdog`. `host.c`'s `wcsstr(argv_in[i], L".dll")` (finder: `grep -n wcsstr host/host.c`) has the identical flaw. Now: exact comparison against a watch list.
- **Unfiltered enumeration.** Network and window collection swept the whole system, so the log filled with `wegame`, `Nutstore`, `firefox`, `Clash`, `SiYuan` traffic instead of the sample's. Now filtered by process.

The `-match 'KeySteam'` window rule is deliberately broad and will fire on, for example, a browser tab showing this project. That is a conscious trade: a false positive costs one log line, a missed window costs the run.

### Encoding constraint — read this before editing

The file contains Chinese and **must be saved as UTF-8 with BOM**.

PowerShell 5.1 on this machine reports its default encoding as `gb2312`. It decodes BOM-less UTF-8 as GBK, and the mangled Chinese in comments breaks quote pairing — the script then fails to parse with errors pointing at unrelated lines. This was hit twice on 2026-09-15, and the `edit` tool drops the BOM every time it rewrites the file.

Verify after any edit:

```bash
head -c 3 scripts/monitor_keysteam.ps1 | od -An -tx1   # expect: ef bb bf
```

Parse-check:

```bash
powershell.exe -NoProfile -Command "\$e=\$null;[System.Management.Automation.Language.Parser]::ParseFile('D:\03_Work\03_Develop\keysteam-unlock-spike\scripts\monitor_keysteam.ps1',[ref]\$null,[ref]\$e)|Out-Null;if(\$e.Count -eq 0){'SYNTAX OK'}else{\$e|%{\$_.Message}}"
```

### Invocation

```bash
powershell.exe -NoProfile -ExecutionPolicy Bypass -File \
  "D:\03_Work\03_Develop\KeySteam v2.99\_re\monitor_keysteam.ps1" \
  -Seconds 600 -LogDir "D:\...\.scratch\run-<TS>"
```

`-Seconds` is a loop count at 500 ms per iteration, so `600` is roughly 5 minutes. Do not go below 300: the sample makes network calls and is silent while waiting, which is normal, not a hang.
