# run_probe.ps1 - Phase B injection test orchestration (ASCII only)
#
# Timing contract:
#   1. monitor must start BEFORE the sample
#   2. sample is launched by this script
#   3. probe injects as soon as the sample appears
#   4. no `timeout` wrapper around sample/host
param(
    [string]$Mode    = "crt",       # crt | apc | none | debug
    [string]$Dll     = "",
    [int]$HoldSec    = 25,
    [int]$InjectAtMs = 0,
    [string]$Sample  = "D:\03_Work\03_Develop\KeySteam v2.99\KeySteam.exe",
    [string]$Probe   = "D:\03_Work\03_Develop\FucKeySteam\.scratch\ksinj\probe.exe"
)

$ErrorActionPreference = "Continue"
$stamp  = Get-Date -Format "yyyyMMdd-HHmmss"
$outDir = "$env:TEMP\ks_re\inj-$Mode-$stamp"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$log = "$outDir\coordination.log"

function W([string]$m) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss.fff"), $m
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding UTF8
}

W "=== Phase B orchestration start mode=$Mode ==="
W "outDir: $outDir"

$pre = Get-Process KeySteam -ErrorAction SilentlyContinue
if ($pre) { W "ABORT: KeySteam already running pid=$($pre.Id -join ',')"; exit 1 }
$pipes = [System.IO.Directory]::GetFiles("\\.\pipe\") | Where-Object { $_ -match 'keysteam' }
if ($pipes) { W "WARN leftover pipes: $($pipes -join ', ')" }

# --- 1. monitor first ---
$monScript = "D:\03_Work\03_Develop\FucKeySteam\scripts\monitor_keysteam.ps1"
$monSec    = $HoldSec + 30
W "starting monitor (before sample), ${monSec}s"
$monJob = Start-Job -ScriptBlock {
    param($s, $sec)
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $s -Seconds $sec -TightLoopMs 0
} -ArgumentList $monScript, $monSec

$monDir = "$env:TEMP\ks_re"
$before = Get-Date
$monLog = $null
while (((Get-Date) - $before).TotalSeconds -lt 25) {
    Start-Sleep -Milliseconds 250
    $cand = Get-ChildItem "$monDir\monitor-*.log" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime | Select-Object -Last 1
    if ($cand -and $cand.LastWriteTime -gt $before) { $monLog = $cand; break }
}
if ($monLog) {
    W "monitor ready: $($monLog.FullName)"
} else {
    W "WARN: monitor readiness not confirmed, continuing"
}

# --- 2. launch sample ---
W "launching sample: $Sample"
$proc = Start-Process -FilePath $Sample -WorkingDirectory (Split-Path $Sample) -PassThru
W "sample launched pid=$($proc.Id)"

# --- 3. probe ---
if ($InjectAtMs -gt 0) { Start-Sleep -Milliseconds $InjectAtMs }

$probeArgs = @()
switch ($Mode) {
    "debug" { $probeArgs = @("--debug-attach", "-w", ($HoldSec * 1000)) }
    "none"  { $probeArgs = @("-w", ($HoldSec * 1000)) }
    default { $probeArgs = @("-m", $Mode, "-d", $Dll, "-w", ($HoldSec * 1000)) }
}

$probeOut = "$outDir\probe.txt"
$probeErr = "$outDir\probe-err.txt"
$pArgs = $probeArgs -join ' '
W "running probe: $Probe $pArgs"
$p = Start-Process -FilePath $Probe -ArgumentList $pArgs -PassThru `
     -RedirectStandardOutput $probeOut -RedirectStandardError $probeErr -NoNewWindow
W "probe pid=$($p.Id)"
$p | Wait-Process -Timeout ($HoldSec + 20) -ErrorAction SilentlyContinue

W "=== probe output ==="
if (Test-Path $probeOut) { Get-Content $probeOut | ForEach-Object { W "  $_" } }
if (Test-Path $probeErr) {
    $e = Get-Content $probeErr -Raw
    if ($e -and $e.Trim()) { W "probe stderr: $e" }
}

# --- 4. cleanup ---
$now = Get-Process KeySteam -ErrorAction SilentlyContinue
if ($now) {
    W "closing sample pid=$($now.Id -join ',')"
    $now | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 900
}
$left = Get-Process KeySteam -ErrorAction SilentlyContinue
if ($left) { W "residual KeySteam: $($left.Id -join ',')" } else { W "residual KeySteam: none" }

Stop-Job $monJob -ErrorAction SilentlyContinue
Remove-Job $monJob -Force -ErrorAction SilentlyContinue

$left2 = Get-Process KeySteam -ErrorAction SilentlyContinue
if ($left2) { $left2 | Stop-Process -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 400
$left3 = Get-Process KeySteam -ErrorAction SilentlyContinue
if ($left3) { W "STILL RUNNING: $($left3.Id -join ',')" } else { W "final: no KeySteam" }

$pipes2 = [System.IO.Directory]::GetFiles("\\.\pipe\") | Where-Object { $_ -match 'keysteam' }
if ($pipes2) { W "residual pipes: $($pipes2 -join ', ')" } else { W "residual pipes: none" }
W "=== orchestration end, outDir: $outDir ==="
