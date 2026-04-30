# Optional: watches the repo and commits after writes (covers manual saves, external edits).
# Run from repo:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/auto_git_watch.ps1
param(
    [int]$DebounceMs = 5000
)

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot

$ctx = @{
    Timer    = (New-Object System.Timers.Timer)
    RepoRoot = $repoRoot
}
$ctx.Timer.AutoReset = $false
$ctx.Timer.Interval = [double]$DebounceMs

$null = Register-ObjectEvent -InputObject $ctx.Timer -EventName Elapsed -SourceIdentifier AutoGitCommitTick -Action {
    Set-Location $Event.MessageData.RepoRoot
    git add -A 2>$null
    if (-not (git diff --cached --quiet 2>$null)) {
        $msg = "chore: auto-commit $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        git commit -m $msg 2>$null
        if ($LASTEXITCODE -eq 0) { Write-Host "[auto_git_watch] $msg" }
    }
} -MessageData $ctx

$handler = {
    $path = $Event.SourceEventArgs.FullPath
    $root = $Event.MessageData.RepoRoot
    if ($path) {
        $rel = $path.Substring($root.Length).TrimStart('\', '/')
        if ($rel -match '^(?:\.git)(?:/|\\)' -or
            $rel -match '^(?:\.venv)(?:/|\\)' -or
            $rel -match '__pycache__' -or
            $rel -match '\.ipynb_checkpoints') { return }
    }
    $Event.MessageData.Timer.Stop()
    $Event.MessageData.Timer.Start()
}

$watcher = New-Object System.IO.FileSystemWatcher
$watcher.Path = $repoRoot
$watcher.Filter = '*.*'
$watcher.IncludeSubdirectories = $true
$watcher.NotifyFilter = [System.IO.NotifyFilters]::FileName -bor [System.IO.NotifyFilters]::LastWrite -bor [System.IO.NotifyFilters]::CreationTime

$null = Register-ObjectEvent -InputObject $watcher -EventName Created -SourceIdentifier AutoGitFsCreate -Action $handler -MessageData $ctx
$null = Register-ObjectEvent -InputObject $watcher -EventName Changed -SourceIdentifier AutoGitFsChanged -Action $handler -MessageData $ctx
$null = Register-ObjectEvent -InputObject $watcher -EventName Renamed -SourceIdentifier AutoGitFsRenamed -Action $handler -MessageData $ctx

$watcher.EnableRaisingEvents = $true
Write-Host "[auto_git_watch] Watching $repoRoot (debounce ${DebounceMs}ms). Ctrl+C to stop."
try {
    while ($true) { Start-Sleep -Seconds 3600 }
}
finally {
    $watcher.EnableRaisingEvents = $false
    $watcher.Dispose()
    Unregister-Event -SourceIdentifier AutoGitFsCreate -ErrorAction SilentlyContinue
    Unregister-Event -SourceIdentifier AutoGitFsChanged -ErrorAction SilentlyContinue
    Unregister-Event -SourceIdentifier AutoGitFsRenamed -ErrorAction SilentlyContinue
    Unregister-Event -SourceIdentifier AutoGitCommitTick -ErrorAction SilentlyContinue
    $ctx.Timer.Dispose()
}
