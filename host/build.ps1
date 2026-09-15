# build.ps1 -- Windows-side fallback build for host.exe.
#
# ----------------------------------------------------------------------
# STATUS OF THIS PATH: NOT VERIFIED WORKING. READ BEFORE RELYING ON IT.
# ----------------------------------------------------------------------
#
# This script exists because the coordinating agent asked for a
# Windows-side entry point. It is provided for completeness, but it was
# NOT confirmed to produce an executable on this machine.
#
# MEASURED FACTS about the Windows-side path:
#
#   * gcc.exe itself runs: `gcc.exe --version` exits 0 and prints fine.
#   * `gcc.exe -### t.c -o out.exe` (dry run) exits 0 and prints a
#     correct command plan.
#   * `gcc.exe -v t.c -o out.exe` exits 1 with NO error text at all.
#     Its -v trace stops immediately after printing the as.exe command
#     line, i.e. the driver dies while spawning / right after spawning
#     its children. No diagnostic is emitted on stderr.
#   * Every toolchain component works when invoked DIRECTLY:
#       cc1.exe t.c -o manual.s      -> exit 0, 428-byte .s produced
#       as.exe -o manual.o manual.s  -> exit 0, 768-byte .o produced
#   * Therefore the components are fine; the gcc DRIVER's subprocess
#     spawn is what breaks under this environment.
#
# HYPOTHESES TESTED AND REJECTED (do not re-test these):
#
#   - Wrong source path format (POSIX vs Windows): both fail.
#   - Missing cc1/as/ld: all present and individually functional.
#   - Missing UCRT downlevel DLLs: present; gcc runs anyway.
#   - Antivirus interference: real-time protection reported off.
#   - TEMP/TMP not writable: TEMP was proven writable; pointing
#     TMP/TEMP at a local directory did not help.
#   - Spaces in "C:\Program Files": using the 8.3 short path
#     C:\PROGRA~1\mingw64\bin\X8EAA8~1.EXE still failed.
#   - The -B flags that fix the WSL path: adding the same four -B
#     flags Windows-side still failed, so this is a separate fault.
#   - Broken baked-in search paths (the "mingw64D:/a/_temp/..."
#     concatenation visible in -v): present but appear non-fatal,
#     since those directories are the ones gcc reports as missing
#     and existing ones are still found.
#
# CONCLUSION: the WSL-side route in build.sh -- invoking the same gcc
# with four -B flags -- is the path that actually works here, verified
# end to end. Use build.sh. Keep this file as a documented dead end.
#
# Usage (if you want to try anyway):
#     powershell.exe -NoProfile -ExecutionPolicy Bypass -File build.ps1

$ErrorActionPreference = 'Stop'

$Gcc      = 'C:\Program Files\mingw64\bin\x86_64-w64-mingw32-gcc.exe'
$Mingw    = 'C:\Program Files\mingw64'
$Ver      = '15.1.0'   # keep in sync with build.sh auto-detection
$HostDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Src      = Join-Path $HostDir 'host.c'
$Out      = Join-Path $HostDir 'host.exe'

Write-Host "build.ps1: gcc  = $Gcc"
Write-Host "build.ps1: src  = $Src"
Write-Host "build.ps1: out  = $Out"

if (-not (Test-Path $Src)) {
    Write-Error "build.ps1: source not found: $Src"
    exit 1
}

# Note: -Wno-expansion-to-defined suppresses a mingw header wart; the
# remaining macro-redefinition warnings come from mingw's own headers
# and are harmless. We silence them to keep the log readable.
$args = @(
    '-municode',
    '-O2',
    '-Wall',
    '-Wno-expansion-to-defined',
    '-Wno-builtin-macro-redefined',
    '-B', "$Mingw\libexec\gcc\x86_64-w64-mingw32\$Ver\",
    '-B', "$Mingw\bin\",
    '-B', "$Mingw\x86_64-w64-mingw32\lib\",
    '-B', "$Mingw\lib\gcc\x86_64-w64-mingw32\$Ver\",
    '-I',  "$Mingw\x86_64-w64-mingw32\include",
    $Src,
    '-o', $Out,
    '-lshell32'
)

Write-Host "build.ps1: invoking gcc (expect this to fail on some hosts)"
& $Gcc @args
$code = $LASTEXITCODE
Write-Host "build.ps1: gcc exit code = $code"

if (Test-Path $Out) {
    Write-Host "build.ps1: BUILD OK"
    Get-Item $Out | Format-List Name, Length, LastWriteTime
} else {
    Write-Host "build.ps1: BUILD FAILED -- no output produced"
    Write-Host "build.ps1: this is the known failure mode; use build.sh from WSL."
    exit 1
}
