#requires -Version 7.0
param([string]$Executable = (Join-Path $PSScriptRoot '..\dist\TubeScholar\TubeScholar.exe'))
$ErrorActionPreference = 'Stop'
$taskExe = (Resolve-Path -LiteralPath $Executable).Path
$taskRepo = Split-Path $PSScriptRoot -Parent
$taskProfile = Join-Path $taskRepo ('build\smoke-' + [guid]::NewGuid().ToString('N'))
$taskHeaders = @{ 'x-tubescholar' = '1' }
$taskBase = 'http://127.0.0.1:8000'
$taskProbe = [Net.Sockets.TcpClient]::new()
try {
    $taskOccupied = $taskProbe.ConnectAsync('127.0.0.1', 8000)
    if ($taskOccupied.Wait(1000) -and $taskProbe.Connected) {
        throw 'Port 8000 is already in use; stop the existing app before running this smoke test.'
    }
} catch [AggregateException] {
    # Connection refused means the test port is available.
} finally {
    $taskProbe.Dispose()
}
New-Item -ItemType Directory -Path $taskProfile -Force | Out-Null
$taskInfo = [Diagnostics.ProcessStartInfo]::new()
$taskInfo.FileName = $taskExe
$taskInfo.UseShellExecute = $false
$taskInfo.CreateNoWindow = $true
$taskInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
$taskInfo.EnvironmentVariables['LOCALAPPDATA'] = $taskProfile
$taskInfo.EnvironmentVariables['TUBESCHOLAR_DATA_DIR'] = Join-Path $taskProfile 'data'
$taskInfo.EnvironmentVariables['TUBESCHOLAR_NO_BROWSER'] = '1'
foreach ($taskKey in @('GEMINI_API_KEY', 'GOOGLE_API_KEY', 'GROQ_API_KEY')) {
    $taskInfo.EnvironmentVariables[$taskKey] = ''
}
$taskProcess = [Diagnostics.Process]::Start($taskInfo)
try {
    $taskReady = $false
    for ($taskAttempt = 0; $taskAttempt -lt 40; $taskAttempt++) {
        if ($taskProcess.HasExited) { throw "Packaged app exited: $($taskProcess.ExitCode)" }
        try {
            $taskHealth = Invoke-RestMethod "$taskBase/api/system/health" -TimeoutSec 1
            if ($taskHealth.status -eq 'ok') { $taskReady = $true; break }
        } catch {}
        Start-Sleep -Milliseconds 250
    }
    if (-not $taskReady) { throw 'Packaged app did not become ready.' }
    $taskPage = Invoke-WebRequest $taskBase -TimeoutSec 5
    if ($taskPage.Content -notmatch 'app.js\?v=3.8.2') { throw 'Stale frontend was packaged.' }
    $taskId = [guid]::NewGuid().ToString('N')
    $taskHeaders['x-analysis-id'] = $taskId
    $taskBody = @{title='Packaged smoke'; subtitle_text="1`n00:00:00,000 --> 00:00:02,000`nSmoke dialogue.`n"} | ConvertTo-Json
    $taskResponse = Invoke-WebRequest "$taskBase/api/local/analyze" -Method Post -Headers $taskHeaders -ContentType 'application/json' -Body $taskBody -SkipHttpErrorCheck -TimeoutSec 10
    if ([int]$taskResponse.StatusCode -ne 500) { throw 'Expected missing-key error in isolated profile.' }
    $taskState = Invoke-RestMethod "$taskBase/api/analysis/status?job_id=$taskId" -TimeoutSec 5
    if ($taskState.status -ne 'error' -or -not $taskState.checkpoint_note_id) { throw 'Job state or checkpoint missing.' }
    $taskNote = Invoke-RestMethod "$taskBase/api/notes/$($taskState.checkpoint_note_id)" -TimeoutSec 5
    if ($taskNote.metadata.subtitles[0].text -ne 'Smoke dialogue.') { throw 'Checkpoint subtitle mismatch.' }
    if ($taskProcess.HasExited) { throw 'Packaged app exited unexpectedly.' }
    Write-Output "Packaged smoke OK: startup, static frontend, job lifecycle and transcript persistence. PID=$($taskProcess.Id)"
    Write-Output "Isolated profile: $taskProfile"
} finally {
    # Only terminate the process created by this test; never touch an installed app.
    if (-not $taskProcess.HasExited) { Stop-Process -Id $taskProcess.Id -Force }
    $taskProcess.Dispose()
}
