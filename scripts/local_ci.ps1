# local_ci.ps1 — 本地 CI 等价一键回归（批12.5 / A2）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\local_ci.ps1 [-SkipPlaywright]
# 内容：停服清库 -> 起双服(28000/8090) -> 12 套 E2E -> 停服清库 -> 单测 -> 静态检查
#        -> 起 8123 -> Playwright 全量 -> 汇总（任一失败 Exit 1）
param(
    [switch]$SkipPlaywright,
    [switch]$SkipE2E,
    # 批42 修复#7：Playwright 步骤端口可覆盖（默认 8123 与文档一致）。
    # 本机其他进程（micont_service）抢占 8123 源端口时用 -WebPort 8125 之类绕开。
    [int]$WebPort = 8123
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$fail = @()

function Say($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Check($name, $ok) {
    if ($ok) { Write-Host "[PASS] $name" -ForegroundColor Green }
    else     { Write-Host "[FAIL] $name" -ForegroundColor Red; $script:fail += $name }
}
function Stop-Serve {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match 'serve\.py' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 600
}
function Clean-Persist { if (Test-Path 'data\persist_rooms.json') { Remove-Item 'data\persist_rooms.json' -Force } }
function Start-Serve([int]$port) {
    $env:PORT = "$port"
    # 批42 修复#7：本机 CI 绑 127.0.0.1，免疫其他进程抢占同号源端口（bind 10048）
    $env:HOST = '127.0.0.1'
    Start-Process -FilePath '.venv\Scripts\python.exe' -ArgumentList 'serve.py' -WindowStyle Hidden
    # 等端口就绪
    foreach ($i in 1..40) {
        Start-Sleep -Milliseconds 250
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
    }
    return $false
}

Say "0/5 停服 + 清持久化"
Stop-Serve; Clean-Persist
Check "清理完成" $true

if (-not $SkipE2E) {
    Say "1/5 双服起 (28000 / 8090)"
    $ok1 = Start-Serve 28000
    $ok2 = Start-Serve 8090
    Check "服1 28000 / 200" $ok1
    Check "服2 8090 / 200" $ok2

    if ($ok1 -and $ok2) {
        Say "2/5 12 套 E2E"
        $suites = @('test_ws.py','test_ws2.py','verify_rooms.py','test_p1.py',
                    'test_bots_p4.py','test_reconnect_p5.py','test_pass_p6.py','test_delta_p1.py',
                    'test_reactions_p33.py', 'test_ws3.py', 'test_ws4.py', 'test_fall_p46.py')
        foreach ($s in $suites) {
            $out = & '.venv\Scripts\python.exe' $s 2>&1 | Out-String
            $code = $LASTEXITCODE
            $tail = ($out -split "`n" | Where-Object { $_ -match '\S' } | Select-Object -Last 1)
            Write-Host "  $s -> Exit $code | $tail"
            Check "E2E $s" ($code -eq 0)
        }
    }

    Say "3/5 停服 + 清持久化"
    Stop-Serve; Clean-Persist
}

Say "4/5 单测 test_game.py"
$u = & '.venv\Scripts\python.exe' 'test_game.py' 2>&1 | Out-String
$ucode = $LASTEXITCODE
Write-Host (($u -split "`n" | Select-Object -Last 8) -join "`n")
Check "单测 ($([string]$ucode))" ($ucode -eq 0)

Say "4.5/5 前端静态检查"
$staticJs = Join-Path $root 'scripts\static_check.js'
if (Test-Path $staticJs) {
    $s = & node $staticJs 'index.html' 2>&1 | Out-String
    $scode = $LASTEXITCODE
    Write-Host ($s.Trim())
    Check "静态检查" ($scode -eq 0 -and $s -match 'ALL STATIC CHECKS PASSED')
} else {
    Write-Host "  (static_check.js 缺失)" -ForegroundColor Red
    Check "静态检查(缺失)" $false
}

if (-not $SkipPlaywright) {
    Say "5/5 Playwright 全量 ($WebPort)"
    Stop-Serve
    $ok = Start-Serve $WebPort
    if ($ok) {
        $env:BASE = "http://127.0.0.1:$WebPort"
        $p = & npx playwright test 2>&1 | Out-String
        $pcode = $LASTEXITCODE
        Write-Host (($p -split "`n" | Where-Object { $_ -match 'passed|failed|error' } | Select-Object -Last 5) -join "`n")
        Check "Playwright" ($pcode -eq 0)
    } else {
        Check "$WebPort 起服" $false
    }
    Stop-Serve; Clean-Persist
}

Say "汇总"
if ($fail.Count -eq 0) {
    Write-Host "ALL GREEN — 本地 CI 全部通过" -ForegroundColor Green
    exit 0
} else {
    Write-Host "FAILED ($($fail.Count)):" -ForegroundColor Red
    $fail | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}
