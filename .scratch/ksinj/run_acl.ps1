param(
    [string]$Sample = "D:\03_Work\03_Develop\KeySteam v2.99\KeySteam.exe",
    [string]$AclExe = "D:\03_Work\03_Develop\keysteam-unlock-spike\.scratch\ksinj\acltest.exe",
    [int]$WaitSec  = 14
)
$ErrorActionPreference = "Continue"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outDir = "$env:TEMP\ks_re\acl-$stamp"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
function W([string]$m) { $l = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss.fff"), $m; Write-Host $l }

$pre = Get-Process -Name KeySteam -ErrorAction SilentlyContinue
if ($pre) { W "ABORT: KeySteam already running"; exit 1 }

W "launching sample"
$proc = Start-Process -FilePath $Sample -WorkingDirectory (Split-Path $Sample) -PassThru
W "sample pid=$($proc.Id)"

$gui = 0
$t0 = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt 12) {
    Start-Sleep -Milliseconds 150
    $cands = Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
             Where-Object { $_.ExecutablePath -like 'D:\03_Work\03_Develop\KeySteam v2.99\*' -and
                            $_.ExecutablePath -notlike '*\_re\probe\*' }
    foreach ($c in $cands) {
        if ($c.ProcessId -ne $proc.Id) { $gui = $c.ProcessId }
    }
    if ($gui) { break }
}
W "gui candidate pid=$gui"

Start-Sleep -Milliseconds 500
$aclOut = "$outDir\acltest.txt"
$p = Start-Process -FilePath $AclExe -PassThru -RedirectStandardOutput $aclOut -NoNewWindow
$p | Wait-Process -Timeout 30 -ErrorAction SilentlyContinue

W "=== acltest output ==="
if (Test-Path $aclOut) { Get-Content $aclOut | ForEach-Object { Write-Host $_ } }

$mine = Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -like 'D:\03_Work\03_Develop\KeySteam v2.99\*' -and
                       $_.ExecutablePath -notlike '*\_re\probe\*' }
foreach ($m in $mine) {
    W "killing mine pid=$($m.ProcessId)"
    Stop-Process -Id $m.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 900
$left = Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -like 'D:\03_Work\03_Develop\KeySteam v2.99\*' -and
                       $_.ExecutablePath -notlike '*\_re\probe\*' }
if ($left) { W "MY RESIDUAL: $($left.ProcessId -join ',')" } else { W "MY RESIDUAL: none" }

$other = Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
         Where-Object { $_.ExecutablePath -like '*\_re\probe\*' }
W "OTHER(peer) procs still alive: $(if ($other) { ($other.ProcessId -join ',') } else { 'none' })"

$allpipes = [System.IO.Directory]::GetFiles("\\.\pipe\") | Where-Object { $_ -match 'keysteam' }
W "all keysteam pipes: $(if ($allpipes) { $allpipes -join ', ' } else { 'none' })"
W "outDir: $outDir"
