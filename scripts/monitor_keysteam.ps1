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
    [string]$MainAccountDir = "D:\02_Games\01_Steam\Steam\userdata\1398488476",
    [int]$TightLoopMs = 0,
    [string]$ResolveHost = "key.steamofl.com"
)

$ErrorActionPreference = "Continue"

# --- 窗口枚举辅助（user32 EnumWindows）------------------------------
#
# 为什么不用 Get-Process 的 MainWindowTitle：它每个进程只报一个主窗口。
# 验证码弹窗是同一进程内的 Qt 模态对话框，会被整个漏掉（2026-09-15 实测）。
# 返回每行的字段顺序：pid, hwnd, visible, enabled, class, title
Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public class KsWinEnum {
  delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc e, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint p);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] static extern bool IsWindowEnabled(IntPtr h);
  public static List<string[]> All() {
    var res = new List<string[]>();
    EnumWindows(delegate(IntPtr h, IntPtr l) {
      var tb = new StringBuilder(512); GetWindowTextW(h, tb, 512);
      var cb = new StringBuilder(256); GetClassNameW(h, cb, 256);
      uint pid; GetWindowThreadProcessId(h, out pid);
      res.Add(new string[] {
        pid.ToString(), h.ToInt64().ToString("X"),
        IsWindowVisible(h).ToString(), IsWindowEnabled(h).ToString(),
        cb.ToString(), tb.ToString()
      });
      return true;
    }, IntPtr.Zero);
    return res;
  }
}
"@

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$log   = Join-Path $LogDir "monitor-$stamp.log"

function W([string]$m) {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss.fff"), $m
    Write-Host $line
    Add-Content -Path $log -Value $line -Encoding UTF8
}

if ($Seconds -lt 0) {
    W "=== 监控开始，等待宿主模式（-Seconds $Seconds）==="
} else {
    W "=== 监控开始，时长 ${Seconds}s ==="
}
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
$seenTarget  = @{}   # 目标 IP 专用去重表（与 $seenConns 分离）

# --- 紧循环观测的两项前提（2026-09-15 追加，#7 问题一）------
#
# 目标 IP：Get-NetTCPConnection 只给 IP 不给主机名，所以判据是
# 「是否连到该 IP」。解析失败不算错误——只意味着本次无法用 IP 判据。
$targetIps = @()
if ($ResolveHost) {
    try {
        $targetIps = @(
            Resolve-DnsName $ResolveHost -Type A -QuickTimeout -ErrorAction SilentlyContinue |
                Where-Object { $_.IPAddress } |
                ForEach-Object { $_.IPAddress } |
                Select-Object -Unique
        )
    } catch { }
    if ($targetIps.Count -gt 0) {
        W "[DNS] 解析 $ResolveHost -> $($targetIps -join ', ')"
    } else {
        W "[DNS] WARN: 无法解析 $ResolveHost，本次运行无 IP 判据"
    }
}

# DNS 缓存基线：缓存条目没有查询时间戳（字段只有 Entry/Data/TTL/Status），
# 所以「本次是否发起过解析」只能靠运行前后的差集，不能靠「某时刻缓存里有它」。
$dnsBase = @{}
try {
    Get-DnsClientCache -ErrorAction SilentlyContinue | ForEach-Object {
        $dnsBase["$($_.Entry)|$($_.Data)"] = $true
    }
} catch { }
W "[DNS] 缓存基线条目数: $($dnsBase.Count)"

# 紧循环间隔的判读说明。实测一次完整采样（Get-Process + Get-NetTCPConnection）
# 约 224 ms，所以原 -Milliseconds 500 的真实周期约 724 ms，
# 而样本从进程出现到弹窗只活 2.09 秒 —— 约 3 个采样点。
# 这是早先「未捕捉到持续 ≥500ms 的外连」这一结论归因能力弱的直接原因。
$sleepMs = if ($TightLoopMs -eq 0) { 500 }
           elseif ($TightLoopMs -lt 0) { 0 }
           else { $TightLoopMs }
W "采样间隔: ${sleepMs}ms（0 = 尽可能快；单次采样实测约 224ms）"

# 观察名单（2026-09-15 统一）。原脚本用 `-like "*$_*"` 子串匹配，
# 导致 nutstore_watchdog 被当成「守护进程出现」记录下来——
# 与 host.c 里 wcsstr(...,".dll") 是同一类错误。改为精确比对。
$watchProcs = @("host", "keysteam", "keysteam-runtime-guard",
                "guard", "watchdog", "kst", "python", "python312", "steam")
function Test-Watched([string]$name) {
    $n = $name.ToLowerInvariant()
    return ($script:watchProcs -contains $n) -or ($n -match '^python3\d+$')
}

# --- 等待宿主模式（-Seconds -1）---------------------------------------
#
# ★ 2026-09-15 新增：解决人工操作与监控窗口的时序协调问题。
#   固定轮数的监控要求 operator 在窗口期内敲命令，两次实测都错过。
#   本模式下监控持续运行直到检测到 host 出现，然后再多跑
#   $AfterHostRounds 轮后结束——何时启动宿主都不影响观测完整性。
#
#   上限 $MaxWaitRounds 轮（默认约 15 分钟）防止无人启动时无限运行。
$waitMode     = ($Seconds -lt 0)
$AfterHostRounds = 60      # 宿主出现后再跑多少轮（约 5 秒）
$MaxWaitRounds   = 12000   # 等待上限（约 15 分钟）
$hostSeen     = $false
$hostSeenAt   = 0

if ($waitMode) { W "=== 等待宿主模式：检测到 host 出现后再跑 $AfterHostRounds 轮 ===" }

$i = 0
while ($true) {
    if ($waitMode) {
        if ($hostSeen -and ($i - $hostSeenAt) -ge $AfterHostRounds) { break }
        if ($i -ge $MaxWaitRounds) { W "WARN: 等待宿主超时（$MaxWaitRounds 轮），未检测到 host"; break }
    } else {
        if ($i -ge $Seconds) { break }
    }
    $i++

    # --- 0. 进程快照（一次全量，供本循环各段复用）---
    #
    # ★ 2026-09-15 性能：原先各段各自调 Get-Process -Id 单查，而单查同样
    #   要走一次完整进程快照。一轮里最多三次（网络段、目标 IP 段、窗口段），
    #   等于三次全量枚举。改为本处取一次快照、建 PID→Process 映射表。
    $procMap = @{}
    try {
        foreach ($p in (Get-Process -ErrorAction SilentlyContinue)) {
            $procMap[[int]$p.Id] = $p
        }
    } catch { }

    # --- 1. 进程：守护进程 / KeySteam 本体 ---
    foreach ($p in $procMap.Values) {
        if (-not (Test-Watched $p.ProcessName)) { continue }
        $key = "$($p.Id):$($p.ProcessName)"
        if (-not $seenProcs.ContainsKey($key)) {
            $seenProcs[$key] = $true
            W "进程出现: PID=$($p.Id) 名称=$($p.ProcessName) 路径=$($p.Path)"
            # 等待模式下，首次见到 host 即开始收尾倒计时
            if ($waitMode -and -not $hostSeen -and $p.ProcessName -ieq 'host') {
                $hostSeen   = $true
                $hostSeenAt = $i
                W "=== 检测到 host，将在 $AfterHostRounds 轮后结束监控 ==="
            }
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
    #
    # ★ 2026-09-15 性能改动：改用 netstat -ano 抓一次快照（约 19 ms），
    #   供本段与 3b 段共用。原来用 Get-NetTCPConnection（约 213 ms），
    #   它是全脚本最慢的一项，把采样率拖到约 195 ms。
    $nsSnapshot = $null
    try { $nsSnapshot = & netstat.exe -ano 2>$null } catch { }

    if ($nsSnapshot) {
        try {
            foreach ($line in $nsSnapshot) {
                if ($line -notmatch "ESTABLISHED|SYN_SENT") { continue }
                $s = ($line -replace "\s+", " ").Trim()
                # 期望：TCP 本地:端口 远端:端口 STATE PID
                if ($s -notmatch '^TCP\s+(\S+)\s+(\S+)\s+(\S+)\s+(\d+)') { continue }
                $remoteEp = $Matches[2]; $state = $Matches[3]; $roPid = [int]$Matches[4]

                $pn = "?"
                if ($roPid -gt 0 -and $procMap.ContainsKey($roPid)) {
                    $pn = $procMap[$roPid].ProcessName
                }
                if (-not (Test-Watched $pn)) { continue }
                $key = "$pn|$remoteEp|$state"
                if (-not $seenConns.ContainsKey($key)) {
                    $seenConns[$key] = $true
                    W "网络连接: $pn(pid=$roPid) -> $remoteEp  state=$state"
                }
            }
        } catch { W "WARN: 网络段失败: $($_.Exception.Message)" }
    } else {
        W "WARN: netstat 不可用，本轮无网络观测"
    }

    # --- 3b. 目标 IP 专用检测（netstat 高频采样）---
    #
    # ★ 2026-09-15 实测依据（性能）：
    #     Get-NetTCPConnection 每次约 213 ms（走 CIM/WMI）
    #     netstat -ano          每次约 19 ms（原生程序）
    #   11 倍差距直接决定采样率：195 ms vs 30 ms。样本从进程出现到弹窗
    #   只活 2.09 秒，采样点越多越不容易漏掉短命连接。
    #
    # ★ 归属问题：上一轮只抓到 TimeWait 残影，OwningProcess 显示为
    #   Idle(PID 0)，无法归属。netstat -ano 直接给出 PID，且在
    #   Established 状态下有效。所以优先用 netstat，并显式标注归属状态。
    #
    # 独立去重表 $seenTarget：原先与通用网络段共用 $seenConns，可能互相遮盖。
    # 复用 3 段已抓取的 $nsSnapshot，不再二次调用 netstat。
    if ($targetIps.Count -gt 0 -and $nsSnapshot) {
        try {
            $needles = $targetIps | ForEach-Object { "$_`:" }
            foreach ($line in $nsSnapshot) {
                $hit = $false
                foreach ($n in $needles) { if ($line -match [regex]::Escape($n)) { $hit = $true; break } }
                if (-not $hit) { continue }

                $s = ($line -replace "\s+", " ").Trim()
                # 期望：TCP 本地:端口 远端:端口 STATE PID
                if ($s -notmatch '^TCP\s+(\S+)\s+(\S+)\s+(\S+)\s+(\d+)') { continue }
                $localEp = $Matches[1]; $remoteEp = $Matches[2]
                $state = $Matches[3]; $roPid = [int]$Matches[4]

                $key = "$remoteEp|$state|$localEp"
                if ($seenTarget.ContainsKey($key)) { continue }
                $seenTarget[$key] = $true

                $pn = "?"
                $note = ""
                if ($roPid -gt 0) {
                    if ($procMap.ContainsKey($roPid)) {
                        $pn = $procMap[$roPid].ProcessName
                    } else {
                        $note = " [进程已退出]"
                    }
                } else {
                    $note = " [归属丢失]"
                }
                $tag = switch -Regex ($state) {
                    "ESTABLISHED" { "★连接已建立" }
                    "SYN_SENT"    { "★正在建连" }
                    "TIME_WAIT"   { "(残影)" }
                    default       { "" }
                }
                W "[IP] 目标 IP: $pn(pid=$roPid) -> $remoteEp  state=$state $tag$note"
            }
        } catch { W "WARN: 目标 IP 检测失败: $($_.Exception.Message)" }
    }

    # --- 3c. DNS 缓存差分 ---
    # 每轮查一次很贵（WMI 调用），所以低频做：每 10 轮一次。
    # 缓存条目一旦出现会存活一个 TTL（观测到的值在 3000 量级），
    # 所以低频采样不会漏掉「本次运行发起过解析」这一事实。
    if (($i % 10) -eq 0) {
        try {
            Get-DnsClientCache -ErrorAction SilentlyContinue | ForEach-Object {
                $k = "$($_.Entry)|$($_.Data)"
                if (-not $dnsBase.ContainsKey($k)) {
                    $dnsBase[$k] = $true
                    W "[DNS] 新增缓存条目: $($_.Entry) -> $($_.Data)"
                }
            }
        } catch { }
    }

    # --- 4. 窗口：弹窗与完整性锁标题 ---
    # 2026-09-15 修正（第二次）：判据是「标题为 倒卖可耻 的窗口是否出现」以及
    # 验证码弹窗（VerificationDialog）是否出现。原先无条件记录全系统
    # 窗口标题，冒烟测试显示 firefox / Word / 微信 / Notepad 等全部入日志。
    # 改为两级：关键标题无条件记录（命中即重点），其余只在该窗口属于
    # 观察名单进程时才记。
    #
    # ★ 2026-09-15 实测缺陷修复：原先用 `Get-Process | MainWindowTitle`，
    #   它每个进程只报**一个主窗口**。验证码弹窗是同一进程内的 Qt 模态
    #   对话框，不是主窗口——于是被整个漏掉。
    #   证据：本轮 12:26 运行时日志只有「KeySteam v2.99」，而用户现场
    #   确实看到了验证码弹窗并手动关闭；对照上一轮用 EnumWindows 采集的
    #   window-evidence.txt，同一状态下能同时抓到
    #   `KeySteam 验证`（Enabled=True，模态激活）与 `KeySteam v2.99`
    #   （Enabled=False，被禁用）。
    #   改用 user32 EnumWindows，枚举全部顶层窗口。
    try {
        $allWins = [KsWinEnum]::All()
        if ($i -eq 0) {
            $visTitled = ($allWins | Where-Object { $_[2] -eq "True" -and $_[5] -ne "" }).Count
            W "[诊断] 首次窗口枚举: 顶层窗口=$($allWins.Count) 可见且有标题=$visTitled"
        }
        foreach ($w in $allWins) {
            $wpid = [int]$w[0]
            $vis  = $w[2]
            $en   = $w[3]
            $cls  = $w[4]
            $t    = $w[5]
            if ($t -eq "") { continue }           # 无标题（含 _q_titlebar 等）
            if ($vis -ne "True") { continue }     # 不可见的不算

            # 关键判据：无条件记录。
            # 注意 "KeySteam" 这条会命中任何标题含该串的窗口（例如
            # 浏览器标签页正在显示本项目的讨论）。这是有意偏保守的
            # 取舍：宁可多报一次误报，也不要漏掉样本的窗口。
            $critical = ($t -match '倒卖可耻') -or ($t -match 'Verification') -or
                        ($t -match 'KeySteam') -or ($t -match '验证')

            $pn = "?"
            if ($procMap.ContainsKey($wpid)) { $pn = $procMap[$wpid].ProcessName }
            $fromWatched = Test-Watched $pn

            if (-not ($critical -or $fromWatched)) { continue }

            $key = "$wpid|$t|$en"
            if (-not $seenWindows.ContainsKey($key)) {
                $seenWindows[$key] = $true
                if ($critical) {
                    W "!!! 关键窗口: pid=$wpid 进程=$pn 标题=`"$t`" 类=$cls 可见=$vis 启用=$en"
                } else {
                    W "窗口: pid=$wpid 进程=$pn 标题=`"$t`" 类=$cls 可见=$vis 启用=$en"
                }
            }
        }
    } catch { W "WARN: 窗口枚举失败: $($_.Exception.Message)" }

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
    #
    # ★ 2026-09-15 性能：本段每次约 12 ms（5 文件哈希），改低频执行
    #   （每 3 轮一次，紧循环下约 700 ms 间隔）。删除检测对延迟不敏感——
    #   判读用的是「是否发生」而非「精确到毫秒的时刻」。
    if (($i % 3) -eq 0) {
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

    if ($sleepMs -gt 0) { Start-Sleep -Milliseconds $sleepMs }
}

W "=== 监控结束 ==="
W "进程数=$($seenProcs.Count) 连接数=$($seenConns.Count) 窗口数=$($seenWindows.Count)"
W "插件目录剩余文件数=$($stubBase.Count)"
W "主号目录文件数=$($mainBase.Count)"
W "DNS 缓存总条目数=$($dnsBase.Count)"
W "日志: $log"
