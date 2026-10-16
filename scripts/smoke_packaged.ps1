#requires -Version 7.0
param(
    [string]$Executable = (Join-Path $PSScriptRoot '..\dist\TubeScholar\TubeScholar.exe'),
    [switch]$VerifyTts
)
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
    if ($taskPage.Content -notmatch 'app.js\?v=3.9.0' -or $taskPage.Content -notmatch 'library.js\?v=1.0.0') { throw 'Stale frontend was packaged.' }
    $taskBundledFrontend = Join-Path (Split-Path $taskExe -Parent) '_internal\frontend'
    foreach ($taskAsset in @('app.js', 'library.js', 'style.css', 'i18n.js', 'index.html')) {
        $taskExpectedHash = (Get-FileHash -LiteralPath (Join-Path $taskRepo "frontend\$taskAsset") -Algorithm SHA256).Hash
        $taskBundledHash = (Get-FileHash -LiteralPath (Join-Path $taskBundledFrontend $taskAsset) -Algorithm SHA256).Hash
        if ($taskExpectedHash -ne $taskBundledHash) { throw "Bundled asset differs from source: $taskAsset" }
    }
    $taskId = [guid]::NewGuid().ToString('N')
    $taskHeaders['x-analysis-id'] = $taskId
    $taskBody = @{title='Packaged smoke'; subtitle_text="1`n00:00:00,000 --> 00:00:02,000`nSmoke dialogue.`n"} | ConvertTo-Json
    $taskResponse = Invoke-WebRequest "$taskBase/api/local/analyze" -Method Post -Headers $taskHeaders -ContentType 'application/json' -Body $taskBody -SkipHttpErrorCheck -TimeoutSec 10
    if ([int]$taskResponse.StatusCode -ne 500) { throw 'Expected missing-key error in isolated profile.' }
    $taskState = Invoke-RestMethod "$taskBase/api/analysis/status?job_id=$taskId" -TimeoutSec 5
    if ($taskState.status -ne 'error' -or -not $taskState.checkpoint_note_id) { throw 'Job state or checkpoint missing.' }
    $taskNote = Invoke-RestMethod "$taskBase/api/notes/$($taskState.checkpoint_note_id)" -TimeoutSec 5
    if ($taskNote.metadata.subtitles[0].text -ne 'Smoke dialogue.') { throw 'Checkpoint subtitle mismatch.' }
    if ($taskPage.Content -match 'id="local-audio-direct-btn"' -or $taskPage.Content -notmatch 'id="local-prompt-status"') { throw 'Unified local dialog missing.' }
    $taskMediaPath = Join-Path $taskProfile 'smoke.mp4'
    [IO.File]::WriteAllBytes($taskMediaPath, [Text.Encoding]::ASCII.GetBytes('packaged-video-fixture'))
    $taskHeaders['x-analysis-id'] = [guid]::NewGuid().ToString('N')
    $taskNoteId = $taskState.checkpoint_note_id
    $taskUpload = Invoke-RestMethod "$taskBase/api/notes/$taskNoteId/video" -Method Post -Headers $taskHeaders -Form @{video=Get-Item -LiteralPath $taskMediaPath} -TimeoutSec 10
    if (-not $taskUpload.success) { throw 'Video attachment failed.' }
    $taskReopened = Invoke-RestMethod "$taskBase/api/notes/$taskNoteId" -TimeoutSec 5
    if (-not $taskReopened.metadata.local_video_available) { throw 'Saved video reference missing.' }
    $taskRange = Invoke-WebRequest "$taskBase/api/notes/$taskNoteId/video" -Headers @{Range='bytes=0-7'} -TimeoutSec 5
    if ([int]$taskRange.StatusCode -ne 206 -or $taskRange.Headers['Content-Range'] -ne 'bytes 0-7/22') { throw 'Saved video range playback failed.' }
    if ($VerifyTts) {
        $taskNarration = "강화학습(RL)은 보상을 바탕으로 학습합니다.`n`n결과는 감소합니다(단, 온도가 일정할 때)."
        $taskEdit = @{markdown=$taskNarration} | ConvertTo-Json
        Invoke-RestMethod "$taskBase/api/notes/$taskNoteId" -Method Put -Headers $taskHeaders -ContentType 'application/json; charset=utf-8' -Body $taskEdit -TimeoutSec 10 | Out-Null
        $taskTtsBody = @{note_id=$taskNoteId; voice='injoon'} | ConvertTo-Json
        $taskTts = Invoke-RestMethod "$taskBase/api/tts/generate" -Method Post -Headers $taskHeaders -ContentType 'application/json' -Body $taskTtsBody -TimeoutSec 60
        $taskCueText = ($taskTts.cues | ForEach-Object { $_.text }) -join ' '
        if (-not $taskTts.success -or $taskTts.filename -notmatch '_v2_injoon_' -or $taskCueText -notmatch '온도가 일정할 때' -or $taskCueText -notmatch '\(RL\)') { throw 'Content-preserving narration failed.' }
        $taskAudio = Invoke-WebRequest "$taskBase/api/tts/audio/$($taskTts.filename)" -Headers @{Range='bytes=0-7'} -TimeoutSec 10
        if ([int]$taskAudio.StatusCode -ne 206) { throw 'Generated audiobook playback failed.' }
        $taskTtsReopened = Invoke-RestMethod "$taskBase/api/notes/$taskNoteId" -TimeoutSec 10
        if ($taskTtsReopened.audiobook.filename -ne $taskTts.filename) { throw 'Generated audiobook restoration failed.' }
        Write-Output 'Packaged live TTS OK: parenthetical meaning, MP3 delivery and saved audiobook restoration.'
    }
    $taskGroupBody = @{name='Packaged library group'} | ConvertTo-Json
    $taskGroup = Invoke-RestMethod "$taskBase/api/library/collections" -Method Post -Headers $taskHeaders -ContentType 'application/json' -Body $taskGroupBody -TimeoutSec 5
    $taskBulkBody = @{note_ids=@($taskNoteId);action='collection_add';collection_id=$taskGroup.id} | ConvertTo-Json
    Invoke-RestMethod "$taskBase/api/library/notes/bulk" -Method Post -Headers $taskHeaders -ContentType 'application/json' -Body $taskBulkBody -TimeoutSec 5 | Out-Null
    $taskLibrary = Invoke-RestMethod "$taskBase/api/library?collection_id=$($taskGroup.id)" -TimeoutSec 5
    if ($taskLibrary.total -ne 1 -or $taskLibrary.collections[0].count -ne 1 -or $taskLibrary.notes[0].classification_version -ne 1) { throw 'Packaged group or automatic classification missing.' }
    $taskBulkBody = @{note_ids=@($taskNoteId);action='trash'} | ConvertTo-Json
    Invoke-RestMethod "$taskBase/api/library/notes/bulk" -Method Post -Headers $taskHeaders -ContentType 'application/json' -Body $taskBulkBody -TimeoutSec 5 | Out-Null
    $taskTrash = Invoke-RestMethod "$taskBase/api/library?trash=true" -TimeoutSec 5
    $taskHidden = Invoke-WebRequest "$taskBase/api/notes/$taskNoteId" -SkipHttpErrorCheck -TimeoutSec 5
    if ($taskTrash.total -ne 1 -or $taskTrash.active_count -ne 0 -or [int]$taskHidden.StatusCode -ne 404) { throw 'Trashed note remains active.' }
    $taskBulkBody = @{note_ids=@($taskNoteId);action='restore'} | ConvertTo-Json
    Invoke-RestMethod "$taskBase/api/library/notes/bulk" -Method Post -Headers $taskHeaders -ContentType 'application/json' -Body $taskBulkBody -TimeoutSec 5 | Out-Null
    $taskRestored = Invoke-RestMethod "$taskBase/api/notes/$taskNoteId" -TimeoutSec 5
    $taskLibrary = Invoke-RestMethod "$taskBase/api/library?collection_id=$($taskGroup.id)" -TimeoutSec 5
    if ($taskLibrary.total -ne 1 -or -not $taskRestored.metadata.local_video_available) { throw 'Restored note lost group membership or media.' }
    if ($VerifyTts -and $taskRestored.audiobook.filename -ne $taskTts.filename) { throw 'Restore lost saved audiobook.' }
    Invoke-RestMethod "$taskBase/api/library/collections/$($taskGroup.id)" -Method Delete -Headers $taskHeaders -TimeoutSec 5 | Out-Null
    $taskRestored = Invoke-RestMethod "$taskBase/api/notes/$taskNoteId" -TimeoutSec 5
    $taskBulkBody = @{note_ids=@($taskNoteId);action='trash'} | ConvertTo-Json
    Invoke-RestMethod "$taskBase/api/library/notes/bulk" -Method Post -Headers $taskHeaders -ContentType 'application/json' -Body $taskBulkBody -TimeoutSec 5 | Out-Null
    $taskBulkBody = @{note_ids=@($taskNoteId);action='purge'} | ConvertTo-Json
    Invoke-RestMethod "$taskBase/api/library/notes/bulk" -Method Post -Headers $taskHeaders -ContentType 'application/json' -Body $taskBulkBody -TimeoutSec 5 | Out-Null
    $taskLibrary = Invoke-RestMethod "$taskBase/api/library?trash=true" -TimeoutSec 5
    $taskVideoPath = Join-Path $taskProfile "data\videos\$($taskRestored.metadata.local_video.filename)"
    if ($taskLibrary.total -ne 0 -or (Test-Path -LiteralPath $taskVideoPath) -or (Test-Path -LiteralPath (Join-Path $taskProfile "data\notes\$taskNoteId.md"))) { throw 'Permanent deletion left owned note or video files.' }
    Write-Output 'Packaged library OK: asset hashes, automatic classification, groups, Trash, restore and permanent deletion.'
    if ($taskProcess.HasExited) { throw 'Packaged app exited unexpectedly.' }
    Write-Output "Packaged smoke OK: startup, unified dialog, transcript persistence, video attachment and Range playback. PID=$($taskProcess.Id)"
    Write-Output "Isolated profile: $taskProfile"
} finally {
    # Only terminate the process created by this test; never touch an installed app.
    if (-not $taskProcess.HasExited) { Stop-Process -Id $taskProcess.Id -Force }
    $taskProcess.Dispose()
}
