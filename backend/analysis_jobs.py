"""Request-scoped analysis jobs, deadlines and cancellable async I/O."""
import asyncio
import contextvars
import logging
import re
import threading
import time
import uuid
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.formparsers import MultiPartException

from config import MAX_LOCAL_VIDEO_BYTES, ANALYSIS_TIMEOUT_SECONDS

log = logging.getLogger("tubescholar.analysis")
_context = contextvars.ContextVar("analysis_job", default=None)
_registry_lock = threading.RLock()
_jobs = OrderedDict()
_pending_cancels = OrderedDict()
_latest_id = None
ANALYSIS_PATHS = {"/api/analyze", "/api/local/analyze", "/api/local/video-analyze", "/api/note/regenerate"}
TERMINAL = {"completed", "cancelled", "error"}


class AnalysisStopped(HTTPException):
    pass


@dataclass
class AnalysisJob:
    job_id: str
    kind: str
    timeout: float = ANALYSIS_TIMEOUT_SECONDS
    started: float = field(default_factory=time.monotonic)
    cancel: threading.Event = field(default_factory=threading.Event)
    lock: Any = field(default_factory=threading.RLock)
    state: dict = field(default_factory=dict)
    failure: Optional[HTTPException] = None
    stage_started: float = field(default_factory=time.monotonic)

    def remaining(self):
        return max(0.0, self.timeout - (time.monotonic() - self.started))

    def check(self):
        if self.failure:
            raise self.failure
        if self.cancel.is_set():
            raise AnalysisStopped(499, "사용자에 의해 분석이 중단되었습니다.")
        if self.remaining() <= 0:
            raise AnalysisStopped(504, "분석 전체 제한 시간을 초과했습니다. 저장된 자막으로 다시 시도해 주세요.")


def current_job():
    return _context.get()


class _JobLogFilter(logging.Filter):
    def filter(self, record):
        job = current_job()
        record.analysis_id = getattr(record, "analysis_id", job.job_id if job else "-")
        return True


if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)sZ %(levelname)s job=%(analysis_id)s %(message)s", "%Y-%m-%dT%H:%M:%S")
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    handler.addFilter(_JobLogFilter())
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False


def begin_job(job_id=None, kind="analysis", timeout=None):
    global _latest_id
    job_id = job_id or uuid.uuid4().hex
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", job_id):
        raise HTTPException(400, "잘못된 분석 작업 ID입니다.")
    with _registry_lock:
        if job_id in _jobs:
            raise HTTPException(409, "이미 사용한 분석 작업 ID입니다. 새 작업으로 다시 시도해 주세요.")
        previous = _jobs.get(_latest_id)
        if previous:
            with previous.lock:
                if previous.state.get("status") not in TERMINAL:
                    previous.cancel.set()
                    _update(previous, "cancelled", event="cancelled", message="새 분석을 시작하여 이전 작업을 중단했습니다.")
        job = AnalysisJob(job_id, kind, timeout=timeout if timeout is not None else ANALYSIS_TIMEOUT_SECONDS)
        if job_id in _pending_cancels:
            _pending_cancels.pop(job_id)
            job.cancel.set()
        _jobs[job_id] = job
        _latest_id = job_id
        # Keep recent results for delayed status/cancel requests; never evict a running job.
        for key, value in list(_jobs.items()):
            if len(_jobs) <= 100:
                break
            if value.state.get("status") in TERMINAL:
                _jobs.pop(key, None)
        _update(job, "processing", event="uploading" if kind.endswith("video-analyze") else "preparing", step=1,
                message="로컬 영상 업로드 중..." if kind.endswith("video-analyze") else "분석 준비 중...")
    return job


def _update(job, status, **fields):
    with job.lock:
        old = job.state.get("event")
        job.state.update(status=status, job_id=job.job_id, input_type=job.kind,
                         timestamp=time.time(), elapsed_seconds=round(time.monotonic() - job.started, 2), **fields)
        if old != fields.get("event"):
            now = time.monotonic()
            log.info("input=%s event=%s status=%s model=%s attempt=%s cycle=%s elapsed=%.2fs previous_stage=%.2fs", job.kind,
                     job.state.get("event"), status, job.state.get("model", ""), job.state.get("attempt", 1),
                     job.state.get("cycle", 1), now - job.started, now - job.stage_started,
                     extra={"analysis_id": job.job_id})
            job.stage_started = now


def update_analysis_state(status, model="", event="", attempt=1, cycle=1, message="", step=2):
    job = current_job()
    if not job:
        return
    with job.lock:
        if job.state.get("status") in TERMINAL:
            return
        # A model response is an intermediate result; the request completes after saving.
        if status == "completed":
            status, event, step = "processing", "saving", 3
            message = "분석 결과를 검증하고 보관함에 저장 중..."
        _update(job, status, model=model, event=event, attempt=attempt, cycle=cycle, message=message, step=step)


def get_analysis_state(job_id=None):
    with _registry_lock:
        job = _jobs.get(job_id or _latest_id)
    if not job:
        return {"status": "idle", "job_id": job_id, "step": 1}
    with job.lock:
        return dict(job.state, elapsed_seconds=round(time.monotonic() - job.started, 2))


def request_analysis_cancel(job_id=None):
    with _registry_lock:
        job = _jobs.get(job_id or _latest_id)
        if not job:
            if job_id and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", job_id):
                _pending_cancels[job_id] = time.monotonic()
                while len(_pending_cancels) > 100:
                    _pending_cancels.popitem(last=False)
            return
        with job.lock:
            if job.state.get("status") not in TERMINAL:
                job.cancel.set()
                _update(job, "cancelled", event="cancelled", message="사용자에 의해 분석이 중단되었습니다.")


def reset_analysis_cancel():
    # The middleware creates the job before reading the body. Never clear its cancellation.
    check_analysis()


def check_analysis():
    job = current_job()
    if job:
        job.check()


def is_analysis_cancelled():
    job = current_job()
    return bool(job and job.cancel.is_set())


def remaining_seconds(limit):
    check_analysis()
    job = current_job()
    return min(limit, job.remaining()) if job else limit


def interruptible_sleep(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        check_analysis()
        time.sleep(min(0.1, max(0, deadline - time.monotonic())))
    return False


@contextmanager
def analysis_commit():
    """Linearize cancellation/new requests with writes so stale results cannot be committed."""
    job = current_job()
    if not job:
        yield
    else:
        with job.lock:
            job.check()
            yield


def set_checkpoint(note_id):
    job = current_job()
    if job:
        with job.lock:
            job.state["checkpoint_note_id"] = note_id


async def await_operation(factory, timeout, *, check_job=True):
    """Cancel the actual async transport operation; no abandoned worker threads."""
    limit = remaining_seconds(timeout) if check_job else timeout
    task = asyncio.create_task(factory())
    deadline = time.monotonic() + limit
    try:
        while True:
            if check_job:
                check_analysis()
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError("외부 서비스 응답 시간 초과 (timeout)")
            done, _ = await asyncio.wait({task}, timeout=min(0.1, left))
            if done:
                if check_job:
                    check_analysis()
                return task.result()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def run_async_operation(factory, timeout, *, check_job=True):
    return asyncio.run(await_operation(factory, timeout, check_job=check_job))


class AnalysisMiddleware:
    """Create jobs and enforce upload limits before FastAPI parses multipart files."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] not in ANALYSIS_PATHS:
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        try:
            job = begin_job(headers.get(b"x-analysis-id", b"").decode("ascii"), scope["path"])
        except (HTTPException, UnicodeError) as exc:
            return await JSONResponse({"detail": getattr(exc, "detail", "잘못된 작업 ID입니다.")},
                                      status_code=getattr(exc, "status_code", 400))(scope, receive, send)
        token = _context.set(job)
        started_response = False
        received = 0
        is_video = scope["path"] == "/api/local/video-analyze"
        # Allow only small multipart framing overhead in addition to the file limit.
        body_limit = MAX_LOCAL_VIDEO_BYTES + 64 * 1024
        receive_task = None

        async def read_message():
            nonlocal received, receive_task
            if receive_task is None:
                receive_task = asyncio.create_task(receive())
            while not receive_task.done():
                job.check()
                await asyncio.wait({receive_task}, timeout=min(0.1, max(0.001, job.remaining())))
            job.check()
            message = receive_task.result()
            receive_task = None
            if message["type"] == "http.disconnect":
                job.cancel.set()
                job.check()
            received += len(message.get("body", b""))
            if is_video and received > body_limit:
                job.failure = HTTPException(413, "업로드 영상이 허용 용량을 초과했습니다.")
                raise job.failure
            return message

        async def guarded_receive():
            try:
                return await read_message()
            except HTTPException as exc:
                job.failure = exc
                if is_video:
                    # Starlette closes in-progress spooled files on MultiPartException.
                    raise MultiPartException(str(exc.detail)) from exc
                raise

        async def guarded_send(message):
            nonlocal started_response
            if message["type"] == "http.response.start":
                if job.failure:
                    message["status"] = job.failure.status_code
                status = message["status"]
                with job.lock:
                    if job.state.get("status") not in TERMINAL:
                        if status < 400:
                            job.check()
                            _update(job, "completed", event="completed", message="노트 저장이 완료되었습니다.", step=3)
                        else:
                            _update(job, "cancelled" if status == 499 else "error", event="cancelled" if status == 499 else "error",
                                    message="분석이 중단되었습니다." if status == 499 else "분석에 실패했습니다. 오류 안내를 확인해 주세요.", http_status=status)
                message["headers"].append((b"x-analysis-id", job.job_id.encode("ascii")))
                started_response = True
            await send(message)

        try:
            job.check()
            if is_video and b"content-length" in headers:
                try:
                    too_large = int(headers[b"content-length"]) > body_limit
                except ValueError:
                    raise HTTPException(400, "잘못된 업로드 크기입니다.")
                if too_large:
                    raise HTTPException(413, "업로드 영상이 허용 용량을 초과했습니다.")
            await self.app(scope, guarded_receive, guarded_send)
        except Exception as exc:
            status = getattr(exc, "status_code", 500)
            detail = getattr(exc, "detail", "서버 처리 중 오류가 발생했습니다.")
            with job.lock:
                if job.state.get("status") != "completed":
                    _update(job, "cancelled" if status == 499 else "error", event="cancelled" if status == 499 else "error", message=str(detail), http_status=status)
            if status == 500:
                log.exception("job=%s analysis failed", job.job_id)
            if started_response:
                raise
            await JSONResponse({"detail": detail, "checkpoint_note_id": job.state.get("checkpoint_note_id")},
                               status_code=status)(scope, receive, send)
        finally:
            if receive_task is not None:
                receive_task.cancel()
                await asyncio.gather(receive_task, return_exceptions=True)
            _context.reset(token)
