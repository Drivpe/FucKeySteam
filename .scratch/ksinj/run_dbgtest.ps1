param(
    [string]$Sample = "D:\03_Work\03_Develop\KeySteam v2.99\KeySteam.exe",
    [string]$Exe    = "D:\03_Work\03_Develop\FucKeySteam\.scratch\ksinj\dbgtest.exe",
    [int]$DurMs     = 9000
)
$ErrorActionPreference = "Continue"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outDir = "$env:TEMP\ks_re\dbgtest-$stamp"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
function W([string]$m) { $l = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss.fff"), $m; Write-Host $l }

$pre = Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
       Where-Object { $_.ExecutablePath -like 'D:\03_Work\03_Develop\KeySteam v2.99\*' -and
                      $_.ExecutablePath -notlike '*\_re\probe\*' }
if ($pre) { W "ABORT: my sample already running"; exit 1 }

W "launching sample"
$proc = Start-Process -FilePath $Sample -WorkingDirectory (Split-Path $Sample) -PassThru
W "sample bootstrap pid=$($proc.Id)"

$out = "$outDir\dbgtest.txt"
$p = Start-Process -FilePath $Exe -ArgumentList "$DurMs" -PassThru `
     -RedirectStandardOutput $out -NoNewWindow
$p | Wait-Process -Timeout 60 -ErrorAction SilentlyContinue

W "=== dbgtest output ==="
if (Test-Path $out) { Get-Content $out | ForEach-Object { Write-Host $_ } }

$mine = Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -like 'D:\03_Work\03_Develop\KeySteam v2.99\*' -and
                       $_.ExecutablePath -notlike '*\_re\probe\*' }
foreach ($m in $mine) { W "kill mine pid=$($m.ProcessId)"; Stop-Process -Id $m.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 900
$left = Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -like 'D:\03_Work\03_Develop\KeySteam v2.99\*' -and
                       $_.ExecutablePath -notlike '*\_re\probe\*' }
W "MY RESIDUAL: $(if ($left) { $left.ProcessId -join ',' } else { 'none' })"
$other = Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
         Where-Object { $_.ExecutablePath -like '*\_re\probe\*' }
W "PEER procs: $(if ($other) { $other.ProcessId -join ',' } else { 'none' })"
W "outDir: $outDir"
