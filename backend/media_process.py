"""Bounded, cancellable FFmpeg execution without pipe-buffer deadlocks."""
import logging
import os
import subprocess
import tempfile
import time

from analysis_jobs import check_analysis, remaining_seconds

log = logging.getLogger("tubescholar.analysis")


def run_ffmpeg(command, timeout=120.0):
    deadline = time.monotonic() + remaining_seconds(timeout)
    kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    # stderr can exceed the pipe buffer during lengthy extraction. Spool it to disk.
    with tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(command, stderr=errors, **kwargs)
        try:
            while proc.poll() is None:
                check_analysis()
                if time.monotonic() >= deadline:
                    raise TimeoutError("FFmpeg 오디오 추출 제한 시간을 초과했습니다.")
                time.sleep(0.1)
            check_analysis()
            if proc.returncode:
                errors.seek(max(0, errors.seek(0, 2) - 4096))
                detail = errors.read().decode("utf-8", errors="replace")
                log.error("FFmpeg exit=%s stderr=%s", proc.returncode, detail)
                raise ValueError("영상에서 오디오를 추출하지 못했습니다. 음성 트랙과 파일 손상 여부를 확인해 주세요.")
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
