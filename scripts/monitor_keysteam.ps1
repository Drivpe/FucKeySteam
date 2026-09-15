# KeySteam 实测监控脚本（PowerShell）
#
# 用途：在实际运行 KeySteam 时，同时监控
#   1. 守护进程（keysteam-runtime-guard / 命名管道）
#   2. 对 key.steamofl.com 的网络连接
#   3. 弹窗与完整性锁的迹象（窗口标题）
#   4. 数据目录（Shikieiki）文件变化
#
# 全部为只读观测，不修改任何东西。在 Windows 侧运行：
#   powershell -ExecutionPolicy Bypass -File monitor_keysteam.ps1 -Seconds 60

# 2026-09-15 追加两个监控目标（注释必须在 param 块之外：
# PowerShell 的 param 块内插入 # 注释会破坏解析）：
#   -StubDir        样本会清理 config/stplug-in/（静态确证），该目录变化是
#                   「样本 cleanup 逻辑已触发」的直接信号，而删除操作事后
#                   find 看不出来，必须实时观测。
#   -MainAccountDir 主号目录写入监控（主号保护实测验证）。本轮约束是
#                   「别动 zdk84214」，静态结论是不写，这条监控是对该结论
#                   的实测验证——写入则当场知道。
param(
    [int]$Seconds = 60,
    [string]$DataDir = "$env:APPDATA\Shikieiki",
    [string]$LogDir  = "$env:TEMP\ks_re",
    [string]$StubDir = "D:\02_Games\01_Steam\Steam\config\stplug-in",
    [string]$MainAccountDir = "D:\02_Games\01_Steam\Steam\userdata\1398488476"
)

$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$log   = Join-Path $LogDir "monitor-$stamp.log"

function W([string]$m) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss.fff"), $m
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding UTF8
}

W "=== 监控开始，时长 ${Seconds}s ==="
W "数据目录: $DataDir"
W "插件目录: $StubDir"
W "主号目录: $MainAccountDir"
W "日志文件: $log"

# --- 基线快照 ---
$base = @{}
if (Test-Path $DataDir) {
    Get-ChildItem -Path $DataDir -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        $base[$_.FullName] = $_.LastWriteTimeUtc.Ticks
    }
}

# 插件目录基线：记录每个文件的哈希，删除/改写都能判读。
$stubBase = @{}
if (Test-Path $StubDir) {
    Get-ChildItem -Path $StubDir -File -ErrorAction SilentlyContinue | ForEach-Object {
        $stubBase[$_.FullName] = (Get-FileHash $_.FullName -Algorithm MD5).Hash
    }
}
W "插件目录基线文件数: $($stubBase.Count)"

# 主号目录基线：只记 mtime，够判断是否被写。
$mainBase = @{}
if (Test-Path $MainAccountDir) {
    Get-ChildItem -Path $MainAccountDir -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        $mainBase[$_.FullName] = $_.LastWriteTimeUtc.Ticks
    }
}
W "主号目录基线文件数: $($mainBase.Count)"
W "数据目录基线文件数: $($base.Count)"

$seenProcs   = @{}
$seenConns   = @{}
$seenWindows = @{}

# 观察名单（2026-09-15 统一）。原脚本用 `-like "*$_*"` 子串匹配，
# 导致 nutstore_watchdog 被当成「守护进程出现」记录下来——
# 与 host.c 里 wcsstr(...,".dll") 是同一类错误。改为精确比对。
$watchProcs = @("host", "keysteam", "keysteam-runtime-guard",
                "guard", "watchdog", "kst", "python", "python312", "steam")
function Test-Watched([string]$name) {
    $n = $name.ToLowerInvariant()
    return ($script:watchProcs -contains $n) -or ($n -match '^python3\d+$')
}

for ($i = 0; $i -lt $Seconds; $i++) {

    # --- 1. 进程：守护进程 / KeySteam 本体 ---
    Get-Process -ErrorAction SilentlyContinue | Where-Object {
        Test-Watched $_.ProcessName
    } | ForEach-Object {
        $key = "$($_.Id):$($_.ProcessName)"
        if (-not $seenProcs.ContainsKey($key)) {
            $seenProcs[$key] = $true
            W "进程出现: PID=$($_.Id) 名称=$($_.ProcessName) 路径=$($_.Path)"
        }
    }

    # --- 2. 命名管道：keysteam_guard_ ---
    try {
        $pipes = [System.IO.Directory]::GetFiles("\\.\pipe\")
        $pipes | Where-Object { $_ -match "keysteam" } | ForEach-Object {
            $key = "pipe:$_"
            if (-not $seenConns.ContainsKey($key)) {
                $seenConns[$key] = $true
                W "命名管道: $_"
            }
        }
    } catch { }

    # --- 3. 网络：只记与本次运行相关的进程 ---
    # 2026-09-15 修正两处：
    #  (a) 原先无条件枚举全系统连接，冒烟测试显示会把 wegame / Nutstore /
    #      firefox / Clash / SiYuan 等无关外连全部写进日志，淹没样本行为。
    #  (b) 第一版过滤用 `-like "*$w*"` 子串匹配，结果 svchost 与
    #      StartMenuExperienceHost 因含 "host" 子串被误判为宿主。
    #      这与 host.c 里 wcsstr(...,".dll") 的脆弱点是同一类错误——
    #      子串匹配当精确匹配用。观察名单与判定已提到循环外统一（Test-Watched）。
    try {
        Get-NetTCPConnection -ErrorAction SilentlyContinue |
            Where-Object { $_.State -eq "Established" -or $_.State -eq "SynSent" } |
            ForEach-Object {
                $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
                $pn = if ($p) { $p.ProcessName } else { "?" }
                if (-not (Test-Watched $pn)) { return }
                $key = "$pn|$($_.RemoteAddress):$($_.RemotePort)"
                if (-not $seenConns.ContainsKey($key)) {
                    $seenConns[$key] = $true
                    W "网络连接: $pn -> $($_.RemoteAddress):$($_.RemotePort)  state=$($_.State)"
                }
            }
    } catch {
        W "WARN: Get-NetTCPConnection 失败，回退 netstat（netstat 无进程名，将全量记录）"
        $ns = & netstat.exe -ano 2>$null | Select-String "ESTABLISHED|SYN_SENT"
        foreach ($l in $ns) {
            $s = ($l -replace "\s+", " ").Trim()
            if ($s -match "TCP (\S+):(\d+) (\S+):(\d+)") {
                $key = $Matches[3] + ":" + $Matches[4]
                if (-not $seenConns.ContainsKey($key)) {
                    $seenConns[$key] = $true
                    W "netstat: $key"
                }
            }
        }
    }

    # --- 4. 窗口：弹窗与完整性锁标题 ---
    # 2026-09-15 修正：判据是「标题为 倒卖可耻 的窗口是否出现」以及
    # 验证码弹窗（VerificationDialog）是否出现。原先无条件记录全系统
    # 窗口标题，冒烟测试显示 firefox / Word / 微信 / Notepad 等全部入日志。
    # 改为两级：关键标题无条件记录（命中即重点），其余只在该窗口属于
    # 观察名单进程时才记。
    try {
        Get-Process -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowTitle -ne "" } |
            ForEach-Object {
                $t = $_.MainWindowTitle
                # 关键判据：无条件记录。
                # 注意 "KeySteam" 这条会命中任何标题含该串的窗口（例如
                # 浏览器标签页正在显示本项目的讨论）。这是有意偏保守的
                # 取舍：宁可多报一次误报，也不要漏掉样本的窗口。
                $critical = ($t -match '倒卖可耻') -or ($t -match 'Verification') -or
                            ($t -match 'KeySteam') -or ($t -match '验证')
                $fromWatched = Test-Watched $_.ProcessName
                if (-not ($critical -or $fromWatched)) { return }
                $key = "$($_.ProcessName):$t"
                if (-not $seenWindows.ContainsKey($key)) {
                    $seenWindows[$key] = $true
                    if ($critical) {
                        W "!!! 关键窗口: 进程=$($_.ProcessName) 标题=`"$t`""
                    } else {
                        W "窗口: 进程=$($_.ProcessName) 标题=`"$t`""
                    }
                }
            }
    } catch { }

    # --- 5. 数据目录变化 ---
    if (Test-Path $DataDir) {
        Get-ChildItem -Path $DataDir -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
            $t = $_.LastWriteTimeUtc.Ticks
            if (-not $base.ContainsKey($_.FullName)) {
                $base[$_.FullName] = $t
                W "新增文件: $($_.FullName)"
            } elseif ($base[$_.FullName] -ne $t) {
                $base[$_.FullName] = $t
                W "文件修改: $($_.FullName)"
            }
        }
    }

    # --- 6. 插件目录变化（样本 cleanup 逻辑的信号）---
    # 用哈希而不是 mtime：删除与改写都要能判读，
    # 且样本可能用「先删再写」的方式清理，mtime 分辨不出。
    if (Test-Path $StubDir) {
        $now = @{}
        Get-ChildItem -Path $StubDir -File -ErrorAction SilentlyContinue | ForEach-Object {
            $now[$_.FullName] = (Get-FileHash $_.FullName -Algorithm MD5).Hash
        }
        foreach ($f in $stubBase.Keys) {
            if (-not $now.ContainsKey($f)) {
                W "插件被删除: $f"
                $stubBase.Remove($f) | Out-Null
            } elseif ($now[$f] -ne $stubBase[$f]) {
                W "插件被改写: $f"
                $stubBase[$f] = $now[$f]
            }
        }
        foreach ($f in $now.Keys) {
            if (-not $stubBase.ContainsKey($f)) {
                $stubBase[$f] = $now[$f]
                W "插件新增: $f"
            }
        }
    } elseif ($stubBase.Count -gt 0) {
        W "插件目录整目录消失: $StubDir"
        $stubBase.Clear()
    }

    # --- 7. 主号目录写入监控（主号保护的实测验证）---
    if (Test-Path $MainAccountDir) {
        Get-ChildItem -Path $MainAccountDir -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
            $t = $_.LastWriteTimeUtc.Ticks
            if (-not $mainBase.ContainsKey($_.FullName)) {
                $mainBase[$_.FullName] = $t
                W "!!! 主号目录新增文件: $($_.FullName)"
            } elseif ($mainBase[$_.FullName] -ne $t) {
                $mainBase[$_.FullName] = $t
                W "!!! 主号目录文件被修改: $($_.FullName)"
            }
        }
    }

    Start-Sleep -Milliseconds 500
}

W "=== 监控结束 ==="
W "进程数=$($seenProcs.Count) 连接数=$($seenConns.Count) 窗口数=$($seenWindows.Count)"
W "插件目录剩余文件数=$($stubBase.Count)"
W "主号目录文件数=$($mainBase.Count)"
W "日志: $log"
