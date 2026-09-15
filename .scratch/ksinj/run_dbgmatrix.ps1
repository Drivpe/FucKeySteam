param(
    [string]$Sample = "D:\03_Work\03_Develop\KeySteam v2.99\KeySteam.exe",
    [string]$Exe    = "D:\03_Work\03_Develop\keysteam-unlock-spike\.scratch\ksinj\dbgmatrix.exe"
)
$ErrorActionPreference = "Continue"
$stamp  = Get-Date -Format "yyyyMMdd-HHmmss"
$outDir = "$env:TEMP\ks_re\dbgmatrix-$stamp"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
function W([string]$m) { $l = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss.fff"), $m; Write-Host $l }

$pre = Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
       Where-Object { $_.ExecutablePath -like 'D:\03_Work\03_Develop\KeySteam v2.99\*' -and
                      $_.ExecutablePath -notlike '*\_re\probe\*' }
if ($pre) { W "ABORT: sample running"; exit 1 }

$np = Start-Process notepad.exe -PassThru
W "notepad pid=$($np.Id)"
Start-Sleep -Milliseconds 1200

$proc = Start-Process -FilePath $Sample -WorkingDirectory (Split-Path $Sample) -PassThru
W "bootstrap pid=$($proc.Id)"

$gui = 0; $t0 = Get-Date
while (((Get-Date) - $t0).TotalSeconds -lt 20) {
    Start-Sleep -Milliseconds 200
    foreach ($c in (Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
                    Where-Object { $_.ExecutablePath -like 'D:\03_Work\03_Develop\KeySteam v2.99\*' -and
                                   $_.ExecutablePath -notlike '*\_re\probe\*' })) {
        $pp = Get-Process -Id $c.ProcessId -ErrorAction SilentlyContinue
        if ($pp -and $pp.MainWindowHandle -ne 0) { $gui = $c.ProcessId; break }
    }
    if ($gui) { break }
}
W "GUI pid = $gui"
Start-Sleep -Milliseconds 1500

$out = "$outDir\dbgmatrix.txt"
$p = Start-Process -FilePath $Exe -PassThru -RedirectStandardOutput $out -NoNewWindow
$p | Wait-Process -Timeout 60 -ErrorAction SilentlyContinue

W "=== dbgmatrix output ==="
if (Test-Path $out) { Get-Content $out | ForEach-Object { Write-Host $_ } }

# 主号目录基线核对
$ma = "D:\02_Games\01_Steam\Steam\userdata\1398488476"
$cnt = (Get-ChildItem $ma -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
W "main account files = $cnt"
$stub = "D:\02_Games\01_Steam\Steam\config\stplug-in"
$sc = (Get-ChildItem $stub -File -ErrorAction SilentlyContinue | Measure-Object).Count
W "stplug-in files = $sc"

foreach ($m in (Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
                Where-Object { $_.ExecutablePath -like 'D:\03_Work\03_Develop\KeySteam v2.99\*' -and
                               $_.ExecutablePath -notlike '*\_re\probe\*' })) {
    W "kill mine pid=$($m.ProcessId)"; Stop-Process -Id $m.ProcessId -Force -ErrorAction SilentlyContinue
}
Stop-Process -Id $np.Id -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 900
$left = Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -like 'D:\03_Work\03_Develop\KeySteam v2.99\*' -and
                       $_.ExecutablePath -notlike '*\_re\probe\*' }
W "MY RESIDUAL: $(if ($left) { $left.ProcessId -join ',' } else { 'none' })"
$other = Get-CimInstance Win32_Process -Filter "Name LIKE 'KeySteam%'" -ErrorAction SilentlyContinue |
         Where-Object { $_.ExecutablePath -like '*\_re\probe\*' }
W "PEER procs: $(if ($other) { $other.ProcessId -join ',' } else { 'none' })"
W "outDir: $outDir"
