# Cursor hook: staged commit after agent/tab file edits. Project root is CWD.
$ErrorActionPreference = 'SilentlyContinue'
$reader = New-Object System.IO.StreamReader([Console]::OpenStandardInput())
$null = $reader.ReadToEnd()
$reader.Close()

$repoRoot = git rev-parse --show-toplevel 2>$null
if (-not $repoRoot) { Write-Output '{}'; exit 0 }

Set-Location $repoRoot

$debounceMs = 4000
$stampPath = Join-Path $env:TEMP 'langgraph_study_cursor_auto_commit.stamp'
$nowMs = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
if (Test-Path $stampPath) {
    try {
        $last = [int64]((Get-Content -Raw $stampPath).Trim())
        if (($nowMs - $last) -lt $debounceMs) { Write-Output '{}'; exit 0 }
    }
    catch {}
}
Set-Content -Path $stampPath -Value ([string]$nowMs) -NoNewline

git add -A 2>$null
if (git diff --cached --quiet 2>$null) { Write-Output '{}'; exit 0 }

$msg = "chore: auto-commit $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
git commit -m $msg 2>$null
Write-Output '{}'
exit 0
