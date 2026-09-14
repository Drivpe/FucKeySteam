# keysteam-unlock-spike

Reverse-engineering spike workspace for `KeySteam v2.99` (a Steam "fake-ownership" tool, second-hand OpenSteamTool derivative). The goal is narrow and single: **make the sample start without showing the verification-code dialog.**

## Layout

This repo is **not** the same directory as the sample workspace.

- **This repo** — `/mnt/d/03_Work/03_Develop/keysteam-unlock-spike`. Docs, scripts, native host source.
- **Workspace** — `/mnt/d/03_Work/03_Develop/KeySteam v2.99`. The sample, the unpacked `main.dll`, the onefile payload copy, the data-directory backup, and the four analysis documents.

Sample artifacts are excluded by `.gitignore` and must stay out. Read the workspace; write here.

## Security posture

The sample is an unsigned, fully-encrypted Nuitka onefile self-extractor that reads and writes the Steam directory, fabricates AppTicket/ETicket material, ships `curl_cffi` for TLS-fingerprint masquerading, and collects process/system state via `psutil`/`_wmi`. It runs a watchdog process and a named pipe.

Work in an isolated VM. Do not run it on a machine whose Steam account matters. This is not boilerplate caution — it is the operative risk here.

## Agent skills

### Issue tracker

Issues and specs live in this repo's private GitHub Issues (Drivpe/keysteam-unlock-spike). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary, unchanged. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context, with the glossary living in the behavioural spec inside the workspace rather than a `CONTEXT.md`. See `docs/agents/domain.md`.
