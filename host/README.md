# host.exe — minimal native host for the Nuitka onefile business module

Loads `main.dll`, resolves the `run_code` export, and invokes it with
**three** arguments:

```c
int run_code(int argc, wchar_t **argv, const wchar_t *dll_filename);
```

Compiling is the whole job here. Nothing in this directory executes the
sample. See "Running" at the end — that part is for a human, in an
isolated VM.

---

## Build

From WSL, in this directory:

```bash
bash build.sh
```

Expected result: `host.exe`, a PE32+ x86-64 console executable, roughly
64 KB, exit code 0.

The build is reproducible apart from the PE header timestamp. Two builds
in the same second are byte-identical; builds a minute apart differ in
exactly three bytes — the `TimeDateStamp` field at PE header offset
`0x88`, and nothing else. Measured: `cmp -l` against a prior build
reports three differing bytes, all inside that field. If you need
bit-exact reproducibility across time, set `SOURCE_DATE_EPOCH`.

---

## The mingw path problem, and why the four `-B` flags fix it

### The symptom

```bash
"/mnt/c/Program Files/mingw64/bin/x86_64-w64-mingw32-gcc.exe" /tmp/t.c -o /tmp/t.exe
# x86_64-w64-mingw32-gcc.exe: fatal error: cannot execute 'cc1': CreateProcess: No such file or directory
```

### The wrong explanation

The intuitive reading is "the Windows-side `.exe` cannot understand the
WSL `/tmp/...` path". **That is not the root cause.** Measured: passing a
native Windows path fails identically.

```bash
gcc.exe 'D:\...\t.c' -o 'D:\...\t.exe'
# same cc1 error
```

The source path is irrelevant. So is the output path.

### The actual root cause

`gcc.exe -print-search-dirs` exposes it:

```
install:  D:/03_Work/03_Develop/KeySteam v2.99/../lib/gcc/x86_64-w64-mingw32/15.1.0/
programs: D:/03_Work/03_Develop/KeySteam v2.99/../libexec/gcc/x86_64-w64-mingw32/15.1.0/;...
```

The driver derives its tool and library search roots **from `argv[0]`**.
When WSL launches a Windows binary, `argv[0]` arrives as the POSIX path
`/mnt/c/Program Files/mingw64/bin/x86_64-w64-mingw32-gcc.exe`. Windows
cannot interpret that, mangles it against the current drive, and computes
a `libexec` root that does not exist. `cc1` is then never found — hence
the message names `cc1` even though `cc1.exe` is present and healthy.

The error text is a red herring. Do not go hunting for a missing `cc1`.

### The fix: four `-B` flags

`-B <dir>` overrides the computed search roots directly, so the broken
`argv[0]` derivation stops mattering. Pointing `-B` at `libexec` changes
the error from `cannot execute 'cc1'` to `cannot execute 'as'` — proof
that `cc1` was located and the next stage is now the missing one.

**Four `-B` flags are required, and each is independently mandatory**
(verified by removing them one at a time):

| `-B` target | supplies |
| --- | --- |
| `libexec/gcc/x86_64-w64-mingw32/15.1.0/` | `cc1`, `collect2` |
| `bin/` | `as`, `ld`, `nm`, … |
| `x86_64-w64-mingw32/lib/` | `crt2.o`, `libmingw32.a`, `-lmsvcrt`, `-lkernel32` |
| `lib/gcc/x86_64-w64-mingw32/15.1.0/` | `crtbegin.o`, `crtend.o`, `-lgcc`, `-lgcc_eh` |

Removing the fourth yields `cannot find -lgcc / -lgcc_eh`. Removing the
third yields `cannot find crt2.o / -lmingw32`. A single
`-B <mingw64 root>` does **not** work: `-B` is a prefix, not a recursive
search root.

Headers are lost to the same `argv[0]` fault, so `-I` is needed too —
without it, `#include <windows.h>` is not found:

```
-I 'C:\Program Files\mingw64\x86_64-w64-mingw32\include'
```

`build.sh` auto-detects the versioned `libexec` directory, so a
toolchain upgrade does not silently break the build. It also converts
the source and output paths to Windows form with `wslpath -w` before
handing them to the driver, which keeps `cc1`, `as` and `ld` agreeing
on how to find the inputs.

### Alternative: a Windows-side `build.ps1` (provided, NOT verified working)

`build.ps1` in this directory is a Windows-side entry point. It is a
documented dead end, not a working fallback.

Measured behavior of the Windows-side route on this machine:

- `gcc.exe --version` → exit 0, prints fine.
- `gcc.exe -### t.c -o out.exe` (dry run) → exit 0, correct command plan.
- `gcc.exe -v t.c -o out.exe` → **exit 1 with no output at all**. The
  `-v` trace stops right after printing the `as.exe` command line: the
  driver dies while spawning, or immediately after spawning, its
  children. Nothing is written to stderr, not even with redirection.
- All components work when invoked **directly**:
  `cc1.exe t.c -o manual.s` → exit 0, 428-byte `.s`;
  `as.exe -o manual.o manual.s` → exit 0, 768-byte `.o`.

So the components are sound and the driver's subprocess spawn is what
breaks in this environment.

Hypotheses tested and **rejected** — do not re-test these:

- Source path format (POSIX vs Windows): both fail.
- Missing `cc1` / `as` / `ld`: all present and individually functional.
- Missing UCRT downlevel DLLs: present; `gcc` runs regardless.
- Antivirus interference: real-time protection reported off.
- `TEMP`/`TMP` not writable: `TEMP` proven writable; repointing
  `TMP`/`TEMP` at a local directory did not help.
- Spaces in `C:\Program Files`: the 8.3 short path
  `C:\PROGRA~1\mingw64\bin\X8EAA8~1.EXE` failed the same way.
- The same four `-B` flags Windows-side: still failed, so this is a
  fault distinct from the `argv[0]` problem that `-B` solves in WSL.
- The `mingw64D:/a/_temp/...` concatenated path visible in `-v`: real,
  but apparently non-fatal — those are exactly the directories `gcc`
  reports as missing, and the ones that exist are still found.

**Use `bash build.sh` from WSL.** That route is verified end to end.

### On the intermittent no-output failure

A "sometimes exit 1 with completely empty stderr" symptom was reported
during coordination. In my probes the Windows-side failure was not
intermittent: it reproduced 5/5 times in one directory, and the
`gcc.exe -v` trace above shows a silent death at the spawn boundary
rather than a nondeterministic one. If you do hit an intermittent
failure on the Windows side, it is consistent with the same spawn
fault surfacing under load; there is no retry logic that makes it
reliable. Prefer `build.sh`.

---

## What the host does

**Three-argument call, and the third argument is NOT an environment
block.** Its type is `filename_char_t const *` (`const wchar_t *` on
Windows): a single NUL-terminated wide string holding the absolute path
of `main.dll`. Nuitka's `MainProgram.c` receives it as
`filename_char_t const *dll_filename` and does
`if (dll_filename != NULL) setDllFilename(dll_filename);`. The compiled
`setDllFilename` is two instructions — store the pointer, return. Its
consumer copies out characters with
`movzx eax, WORD PTR [rcx]` / `mov WORD PTR [rdx], ax`, stepping two
bytes at a time and stopping at one NUL: **one level of indirection
only.** A pointer array would need two; an environment block would need
`=` or double-NUL scanning. Neither appears.

This matters because the mistake is silent. Passing an environment array
here does not crash — the callee stores the array's first slot and later
reads it as character data, producing a garbage path while the process
runs normally. An earlier revision of this file did exactly that.

**`argv` is `wchar_t**`, the third argument is `const wchar_t *`.**
Never `char**`; never `wchar_t**` for the third. Built with `-municode`
so the entry point is `wmain` and the CRT hands us a wide `argv`.

**`argv[0]` ends in `.py`.** This is load-bearing, not cosmetic. The
payload strips and casefolds `argv[0]` and compares it against
`(".py", ".pyw")` to conclude it is running "from source", which turns
off the integrity self-check. The default is
`<payload_dir>\KeySteam.py`. The file does not need to exist on disk.

**Environment variables go into the PROCESS environment**, not into the
third argument. Two are relevant:

- `NUITKA_ONEFILE_DIRECTORY` — **the directory containing the host
  executable**, which is what Nuitka itself sets
  (`stripBaseFilename(binary_filename)`). Not the payload directory.
- `NUITKA_ORIGINAL_ARGV0` — the value for
  `__compiled__.original_argv0`. **Optional:** if unset, Nuitka falls
  back to the `argv[0]` we pass. Set it to make `original_argv0` name
  the host rather than the script path.

Set with `SetEnvironmentVariableW`, not through `run_code`'s arguments.

Note `NUITKA_ONEFILE_TEMP` is **not** a Nuitka variable — it has zero
hits in Nuitka's source. The three occurrences inside `main.dll` are
KeySteam's own application-level identifiers.

**Dependency resolution.** `main.dll` statically imports
`python312.dll` plus KERNEL32, VCRUNTIME140 and seven `api-ms-win-crt-*`
stubs. Those must resolve out of the payload directory. Two steps,
mirroring Nuitka's own `OnefileBootstrap.c`:

```c
AddDllDirectory(payload_path);
LoadLibraryExW(L"main.dll", NULL,
    LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR |   /* 0x00000100 */
    LOAD_LIBRARY_SEARCH_SYSTEM32    |    /* 0x00000800 */
    LOAD_LIBRARY_SEARCH_USER_DIRS);      /* 0x00000400  = 0xD00 */
```

`AddDllDirectory` normally requires `SetDefaultDllDirectories`, but
passing `LOAD_LIBRARY_SEARCH_USER_DIRS` explicitly satisfies the
precondition for this one call. The host deliberately takes that route:
`SetDefaultDllDirectories` would change DLL resolution for every
subsequent load in the process, a side effect we do not need.
`LOAD_WITH_ALTERED_SEARCH_PATH` (0x8) is deliberately **not** used — it
cannot be combined with the `LOAD_LIBRARY_SEARCH_*` flags.

**Exit code** on the normal path is `run_code`'s return value verbatim.
In practice that path is unreachable: `run_code` calls `Nuitka_Main`,
which ends in `Py_Exit` (`MainProgram.c:2355`) and terminates the whole
process. So `host.exe` normally never returns at all — the line
`[host] run_code returned N` is only ever printed on an *abnormal* exit.

The host's own failure codes, verified against the source:

| Code | Meaning | Site |
| --- | --- | --- |
| `0` | `--help` / `-h` | host.c:192 |
| `2` | Argument or memory failure (no DLL path, OOM, `GetModuleFileNameW` failed) | host.c:206, 215, 226, 385, 405 |
| `3` | `LoadLibraryExW(main.dll)` failed — the module or one of its imports could not be resolved | host.c:324 |
| `4` | `GetProcAddress(main.dll, "run_code")` returned NULL | host.c:363 |

**These line numbers have already gone stale twice** — once after the
`run_code`-third-argument rewrite and again after the
`LoadLibraryExW`-full-path fix. Do not trust them; re-derive:

```bash
grep -n 'return [0-9]\|return status' host/host.c
```

The task's own lesson generalises: this repo has a documented history of
line-number and position drift, so any citation of a specific line is a
claim that needs re-checking, not a fact that can be quoted forward.

There is **no** exit code `5`. An earlier handoff document claimed
`5 = environment variable setting failure`; no such path exists in the
source — `fail()` prints diagnostics and returns void, it does not
produce a code. If you observe a `5`, it came from `run_code` itself.

**Errors** go to stderr, with `GetLastError()` printed both numerically
and as text via `FormatMessageW`, for both `LoadLibraryExW` and
`GetProcAddress`.

---

## Command line

```
host.exe --dll <path\to\main.dll> [--no-envp] [--null-3rd] [args...]
```

- `--dll <path>` — path to `main.dll`. The payload directory is derived
  from its parent, and that directory is used for `AddDllDirectory`, for
  `NUITKA_ONEFILE_DIRECTORY`, and as the prefix of `argv[0]`.
- `--no-envp` — do **not** set `NUITKA_ONEFILE_DIRECTORY` /
  `NUITKA_ORIGINAL_ARGV0` in the process environment. Default is to set
  both.
- `--null-3rd` — pass `NULL` as `run_code`'s third argument. Default is
  the absolute `main.dll` path. (The argument carries the DLL path, not an
  environment block.)
- `args...` — forwarded to `run_code` after `argv[0]`. Host-level
  switches are not forwarded.
- `--help` / `-h` — usage.

**The two switches are independent**, and they used to be one. Before
2026-09-15 `--no-envp` did *both* jobs, so the "control run" varied the
third argument **and** the environment at once — a compound diff that
could not attribute anything. Re-derive the current split rather than
trusting a remembered flag name:

```bash
grep -n 'inject_env\|pass_third' host/host.c
```

Before loading anything the host prints the resolved paths, the switch
state, the constructed `argv` array and the two injected variables, so a
run log records exactly what `run_code` received. The switch banner reads
`[host] switches = env:inject|skip  third:dll path|NULL (control run)`.

---

## Running (human operator, isolated VM only)

**Do not run the sample on a machine whose Steam account matters.** It is
unsigned, fabricates AppTicket/ETicket material, collects process and
system state, and ships `curl_cffi` for TLS-fingerprint masquerading. Use
a throwaway VM with no valuable Steam session.

Baseline run, from Windows in the payload directory:

```cmd
D:\path\to\keysteam-unlock-spike\host\host.exe --dll "D:\03_Work\03_Develop\KeySteam v2.99\_re\work\payload\main.dll"
```

Comparison run, passing NULL instead of the DLL path (and still
injecting the environment, so only the third argument varies):

```cmd
D:\path\to\keysteam-unlock-spike\host\host.exe --dll "D:\03_Work\03_Develop\KeySteam v2.99\_re\work\payload\main.dll" --null-3rd
```

Second comparison run, dropping only the environment variables:

```cmd
D:\path\to\keysteam-unlock-spike\host\host.exe --dll "D:\03_Work\03_Develop\KeySteam v2.99\_re\work\payload\main.dll" --no-envp
```

Capture the log, since the host's diagnostics go to stderr:

```cmd
... > run.log 2>&1
```

The two runs can be diffed to see what the third argument changes:
with `NULL`, `getBinaryFilenameWideChars` falls through to
`GetModuleFileNameW(NULL, ...)` and reports `main.dll`'s own path.

---

## Files

- `host.c` — the host source.
- `build.sh` — the verified build (WSL side).
- `build.ps1` — Windows-side fallback; documented dead end, kept for
  the record.
- `host.exe` — build output. Excluded by `.gitignore`; source is
  committed, artifacts are not.

---

## Unresolved

- The Windows-side gcc driver spawn failure is not root-caused, only
  characterized and bounded. The workaround is to build from WSL.
- `build.ps1` has never produced an executable here.
- `run_code`'s third parameter is used as documented, but the host
  itself has never been run — by design, execution is the human's job in
  a VM.
- The host does not verify that `main.dll` actually exports `run_code`
  as anything other than by name; if the export is ordinal-only,
  `GetProcAddress` returns NULL and the host exits 4 with a hint.
