# Local analysis reliability

Local subtitles are saved in the library before study-note generation begins. If
generation fails or is cancelled, reopen that entry and use **Regenerate note**;
the original video does not need to be uploaded or transcribed again.

Each analysis request sends an `X-Analysis-Id`. Status and cancellation requests
use `job_id` to target that analysis. Starting another analysis cancels the previous
one; delayed responses and polling results cannot update the new analysis.

The default total deadline is 600 seconds, including upload, extraction,
transcription and generation. Configure `TUBESCHOLAR_ANALYSIS_TIMEOUT_SECONDS` in
the application's `.env` to change it. The video upload limit is controlled by
`TUBESCHOLAR_MAX_VIDEO_MB` (default 2048). Limits are checked in the browser and
while receiving the upload, including requests without Content-Length.

FFmpeg is terminated when cancelled or timed out. Gemini and Groq use cancellable
async requests and close their clients after each operation. Gemini upload cleanup
has its own short best-effort timeout and cannot turn a successful note into a
failed request. Missing or invalid generated SRT is reported as unavailable;
study-note summaries are never substituted for dialogue subtitles.

Analysis logs include UTC timestamps, job IDs, input types, stage changes, models,
attempts and elapsed time. Exceptions retain tracebacks and FFmpeg failures retain
the tail of stderr. API keys and uploaded media contents are not added to logs.

## Offline verification

From the repository root on Windows:

```powershell
.\.venv\Scripts\python.exe -u -B scripts\test_analysis.py
node --test scripts\test_analysis_frontend.cjs
```

The tests use isolated temporary data and mocked AI services. One integration test
performs real FFmpeg extraction on generated local audio. No external AI API calls
or personal video files are used.

Before packaging, `build_installer.bat` checks that native wheels match the build
Python interpreter. A Python 3.13 wheel in a Python 3.10 environment can otherwise
produce a seemingly successful build with DLL import failures.

After building, run `./scripts/smoke_packaged.ps1` in PowerShell 7 with port 8000
available. It launches the packaged app without a browser, uses an isolated profile
under `build`, verifies startup and subtitle persistence without API keys, and
stops only the process it created. `TUBESCHOLAR_NO_BROWSER=1` suppresses automatic
browser launch for this check.
