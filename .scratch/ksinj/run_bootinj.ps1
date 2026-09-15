param(
    [string]$Sample = "D:\03_Work\03_Develop\KeySteam v2.99\KeySteam.exe",
    [string]$Exe    = "D:\03_Work\03_Develop\keysteam-unlock-spike\.scratch\ksinj\bootinj.exe",
    [string]$Dll    = "D:\03_Work\03_Develop\keysteam-unlock-spike\.scratch\ksinj\payload\ksprobe.dll",
    [int]$DurMs     = 20000
)
$ErrorActionPreference = "Continue"
$stamp  = Get-Date -Format "yyyyMMdd-HHmmss"
$outDir = "$env:TEMP\ks_re\bootinj-$stamp"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
function W([string]$m) { $l = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss.fff"), $m; Write-Host $l }

$pre = Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
       Where-Object { $_.ExecutablePath -like 'D:\03_Work\03_Develop\KeySteam v2.99\*' -and
                      $_.ExecutablePath -notlike '*\_re\probe\*' }
if ($pre) { W "ABORT: sample running"; exit 1 }


$out = "$outDir\bootinj.txt"
$pargs = "`"$Dll`" $DurMs"
W "start probe FIRST: $Exe $pargs"
$p = Start-Process -FilePath $Exe -ArgumentList $pargs -PassThru `
     -RedirectStandardOutput $out -NoNewWindow

Start-Sleep -Milliseconds 700   
W "launch sample"
$proc = Start-Process -FilePath $Sample -WorkingDirectory (Split-Path $Sample) -PassThru
W "bootstrap pid=$($proc.Id)"

$p | Wait-Process -Timeout ($DurMs/1000 + 60) -ErrorAction SilentlyContinue

W "=== bootinj output ==="
if (Test-Path $out) { Get-Content $out | ForEach-Object { Write-Host $_ } }

$ma = "D:\02_Games\01_Steam\Steam\userdata\1398488476"
W "main account files = $((Get-ChildItem $ma -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count)"
W "stplug-in files = $((Get-ChildItem 'D:\02_Games\01_Steam\Steam\config\stplug-in' -File -ErrorAction SilentlyContinue | Measure-Object).Count)"

foreach ($m in (Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
                Where-Object { $_.ExecutablePath -like 'D:\03_Work\03_Develop\KeySteam v2.99\*' -and
                               $_.ExecutablePath -notlike '*\_re\probe\*' })) {
    W "kill mine pid=$($m.ProcessId)"; Stop-Process -Id $m.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Milliseconds 900
$left = Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -like 'D:\03_Work\03_Develop\KeySteam v2.99\*' -and
                       $_.ExecutablePath -notlike '*\_re\probe\*' }
W "MY RESIDUAL: $(if ($left) { $left.ProcessId -join ',' } else { 'none' })"
$other = Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
         Where-Object { $_.ExecutablePath -like '*\_re\probe\*' }
W "PEER procs: $(if ($other) { $other.ProcessId -join ',' } else { 'none' })"
W "outDir: $outDir"
