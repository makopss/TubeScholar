import os
import sys
import time
import json
import re
import threading
import subprocess
import tempfile
import shutil
import logging
import uuid
import mimetypes
from typing import Optional, List, Dict, Any, Literal
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
import imageio_ffmpeg

# backend 디렉토리를 모듈 경로에 먼저 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    BUNDLE_DIR,
    ENV_PATH,
    FRONTEND_DIR,
    AUDIO_DIR,
    MAX_LOCAL_VIDEO_MB,
    MAX_LOCAL_VIDEO_BYTES,
    suppress_genai_warnings,
)

suppress_genai_warnings()

from extractor import (
    extract_video_id, 
    get_video_info, 
    get_video_transcript, 
    list_transcript_tracks,
    get_channel_videos, 
    is_valid_youtube_channel_url,
    parse_srt_vtt_text,
    detect_text_language,
    convert_to_srt,
    convert_to_txt,
    _group_subtitles_into_chunks,
)
from analyzer import (
    generate_study_note_gemini,
    generate_clipboard_prompt,
    generate_study_note_from_audio,
    translate_subtitles_gemini,
    translate_subtitles_stream,
    DEFAULT_NOTE_MODEL,
    DEFAULT_TRANSLATE_MODEL,
    get_analysis_state,
    update_analysis_state,
    request_analysis_cancel,
    reset_analysis_cancel,
    is_analysis_cancelled,
)
from storage import (
    save_note as _save_note, get_note, list_saved_notes, delete_note, update_note,
    update_note_subtitles, update_note_audiobook, is_safe_note_id, get_cached_subtitles, save_translation_cache,
    clean_ai_citation_artifacts, attach_note_video, local_video_path
)
from prompt_loader import list_available_templates, get_user_prompts_dir
from languages import TARGET_LANGUAGES, DEFAULT_TARGET_LANG, language_name, normalize_target_lang, is_same_language
from stt import transcribe_audio_groq
from tts import (
    generate_note_audio, generate_subtitles_audio, list_available_voices,
    abbreviate_note_title, get_audiobook_download_filename
)

from analysis_jobs import (
    AnalysisMiddleware, check_analysis, analysis_commit, set_checkpoint, current_job,
)
from media_process import run_ffmpeg
import library_manager

log = logging.getLogger("tubescholar.analysis")


def save_note(*args, **kwargs):
    with analysis_commit():
        update_analysis_state("processing", event="saving", message="분석 결과를 보관함에 저장 중...", step=3)
        return _save_note(*args, **kwargs)


def save_transcript_checkpoint(video_info, subtitles, lang_meta):
    with analysis_commit():
        note_id = f"{video_info['video_id']}_{uuid.uuid4().hex[:12]}"
        _save_note(
            video_info, "자막 전사를 보관했습니다. ‘노트 재작성’으로 학습 노트를 생성할 수 있습니다.",
            note_id=note_id, subtitles=subtitles, lang_meta=lang_meta,
        )
        set_checkpoint(note_id)
        return note_id


def parse_local_transcript(text):
    result = parse_srt_vtt_text(text)
    subtitles = [s for s in result.get("subtitles", [])
                 if s.get("text", "").strip() and s.get("end", 0) > s.get("start", 0)]
    if not subtitles:
        raise HTTPException(400, "유효한 타임코드와 대사가 있는 SRT/VTT 자막 파일이 필요합니다.")
    chunks = _group_subtitles_into_chunks(subtitles, window_sec=35.0)
    language = detect_text_language(subtitles)
    result.update(subtitles=subtitles, chunks=chunks,
                  full_text="\n".join(f"[{s['timestamp']}] {s['text']}" for s in chunks),
                  language=language, source_lang=language, original_lang=language)
    return result


app = FastAPI(title="TubeScholar API")
app.add_middleware(AnalysisMiddleware)

# 🔒 로컬 서버 보안
# 1) DNS 리바인딩 방지: Host 헤더가 127.0.0.1/localhost 인 요청만 허용
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

# 2) CSRF 방지: 상태를 바꾸는 /api 요청은 전용 헤더 필수
#    (외부 웹사이트가 커스텀 헤더를 붙이면 CORS preflight 가 발생하는데, 이 서버는 CORS 를 허용하지 않으므로 차단됨)
_CSRF_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_last_heartbeat = time.time()
_heartbeat_received = False
_shutdown_timer: Optional[threading.Timer] = None
_shutdown_lock = threading.Lock()

def cancel_shutdown():
    """새로운 요청이나 하트비트가 수신되면 종료 예약 취소 (새로고침 지원)"""
    global _shutdown_timer
    with _shutdown_lock:
        if _shutdown_timer is not None:
            _shutdown_timer.cancel()
            _shutdown_timer = None

def _perform_exit():
    os._exit(0)

@app.middleware("http")
async def csrf_guard(request: Request, call_next):
    global _last_heartbeat, _heartbeat_received
    if not request.url.path.startswith("/api/system/browser-close"):
        _last_heartbeat = time.time()
        _heartbeat_received = True
        if _shutdown_timer is not None:
            cancel_shutdown()
    if request.method in _CSRF_METHODS and request.url.path.startswith("/api/"):
        if request.headers.get("x-tubescholar") != "1":
            return JSONResponse(status_code=403, content={"detail": "허용되지 않은 요청입니다. (CSRF 보호)"})
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    if not request.url.path.startswith("/api/system/browser-close"):
        _last_heartbeat = time.time()
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("Unhandled request failure path=%s", request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": f"서버 처리 중 오류가 발생했습니다: {str(exc)}"}
    )

class AnalyzeRequest(BaseModel):
    url: str
    engine: Optional[str] = "gemini"
    gemini_model: Optional[str] = DEFAULT_NOTE_MODEL
    source_lang: Optional[str] = None   # 원문 자막 트랙 ('en', 'en:auto'), 없으면 자동 감지
    target_lang: Optional[str] = DEFAULT_TARGET_LANG  # 번역 언어 (자막)
    note_target_lang: Optional[str] = None  # 학습 노트 작성 언어

class LocalAnalyzeRequest(BaseModel):
    title: str
    subtitle_text: str
    engine: Optional[str] = "gemini"
    target_lang: Optional[str] = DEFAULT_TARGET_LANG
    note_target_lang: Optional[str] = None

class LocalPromptRequest(BaseModel):
    title: str
    subtitle_text: str
    target_lang: Optional[str] = DEFAULT_TARGET_LANG
    note_target_lang: Optional[str] = None

class PromptRequest(BaseModel):
    url: str
    source_lang: Optional[str] = None
    target_lang: Optional[str] = DEFAULT_TARGET_LANG
    note_target_lang: Optional[str] = None

class RegenerateNoteRequest(BaseModel):
    video_id: Optional[str] = None
    title: Optional[str] = None
    channel: Optional[str] = None
    duration_str: Optional[str] = None
    video_type: Optional[str] = "youtube"
    url: Optional[str] = ""
    note_id: Optional[str] = None
    subtitles: List[Dict[str, Any]]
    source_lang: Optional[str] = None
    note_target_lang: Optional[str] = DEFAULT_TARGET_LANG
    gemini_model: Optional[str] = DEFAULT_NOTE_MODEL

class ManualSaveRequest(BaseModel):
    url: Optional[str] = ""
    video_id: Optional[str] = None
    title: Optional[str] = ""
    channel: Optional[str] = ""
    markdown: str
    video_type: Optional[str] = "youtube"
    note_id: Optional[str] = None
    subtitles: Optional[List[Dict[str, Any]]] = None
    source_lang: Optional[str] = None
    target_lang: Optional[str] = None
    note_target_lang: Optional[str] = None
    translation_source: Optional[str] = None

class UpdateNoteRequest(BaseModel):
    markdown: str


class CollectionSource(BaseModel):
    kind: Literal['manual', 'youtube_playlist', 'local_folder'] = 'manual'
    reference: str = Field(default='', max_length=2000)


class CollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    source: CollectionSource = Field(default_factory=CollectionSource)


class CollectionRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CollectionOrderRequest(BaseModel):
    note_ids: List[str] = Field(max_length=10000)


class LibraryBulkRequest(BaseModel):
    note_ids: List[str] = Field(min_length=1, max_length=500)
    action: Literal['tags_add', 'tags_remove', 'collection_add', 'collection_remove',
                    'status', 'star', 'unstar', 'trash', 'restore', 'purge']
    tags: Optional[List[str]] = None
    collection_id: Optional[str] = None
    status: Optional[Literal['unread', 'learning', 'completed', 'review']] = None


class LibraryExportRequest(BaseModel):
    note_ids: List[str] = Field(min_length=1, max_length=500)

class ChannelRequest(BaseModel):
    channel_url: str
    max_results: Optional[int] = 15

class SubtitlesRequest(BaseModel):
    url: Optional[str] = ""
    video_id: Optional[str] = ""
    translate_ko: Optional[bool] = False
    subtitles: Optional[List[Dict[str, Any]]] = None
    note_id: Optional[str] = None
    title: Optional[str] = None  # 번역 프롬프트 문맥용 영상 제목
    source_lang: Optional[str] = None
    target_lang: Optional[str] = DEFAULT_TARGET_LANG

class SubtitleDownloadRequest(BaseModel):
    subtitles: List[Dict[str, Any]]
    format: Optional[str] = "srt"
    lang_mode: Optional[str] = "original"
    title: Optional[str] = "자막"
    auto_translate: Optional[bool] = False
    sync_offset: Optional[float] = 0.0  # 초 단위, +값 = 자막을 더 빨리 표시
    target_lang: Optional[str] = DEFAULT_TARGET_LANG  # 'ko_text' 필드에 담긴 번역문의 언어

class ConfigRequest(BaseModel):
    api_key: Optional[str] = None
    groq_api_key: Optional[str] = None

class TTSRequest(BaseModel):
    note_id: Optional[str] = "temp_note"
    markdown: Optional[str] = ""
    voice: Optional[str] = "injoon"
    speed: Optional[str] = "+0%"
    title: Optional[str] = None

class SubtitleTTSRequest(BaseModel):
    video_id: Optional[str] = "temp_video"
    note_id: Optional[str] = None
    title: Optional[str] = None
    mode: Optional[str] = "ko"
    voice: Optional[str] = "injoon"
    speed: Optional[str] = "+0%"
    subtitles: Optional[List[Dict[str, Any]]] = None

class SubtitleSaveRequest(BaseModel):
    note_id: Optional[str] = None
    video_id: Optional[str] = None
    subtitles: List[Dict[str, Any]]
    target_lang: Optional[str] = DEFAULT_TARGET_LANG
    source_lang: Optional[str] = None
    translation_source: Optional[str] = "manual"

@app.get("/api/system/health")
def system_health():
    """경량 서버 상태 확인 엔드포인트 (디스크 I/O 없음)"""
    return {"status": "ok"}

@app.get("/api/config")
def get_config():
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    has_gemini = bool(gemini_key.strip())
    masked_gemini = f"{gemini_key[:4]}...{gemini_key[-4:]}" if len(gemini_key) >= 8 else ("configured" if has_gemini else "")

    groq_key = os.environ.get("GROQ_API_KEY") or ""
    has_groq = bool(groq_key.strip())
    masked_groq = f"{groq_key[:4]}...{groq_key[-4:]}" if len(groq_key) >= 8 else ("configured" if has_groq else "")

    return {
        "max_local_video_bytes": MAX_LOCAL_VIDEO_BYTES,
        "has_api_key": has_gemini,
        "masked_key": masked_gemini,
        "has_groq_key": has_groq,
        "masked_groq_key": masked_groq
    }

@app.post("/api/config")
def set_config(req: ConfigRequest):
    def _clean_key(v: str) -> str:
        # 줄바꿈/제어문자/공백 제거 → .env 에 다른 줄이 끼어드는 것(인젝션) 방지
        return re.sub(r"[\s\x00-\x1f\x7f]", "", v or "")

    updates: Dict[str, Optional[str]] = {}
    if req.api_key is not None:
        k = _clean_key(req.api_key)
        os.environ["GEMINI_API_KEY"] = k
        updates["GEMINI_API_KEY"] = k if k else None

    if req.groq_api_key is not None:
        k = _clean_key(req.groq_api_key)
        os.environ["GROQ_API_KEY"] = k
        updates["GROQ_API_KEY"] = k if k else None

    # 기존 .env의 주석(#)과 빈 줄, 타 설정 키 순서를 그대로 보존하면서 업데이트
    raw_lines: List[str] = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()

    out_lines: List[str] = []
    seen_keys = set()
    for line in raw_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out_lines.append(line if line.endswith("\n") else line + "\n")
            continue
        key_part = line.split("=", 1)[0].strip()
        if key_part in updates:
            seen_keys.add(key_part)
            new_val = updates[key_part]
            if new_val is not None:
                out_lines.append(f"{key_part}={new_val}\n")
        else:
            out_lines.append(line if line.endswith("\n") else line + "\n")

    for k, v in updates.items():
        if k not in seen_keys and v is not None:
            out_lines.append(f"{k}={v}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(out_lines)
        
    return {"success": True, "message": "API 키가 성공적으로 저장되었습니다."}

def _lang_payload(tr: Dict[str, Any]) -> Dict[str, Any]:
    """자막 추출 결과 중 화면(언어 선택 상자/번역 버튼)에 필요한 언어 정보."""
    return {
        "transcript_language": tr.get("language"),
        "source_lang": tr.get("source_lang"),
        "original_lang": tr.get("original_lang"),
        "target_lang": tr.get("target_lang"),
        "translation_source": tr.get("translation_source"),
        "translation_track": tr.get("translation_track"),
        "tracks": tr.get("tracks", []),
    }


def _lang_meta(tr: Dict[str, Any], note_target_lang: Optional[str] = None) -> Dict[str, Any]:
    """노트에 저장할 언어 정보."""
    meta = {
        "source_lang": tr.get("source_lang"),
        "target_lang": tr.get("target_lang"),
        "translation_source": tr.get("translation_source"),
    }
    if note_target_lang:
        meta["note_target_lang"] = note_target_lang
    return meta


@app.get("/api/languages")
def get_languages():
    """번역 언어 선택 목록 (프론트/백엔드 공통 호환)."""
    return {
        "default": DEFAULT_TARGET_LANG,
        "target_languages": TARGET_LANGUAGES,
        "languages": [{"code": k, "name": v} for k, v in TARGET_LANGUAGES.items()],
    }

@app.get("/api/analysis/status")
def get_analysis_status(job_id: Optional[str] = None):
    """실시간 분석 진행 및 모델 폴백 상태 조회 (프론트엔드 폴링용)"""
    return get_analysis_state(job_id)

@app.post("/api/analysis/cancel")
def cancel_analysis(job_id: Optional[str] = None):
    """프론트엔드에서 [중단] 버튼 클릭 시 진행 중인 AI 분석 루프를 즉시 중단합니다."""
    request_analysis_cancel(job_id)
    return {"success": True, "state": get_analysis_state(job_id)}



@app.post("/api/prompt")
def get_prompt_for_ai(req: PromptRequest):
    """구독 중인 ChatGPT Plus / Claude Pro 대화창에 바로 붙여넣을 수 있는 프롬프트 생성"""
    video_id = extract_video_id(req.url)
    if not video_id:
        raise HTTPException(status_code=400, detail="유효한 유튜브 영상 URL이 아닙니다.")
    
    target = normalize_target_lang(req.target_lang)
    note_target = normalize_target_lang(req.note_target_lang or req.target_lang)
    video_info = get_video_info(video_id)
    transcript_result = get_video_transcript(
        video_id, source_lang=req.source_lang, target_lang=target,
        ytdlp_lang=video_info.get("language")
    )
    if not transcript_result.get("success"):
        raise HTTPException(status_code=400, detail=transcript_result.get("error"))

    prompt_text = generate_clipboard_prompt(video_info, transcript_result, target_lang=note_target)
    return {
        "success": True,
        "video_info": video_info,
        "prompt": prompt_text,
        "subtitles": transcript_result.get("subtitles", []),
        "is_generated": transcript_result.get("is_generated"),
        "note_target_lang": note_target,
        **_lang_payload(transcript_result)
    }

@app.post("/api/local/prompt")
def get_local_prompt_for_ai(req: LocalPromptRequest):
    """로컬 자막 파일로부터 ChatGPT/Claude 복사용 프롬프트 생성"""
    transcript_result = parse_local_transcript(req.subtitle_text)
    target = normalize_target_lang(req.target_lang)
    note_target = normalize_target_lang(req.note_target_lang or req.target_lang)
    src_lang = transcript_result.get("language") or "en"
    same_lang = is_same_language(src_lang, target)
    video_info = {
        "video_id": f"local_{uuid.uuid4().hex}",
        "title": req.title or "로컬 비디오",
        "channel": "Local Video",
        "video_type": "local",
        "duration_str": "로컬 파일"
    }
    prompt_text = generate_clipboard_prompt(video_info, transcript_result, target_lang=note_target)
    return {
        "success": True,
        "video_info": video_info,
        "prompt": prompt_text,
        "subtitles": transcript_result.get("subtitles", []),
        "source_lang": src_lang,
        "original_lang": src_lang,
        "transcript_language": src_lang,
        "is_korean": src_lang == "ko",
        "is_same_language": same_lang,
        "translation_source": "same" if same_lang else None,
        "target_lang": target,
        "note_target_lang": note_target
    }

def _raise_if_cancelled(llm_result: Optional[Dict[str, Any]] = None):
    check_analysis()
    if (llm_result and llm_result.get("cancelled")) or is_analysis_cancelled():
        raise HTTPException(status_code=499, detail="사용자에 의해 분석이 중단되었습니다.")


@app.post("/api/local/analyze")
def analyze_local_video(req: LocalAnalyzeRequest):
    return _analyze_local_subtitles(req)


def _retain_video(note_id, source_path, original_name):
    with open(source_path, "rb") as stream:
        return attach_note_video(note_id, stream, original_name, check_analysis, analysis_commit)


def _analyze_local_subtitles(req, source_path=None, original_name=None):
    """로컬 자막 텍스트를 Gemini로 분석하여 학습 노트 생성"""
    reset_analysis_cancel()
    update_analysis_state("processing", event="extracting_local", message="로컬 자막 파싱 및 분석 준비 중...", step=1)
    transcript_result = parse_local_transcript(req.subtitle_text)
    target = normalize_target_lang(req.target_lang)
    note_target = normalize_target_lang(req.note_target_lang or req.target_lang)
    src_lang = transcript_result.get("language") or "en"
    same_lang = is_same_language(src_lang, target)
    trans_source = "same" if same_lang else None
    video_info = {
        "video_id": f"local_{uuid.uuid4().hex}",
        "title": req.title or "로컬 비디오",
        "channel": "Local Video",
        "video_type": "local",
        "duration_str": "로컬 파일"
    }
    
    if not transcript_result.get("subtitles") or not transcript_result.get("full_text", "").strip():
        raise HTTPException(400, "분석할 유효한 자막이 없습니다.")
    checkpoint_id = save_transcript_checkpoint(video_info, transcript_result["subtitles"], {
        "source_lang": src_lang, "target_lang": target, "note_target_lang": note_target,
        "translation_source": trans_source,
    })
    if source_path:
        video_info["local_video"] = _retain_video(checkpoint_id, source_path, original_name)
    update_analysis_state("processing", event="transcript_ready", message="자막을 보관했습니다. 학습 노트 생성 중...", step=2)
    llm_result = generate_study_note_gemini(
        video_info=video_info,
        transcript_data=transcript_result,
        target_lang=note_target
    )

    _raise_if_cancelled(llm_result)
    if not llm_result.get("success"):
        raise HTTPException(status_code=500, detail=f"분석 실패: {llm_result.get('error')}")

    save_res = save_note(
        video_info, 
        llm_result["markdown"], 
        note_id=checkpoint_id,
        subtitles=transcript_result.get("subtitles", []),
        lang_meta={
            "source_lang": src_lang,
            "target_lang": target,
            "note_target_lang": note_target,
            "translation_source": trans_source
        }
    )
    return {
        "success": True,
        "note_id": save_res["note_id"],
        "video_info": video_info,
        "subtitles": save_res["metadata"].get("subtitles", transcript_result.get("subtitles", [])),
        "source_lang": src_lang,
        "original_lang": src_lang,
        "transcript_language": src_lang,
        "is_korean": src_lang == "ko",
        "is_same_language": same_lang,
        "translation_source": trans_source,
        "target_lang": target,
        "model_used": llm_result.get("model_used"),
        "markdown": save_res["markdown"],
        "file_path": save_res["file_path"],
        "note_target_lang": note_target,
        "audiobook": save_res.get("audiobook"),
        "subtitle_audiobook": save_res.get("subtitle_audiobook"),
    }

@app.post("/api/local/video-analyze")
def analyze_local_video_audio(
    video: UploadFile = File(...),
    title: Optional[str] = Form(None),
    target_lang: Optional[str] = Form(None),
    note_target_lang: Optional[str] = Form(None),
    subtitle_text: Optional[str] = Form(None)
):
    """자막이 없는 로컬 영상 파일에서 오디오를 추출하여 Gemini로 타임스탬프 학습 노트 생성
    (일반 def: FastAPI 가 작업 스레드에서 실행하므로 분석 중에도 다른 요청이 멈추지 않음)"""
    reset_analysis_cancel()
    update_analysis_state(
        "processing",
        event="extracting_audio",
        message="1단계: 로컬 영상에서 오디오 트랙(MP3) 추출 중...",
        step=1,
    )
    vid_title = title or os.path.splitext(os.path.basename(video.filename or "") or "로컬 비디오")[0]
    target = normalize_target_lang(target_lang)
    note_target = normalize_target_lang(note_target_lang or target_lang)
    
    checkpoint_id = None
    subtitle_status = "complete"
    warning = None
    temp_dir = tempfile.mkdtemp()
    # 클라이언트 파일명은 경로로 쓰지 않음 (경로 탈출 방지) → 고정 이름 + 검증된 확장자만 사용
    ext = os.path.splitext(os.path.basename(video.filename or ""))[1].lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", ext or ""):
        ext = ".mp4"
    temp_video_path = os.path.join(temp_dir, "input" + ext)
    temp_audio_path = os.path.join(temp_dir, "extracted_audio.mp3")

    try:
        written_bytes = 0
        chunk_size = 1024 * 1024  # 1MB 단위 스트리밍 복사 및 용량 제한 검사
        with open(temp_video_path, "wb") as f:
            while True:
                _raise_if_cancelled()
                buf = video.file.read(chunk_size)
                if not buf:
                    break
                written_bytes += len(buf)
                if written_bytes > MAX_LOCAL_VIDEO_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"업로드 영상 크기가 허용 한도({MAX_LOCAL_VIDEO_MB}MB)를 초과했습니다."
                    )
                f.write(buf)

        # Release Starlette's spool as soon as the extraction input is ready.
        video.file.close()
        _raise_if_cancelled()
        if subtitle_text is not None:
            return _analyze_local_subtitles(LocalAnalyzeRequest(
                title=vid_title, subtitle_text=subtitle_text, target_lang=target,
                note_target_lang=note_target,
            ), temp_video_path, video.filename)
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe, "-nostdin", "-y",
            "-i", temp_video_path,
            "-vn",
            "-acodec", "libmp3lame",
            "-ar", "16000",
            "-ac", "1",
            "-b:a", "32k",
            temp_audio_path
        ]
        try:
            run_ffmpeg(cmd)
        except TimeoutError as exc:
            raise HTTPException(504, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

        _raise_if_cancelled()
        # 1. Groq Whisper Cloud STT 시도 (Groq API 키가 설정되어 있는 경우)
        groq_key = os.environ.get("GROQ_API_KEY")
        stt_result = None
        if groq_key:
            update_analysis_state(
                "processing",
                event="groq_stt",
                message="Groq Whisper 초고속 음성인식으로 타임스탬프 자막 추출 중...",
                step=1,
            )
            stt_result = transcribe_audio_groq(temp_audio_path, api_key=groq_key)

        _raise_if_cancelled()
        if stt_result and stt_result.get("success") and stt_result.get("subtitles"):
            # Groq Whisper 자막 완성 -> 35초 단위로 병합하여 Gemini에게 전달 (토큰 절약 및 속도 향상)
            subtitles = stt_result["subtitles"]
            src_lang = detect_text_language(subtitles)
            duration_str = subtitles[-1]["timestamp"] if subtitles else "00:00"
            video_info = {
                "video_id": f"local_{uuid.uuid4().hex}",
                "title": vid_title,
                "channel": "내 로컬 PC 영상 (Groq Whisper 자막)",
                "video_type": "local",
                "duration_str": duration_str
            }
            merged_chunks = _group_subtitles_into_chunks(subtitles, window_sec=35.0)
            full_text = "\n".join(f"[{c['timestamp']}] {c['text']}" for c in (merged_chunks or subtitles))
            transcript_data = {
                "language": src_lang,
                "full_text": full_text,
                "chunks": merged_chunks,
                "subtitles": subtitles
            }
            checkpoint_id = save_transcript_checkpoint(video_info, subtitles, {
                "source_lang": src_lang, "target_lang": target, "note_target_lang": note_target,
                "translation_source": "same" if is_same_language(src_lang, target) else None,
            })
            video_info["local_video"] = _retain_video(checkpoint_id, temp_video_path, video.filename)
            update_analysis_state("processing", event="transcript_ready", message="전사 자막을 보관했습니다. 학습 노트 생성 중...", step=2)
            llm_result = generate_study_note_gemini(video_info, transcript_data, target_lang=note_target)
            _raise_if_cancelled(llm_result)
            if not llm_result.get("success"):
                raise HTTPException(status_code=500, detail=f"Gemini 학습 노트 생성 실패: {llm_result.get('error')}")

            model_used = f"Groq Whisper Large-v3 + Gemini {llm_result.get('model_used')}"
        else:
            if stt_result:
                log.warning("job=%s Groq failed; switching to Gemini audio: %s",
                            current_job().job_id if current_job() else "-", stt_result.get("error", "empty transcription"))
            # Groq 키가 없거나 실패한 경우: 기존 Gemini Multimodal Audio 직접 청취 방식으로 폴백
            llm_result = generate_study_note_from_audio(
                audio_path=temp_audio_path,
                video_title=vid_title,
                target_lang=note_target
            )
            _raise_if_cancelled(llm_result)
            if not llm_result.get("success"):
                raise HTTPException(status_code=500, detail=f"Gemini 음성 분석 실패: {llm_result.get('error')}")

            video_info = {
                "video_id": f"local_{uuid.uuid4().hex}",
                "title": vid_title,
                "channel": "내 로컬 PC 영상 (Gemini 음성 직접 청취)",
                "video_type": "local",
                "duration_str": "로컬 음성 분석"
            }
            subtitles = llm_result.get("subtitles", [])
            src_lang = detect_text_language(subtitles)
            model_used = llm_result.get("model_used")
            subtitle_status = llm_result.get("subtitle_status", "unavailable")
            warning = llm_result.get("warning")

        _raise_if_cancelled(llm_result)
        same_lang = is_same_language(src_lang, target)
        trans_source = "same" if same_lang else None
        save_res = save_note(
            video_info,
            llm_result["markdown"],
            note_id=checkpoint_id,
            subtitles=subtitles,
            lang_meta={
                "source_lang": src_lang,
                "target_lang": target,
                "note_target_lang": note_target,
                "translation_source": trans_source,
                "subtitle_status": subtitle_status,
            }
        )
        subtitles = save_res["metadata"].get("subtitles", subtitles)
        if not checkpoint_id:
            set_checkpoint(save_res["note_id"])
            video_info["local_video"] = _retain_video(save_res["note_id"], temp_video_path, video.filename)
        return {
            "success": True,
            "subtitle_status": subtitle_status,
            "warning": warning,
            "note_id": save_res["note_id"],
            "video_info": video_info,
            "subtitles": subtitles,
            "source_lang": src_lang,
            "original_lang": src_lang,
            "transcript_language": src_lang,
            "is_korean": src_lang == "ko",
            "is_same_language": same_lang,
            "translation_source": trans_source,
            "target_lang": target,
            "model_used": model_used,
            "markdown": save_res["markdown"],
            "file_path": save_res["file_path"],
            "note_target_lang": note_target,
            "audiobook": save_res.get("audiobook"),
            "subtitle_audiobook": save_res.get("subtitle_audiobook"),
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@app.post("/api/manual-save")
def manual_save_note(req: ManualSaveRequest):
    """구독 AI로부터 받은 답변 마크다운을 직접 붙여넣어 새 노트로 저장"""
    if req.note_id and not is_safe_note_id(req.note_id):
        raise HTTPException(status_code=400, detail="잘못된 노트 ID 입니다.")
    video_id = extract_video_id(req.url) if req.url else None
    if not video_id:
        safe_req_vid = req.video_id if (req.video_id and is_safe_note_id(req.video_id)) else None
        video_id = safe_req_vid or f"custom_{int(time.time())}"
        v_type = req.video_type or ("local" if str(video_id).startswith("local_") else "youtube")
        video_info = {
            "video_id": video_id,
            "title": req.title or "구독 AI 학습 노트",
            "channel": req.channel or "구독 AI 연동",
            "video_type": v_type,
            "url": req.url or ""
        }
    else:
        video_info = get_video_info(video_id)
        video_info["video_type"] = "youtube"

    # 항상 새로운 note_id로 독립 저장하여 이전 기록을 덮어쓰지 않음
    note_target = normalize_target_lang(req.note_target_lang or req.target_lang)
    lang_meta = {
        "source_lang": req.source_lang,
        "target_lang": req.target_lang,
        "note_target_lang": note_target,
        "translation_source": req.translation_source
    }
    save_res = save_note(
        video_info, 
        req.markdown, 
        note_id=req.note_id, 
        note_title=req.title,
        subtitles=req.subtitles,
        lang_meta=lang_meta
    )
    return {
        "success": True,
        "note_id": save_res["note_id"],
        "video_info": video_info,
        "markdown": save_res["markdown"],
        "file_path": save_res["file_path"],
        "note_target_lang": note_target,
        "audiobook": save_res.get("audiobook"),
        "subtitle_audiobook": save_res.get("subtitle_audiobook"),
    }

@app.post("/api/analyze")
def analyze_video(req: AnalyzeRequest):
    reset_analysis_cancel()
    update_analysis_state("processing", event="extracting_yt", message="유튜브 영상 정보 및 자막 추출 중...", step=1)
    video_id = extract_video_id(req.url)
    if not video_id:
        raise HTTPException(status_code=400, detail="올바른 유튜브 영상 URL 또는 Video ID가 아닙니다.")

    # 1. 메타데이터 추출
    video_info = get_video_info(video_id)
    video_info["video_type"] = "youtube"
    _raise_if_cancelled()

    target = normalize_target_lang(req.target_lang)
    note_target = normalize_target_lang(req.note_target_lang or req.target_lang)

    # 2. 자막 추출 (원문 = 실제 발화 언어, 번역 언어의 공식 자막이 있으면 함께 정렬)
    transcript_result = get_video_transcript(
        video_id, source_lang=req.source_lang, target_lang=target,
        ytdlp_lang=video_info.get("language")
    )
    _raise_if_cancelled()
    if not transcript_result.get("success"):
        raise HTTPException(
            status_code=400, 
            detail=f"자막 추출 실패: {transcript_result.get('error', '자막을 찾을 수 없습니다.')}"
        )

    # 3. Gemini 지식 확장 노트 생성
    llm_result = generate_study_note_gemini(
        video_info=video_info,
        transcript_data=transcript_result,
        model_name=req.gemini_model or DEFAULT_NOTE_MODEL,
        target_lang=note_target
    )

    _raise_if_cancelled(llm_result)
    if not llm_result.get("success"):
        raise HTTPException(
            status_code=500, 
            detail=f"학습 노트 생성 실패: {llm_result.get('error')}"
        )

    # 4. 고유 note_id로 로컬 저장 (동일 영상이라도 별도 버전으로 누적 보관)
    save_res = save_note(
        video_info, llm_result["markdown"],
        subtitles=transcript_result.get("subtitles", []),
        lang_meta=_lang_meta(transcript_result, note_target_lang=note_target)
    )

    return {
        "success": True,
        "note_id": save_res["note_id"],
        "video_info": video_info,
        "subtitles": transcript_result.get("subtitles", []),
        "is_generated": transcript_result.get("is_generated"),
        "is_korean": transcript_result.get("is_korean", False),
        "model_used": llm_result.get("model_used"),
        "markdown": save_res["markdown"],
        "file_path": save_res["file_path"],
        "note_target_lang": note_target,
        "audiobook": save_res.get("audiobook"),
        "subtitle_audiobook": save_res.get("subtitle_audiobook"),
        **_lang_payload(transcript_result)
    }

@app.post("/api/note/regenerate")
def regenerate_study_note(req: RegenerateNoteRequest):
    """기존 자막 데이터를 바탕으로 선택된 언어로 Gemini 학습 노트를 즉시 재작성"""
    reset_analysis_cancel()
    update_analysis_state("processing", event="regen_prep", message="기존 자막 기반으로 학습 노트 재작성 준비 중...", step=2)
    if req.note_id and not is_safe_note_id(req.note_id):
        raise HTTPException(status_code=400, detail="잘못된 노트 ID 입니다.")
    if not req.subtitles:
        raise HTTPException(status_code=400, detail="학습 노트 재작성을 위한 자막 데이터가 없습니다.")
    if req.note_id:
        set_checkpoint(req.note_id)

    note_target = normalize_target_lang(req.note_target_lang)

    video_info = {
        "video_id": req.video_id or f"custom_{int(time.time())}",
        "title": req.title or "학습 영상",
        "channel": req.channel or "",
        "duration_str": req.duration_str or "",
        "video_type": req.video_type or "youtube",
        "url": req.url or (f"https://www.youtube.com/watch?v={req.video_id}" if req.video_id and not req.video_id.startswith("local_") else "")
    }

    src_lang = req.source_lang or detect_text_language(req.subtitles)
    merged_chunks = _group_subtitles_into_chunks(req.subtitles, window_sec=35.0)
    full_text = "\n".join(f"[{c.get('timestamp', '00:00')}] {c.get('text', '')}" for c in (merged_chunks or req.subtitles))
    transcript_data = {
        "language": src_lang,
        "full_text": full_text,
        "chunks": merged_chunks,
        "subtitles": req.subtitles
    }

    llm_result = generate_study_note_gemini(
        video_info=video_info,
        transcript_data=transcript_data,
        model_name=req.gemini_model or DEFAULT_NOTE_MODEL,
        target_lang=note_target
    )

    _raise_if_cancelled(llm_result)
    if not llm_result.get("success"):
        raise HTTPException(
            status_code=500,
            detail=f"학습 노트 재작성 실패: {llm_result.get('error')}"
        )

    # 기존 note_id가 있으면 덮어써서 갱신, 없으면 신규 생성
    save_res = save_note(
        video_info=video_info,
        markdown_content=llm_result["markdown"],
        note_id=req.note_id,
        note_title=req.title,
        subtitles=req.subtitles,
        lang_meta={"note_target_lang": note_target}
    )

    return {
        "success": True,
        "note_id": save_res["note_id"],
        "video_info": video_info,
        "model_used": llm_result.get("model_used"),
        "markdown": save_res["markdown"],
        "file_path": save_res["file_path"],
        "note_target_lang": note_target,
        "audiobook": save_res.get("audiobook"),
        "subtitle_audiobook": save_res.get("subtitle_audiobook"),
    }

@app.post("/api/subtitles")
def get_or_translate_subtitles(req: SubtitlesRequest):
    """
    영상 자막을 조회하거나 한국어로 번역합니다.
    """
    subtitles = req.subtitles or []
    lang = "en"
    target = normalize_target_lang(req.target_lang)
    res_meta = {}
    
    if not subtitles:
        v_id = req.video_id or (extract_video_id(req.url) if req.url else None)
        # 1. 디스크 번역 캐시 우선 확인
        cached = get_cached_subtitles(req.note_id, v_id, target)
        if cached and cached.get("subtitles"):
            subtitles = cached["subtitles"]
            lang = cached.get("source_lang") or detect_text_language(subtitles)
            res_meta = {
                "source_lang": lang,
                "original_lang": lang,
                "target_lang": target,
                "translation_source": cached.get("translation_source", "gemini"),
            }
        # 2. 저장된 노트의 원문 자막 번들 확인 (로컬 영상/수동 노트 지원)
        if not subtitles and req.note_id:
            n = get_note(req.note_id)
            if n and n.get("metadata", {}).get("subtitles"):
                subtitles = n["metadata"]["subtitles"]
                lang = n["metadata"].get("source_lang") or detect_text_language(subtitles)
                res_meta = {
                    "source_lang": lang,
                    "original_lang": lang,
                    "target_lang": target,
                    "translation_source": n["metadata"].get("translation_source"),
                }
        # 3. 유튜브 영상인 경우 자막 추출
        if not subtitles:
            if not v_id or str(v_id).startswith("local_") or str(v_id).startswith("custom_"):
                raise HTTPException(status_code=400, detail="올바른 유튜브 URL 또는 Video ID가 필요합니다.")
            res = get_video_transcript(v_id, source_lang=req.source_lang, target_lang=target)
            if not res.get("success"):
                raise HTTPException(status_code=400, detail=f"자막 추출 실패: {res.get('error')}")
            subtitles = res.get("subtitles", [])
            lang = res.get("language", "en")
            res_meta = _lang_payload(res)
            if req.note_id and subtitles:
                update_note_subtitles(req.note_id, subtitles, _lang_meta(res))

    if req.translate_ko and subtitles:
        has_ko = any(s.get("ko_text") for s in subtitles)
        if not has_ko:
            subtitles = translate_subtitles_gemini(subtitles, target_lang=target, video_title=req.title)
        v_id = req.video_id or (extract_video_id(req.url) if req.url else None)
        if v_id:
            save_translation_cache(v_id, target, subtitles, "gemini")
        if req.note_id:
            update_note_subtitles(req.note_id, subtitles, {"target_lang": target, "translation_source": "gemini"})
        res_meta["translation_source"] = "gemini"

    return {
        "success": True,
        "language": lang,
        "subtitles": subtitles,
        **res_meta
    }

@app.post("/api/subtitles/reload")
def reload_subtitles(req: SubtitlesRequest):
    """
    원문 언어(트랙) 또는 번역 언어를 바꿀 때 자막을 다시 불러옵니다.
    이미 생성/보관된 번역 캐시가 있으면 최우선으로 즉시 복원하여 이전 번역 손실을 방지합니다.
    """
    v_id = req.video_id or (extract_video_id(req.url) if req.url else None)
    if not v_id and not req.note_id:
        raise HTTPException(status_code=400, detail="자막 언어를 바꿀 영상 또는 노트 정보가 없습니다.")
    if req.note_id and not is_safe_note_id(req.note_id):
        raise HTTPException(status_code=400, detail="잘못된 노트 ID 입니다.")

    target = normalize_target_lang(req.target_lang)

    # 1. 기존에 생성된 번역 캐시가 있는지 최우선 확인! (사용자가 번역했던 내용 영구 보존)
    cached = get_cached_subtitles(req.note_id, v_id, target)
    if cached and cached.get("subtitles"):
        cached_subs = cached["subtitles"]
        if any(bool(s.get("ko_text") and str(s.get("ko_text")).strip()) for s in cached_subs):
            if req.note_id:
                update_note_subtitles(req.note_id, cached_subs, {
                    "target_lang": target,
                    "translation_source": cached.get("translation_source", "gemini")
                })
            return {
                "success": True,
                "subtitles": cached_subs,
                "is_generated": False,
                "target_lang": target,
                "source_lang": cached.get("source_lang"),
                "translation_source": cached.get("translation_source", "gemini"),
                "is_same_language": False
            }

    # 2. 로컬 영상이거나 custom 노트인 경우 유튜브 API 호출 없이 원문 자막(번역 대기 상태) 반환
    if not v_id or str(v_id).startswith("local_") or str(v_id).startswith("custom_"):
        base_subs = req.subtitles or []
        if not base_subs and req.note_id:
            n = get_note(req.note_id)
            if n:
                base_subs = n.get("metadata", {}).get("subtitles") or []
        stripped_subs = [
            {k: v for k, v in s.items() if k != "ko_text"}
            for s in base_subs if isinstance(s, dict)
        ]
        return {
            "success": True,
            "subtitles": stripped_subs,
            "is_generated": False,
            "target_lang": target,
            "source_lang": req.source_lang,
            "translation_source": None,
            "is_same_language": False
        }

    # 3. 캐시가 없으면 유튜브에서 자막을 가져옴
    res = get_video_transcript(v_id, source_lang=req.source_lang, target_lang=target)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=f"자막 추출 실패: {res.get('error')}")

    subs = res.get("subtitles", [])
    if res.get("translation_source") == "youtube" or res.get("is_same_language"):
        save_translation_cache(v_id, target, subs, res.get("translation_source", "youtube"))

    if req.note_id:
        update_note_subtitles(req.note_id, subs, _lang_meta(res))

    return {
        "success": True,
        "subtitles": subs,
        "is_generated": res.get("is_generated"),
        **_lang_payload(res)
    }

@app.get("/api/subtitles/tracks")
def get_subtitle_tracks(video_id: str):
    """원문 언어 선택 상자용: 영상이 가진 자막 트랙 목록."""
    v_id = extract_video_id(video_id or "")
    if not v_id:
        raise HTTPException(status_code=400, detail="올바른 Video ID가 아닙니다.")
    return list_transcript_tracks(v_id)
 
@app.post("/api/subtitles/save")
def save_subtitles_endpoint(req: SubtitleSaveRequest):
    """사용자가 직접 수정한 자막(오타 교정, 번역문 수정 등)을 영구 저장합니다."""
    if not req.subtitles:
        raise HTTPException(status_code=400, detail="저장할 자막 데이터가 없습니다.")

    target = normalize_target_lang(req.target_lang)
    lang_meta = {
        "target_lang": target,
        "source_lang": req.source_lang,
        "translation_source": req.translation_source or "manual"
    }

    # 각 대사 텍스트에 포함되었을 수 있는 AI 인용 마커 정화
    clean_subs = []
    for s in req.subtitles:
        item = dict(s)
        if "text" in item and item["text"] is not None:
            item["text"] = clean_ai_citation_artifacts(str(item["text"]))
        if "ko_text" in item and item["ko_text"] is not None:
            item["ko_text"] = clean_ai_citation_artifacts(str(item["ko_text"]))
        clean_subs.append(item)

    saved_note = False
    if req.note_id:
        saved_note = update_note_subtitles(req.note_id, clean_subs, lang_meta)

    vid = req.video_id
    if not vid and req.note_id:
        n = get_note(req.note_id)
        if n:
            vid = n.get("metadata", {}).get("video_id") or n.get("video_id")

    if vid and not saved_note:
        has_trans = any(bool(s.get("ko_text") and str(s.get("ko_text")).strip()) for s in clean_subs)
        if has_trans:
            save_translation_cache(vid, target, clean_subs, req.translation_source or "manual")
        try:
            from tts import cleanup_stale_subtitle_audiobooks
            cleanup_stale_subtitle_audiobooks("", vid, clean_subs)
        except Exception:
            pass

    return {
        "success": True,
        "saved_note": saved_note,
        "video_id": vid,
        "message": "자막이 성공적으로 저장되었습니다."
    }

@app.post("/api/subtitles/translate-stream")
async def translate_subtitles_stream_endpoint(req: SubtitlesRequest, request: Request):
    """
    자막을 배치 단위로 번역하며 실시간 진행 상황 및 로그 이벤트를 SSE로 스트리밍합니다.
    클라이언트가 연결을 끊으면 번역 작업을 즉각 중단합니다.
    """
    subtitles = req.subtitles or []
    
    # 전달받은 자막이 비어있는 경우 note_id나 video_id/url로 자막 복구
    if not subtitles and req.note_id:
        note_data = await run_in_threadpool(get_note, req.note_id)
        if note_data and note_data.get("metadata", {}).get("subtitles"):
            subtitles = note_data["metadata"]["subtitles"]

    if not subtitles:
        v_id = req.video_id or (extract_video_id(req.url) if req.url else None)
        if v_id:
            res = await run_in_threadpool(get_video_transcript, v_id)
            if res.get("success"):
                subtitles = res.get("subtitles", [])

    is_cancelled = False
    def check_cancelled():
        nonlocal is_cancelled
        return is_cancelled

    async def event_generator():
        nonlocal is_cancelled
        # 번역(Gemini 호출 + 속도 제한 대기)은 블로킹 작업이므로 작업 스레드에서 실행
        # → 번역 중에도 노트 목록/오디오북/종료 등 다른 요청이 멈추지 않음
        target = normalize_target_lang(req.target_lang)
        gen = translate_subtitles_stream(
            subtitles, target_lang=target, is_cancelled_callback=check_cancelled, video_title=req.title
        )
        try:
            async for event in iterate_in_threadpool(gen):
                if await request.is_disconnected():
                    break
                if event.get("type") in ["complete", "cancelled"]:
                    last_subtitles = event.get("subtitles")
                    if last_subtitles:
                        v_id = req.video_id or (extract_video_id(req.url) if req.url else None)
                        if v_id:
                            await run_in_threadpool(save_translation_cache, v_id, target, last_subtitles, "gemini")
                        if req.note_id:
                            try:
                                await run_in_threadpool(
                                    update_note_subtitles, req.note_id, last_subtitles,
                                    {"target_lang": target, "translation_source": "gemini"}
                                )
                            except Exception:
                                pass
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            # 연결 종료/취소 시 작업 스레드의 번역 루프도 다음 배치에서 중단되도록 신호
            is_cancelled = True

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/api/subtitles/download")
def download_subtitles(req: SubtitleDownloadRequest):
    """
    자막 목록을 지정된 언어 및 포맷(.srt 또는 .txt)으로 변환하여 반환
    """
    if not req.subtitles:
        raise HTTPException(status_code=400, detail="다운로드할 자막 데이터가 없습니다.")

    fmt = req.format.lower() if req.format else "srt"
    mode = req.lang_mode.lower() if req.lang_mode else "original"
    subtitles = req.subtitles
    target = normalize_target_lang(req.target_lang)
    target_name = language_name(target)

    if mode in ["ko", "bilingual"]:
        has_ko = any(s.get("ko_text") for s in subtitles)
        if not has_ko:
            if req.auto_translate:
                subtitles = translate_subtitles_gemini(subtitles, target_lang=target, video_title=req.title)
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"{target_name} 번역이 아직 생성되지 않았습니다. 먼저 화면의 [{target_name} 번역 요청] 버튼을 눌러 번역을 완료해주세요."
                )

    if fmt == "txt":
        content = convert_to_txt(subtitles, lang_mode=mode)
        ext = "txt"
    else:
        content = convert_to_srt(subtitles, lang_mode=mode, sync_offset=float(req.sync_offset or 0.0))
        ext = "srt"

    safe_title = re.sub(r'[/\\?%*:|"<> ]+', '_', req.title or "subtitles").strip('_')
    mode_tag = {"original": "원문", "ko": f"{target_name}번역", "bilingual": f"{target_name}병기"}.get(mode, mode)
    filename = f"{safe_title}_{mode_tag}.{ext}"

    return {
        "success": True,
        "filename": filename,
        "content": content,
        "subtitles": subtitles
    }

@app.get('/api/library')
def query_study_library(
    q: str = Query(default='', max_length=200), collection_id: str = '',
    tag: str = '', status: Literal['', 'unread', 'learning', 'completed', 'review'] = '',
    source: Literal['', 'youtube', 'local'] = '', language: str = '',
    starred: bool = False, trash: bool = False,
    sort: Literal['newest', 'updated', 'opened', 'title', 'collection'] = 'newest',
    offset: int = Query(default=0, ge=0), limit: int = Query(default=40, ge=1, le=100),
    topic: str = Query(default='', max_length=40),
):
    return library_manager.query_library(q, collection_id, tag, status, source, language,
                                         starred, trash, sort, offset, limit, topic)


@app.post('/api/library/collections')
def create_study_collection(req: CollectionRequest):
    return library_manager.create_collection(req.name, req.source.model_dump())


@app.patch('/api/library/collections/{collection_id}')
def rename_study_collection(collection_id: str, req: CollectionRenameRequest):
    return library_manager.edit_collection(collection_id, name=req.name)


@app.put('/api/library/collections/{collection_id}/order')
def reorder_study_collection(collection_id: str, req: CollectionOrderRequest):
    return library_manager.edit_collection(collection_id, note_ids=req.note_ids)


@app.delete('/api/library/collections/{collection_id}')
def remove_study_collection(collection_id: str):
    return library_manager.edit_collection(collection_id, delete=True)


@app.post('/api/library/notes/bulk')
def bulk_manage_notes(req: LibraryBulkRequest):
    return library_manager.bulk_update(**req.model_dump())


@app.post('/api/library/export')
def export_library_notes(req: LibraryExportRequest):
    return StreamingResponse(library_manager.export_notes(req.note_ids), media_type='application/zip',
                             headers={'Content-Disposition': 'attachment; filename="TubeScholar-notes.zip"'})


@app.post('/api/library/notes/{note_id}/opened')
def record_library_open(note_id: str):
    return library_manager.record_opened(note_id)


@app.get("/api/notes")
def get_notes():
    return {"notes": list_saved_notes()}

@app.get("/api/notes/{note_id}")
def get_single_note(note_id: str):
    note = get_note(note_id)
    if not note:
        raise HTTPException(status_code=404, detail="저장된 학습 노트를 찾을 수 없습니다.")
    if note["metadata"].get("video_type") == "local":
        note["metadata"]["local_video_available"] = bool(local_video_path(note["metadata"].get("local_video")))
    return note


@app.get("/api/notes/{note_id}/video")
def get_saved_video(note_id: str):
    note = get_note(note_id) if is_safe_note_id(note_id) else None
    path = local_video_path(note["metadata"].get("local_video")) if note and note["metadata"].get("video_type") == "local" else None
    if not path:
        raise HTTPException(404, "보관된 영상이 없습니다. 원본 파일을 다시 연결해 주세요.")
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    if not mime.startswith(("video/", "audio/")):
        mime = "application/octet-stream"
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@app.post("/api/notes/{note_id}/video")
def reconnect_saved_video(note_id: str, video: UploadFile = File(...)):
    if not is_safe_note_id(note_id):
        raise HTTPException(400, "잘못된 노트 ID입니다.")
    try:
        reference = attach_note_video(note_id, video.file, video.filename, check_analysis, analysis_commit)
        return {"success": True, "local_video": reference}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        video.file.close()

@app.put("/api/notes/{note_id}")
def update_single_note(note_id: str, req: UpdateNoteRequest):
    """사용자가 직접 편집한 마크다운을 저장"""
    if not is_safe_note_id(note_id):
        raise HTTPException(status_code=400, detail="잘못된 노트 ID 입니다.")
    res = update_note(note_id, req.markdown)
    if not res:
        raise HTTPException(status_code=404, detail="수정할 노트를 찾을 수 없습니다.")
    return {"success": True, "note": res}

@app.delete("/api/notes/{note_id}")
def remove_note(note_id: str):
    if not is_safe_note_id(note_id):
        raise HTTPException(status_code=400, detail="잘못된 노트 ID 입니다.")
    return library_manager.bulk_update([note_id], 'trash')

@app.post("/api/channel/videos")
def channel_videos(req: ChannelRequest):
    if not req.channel_url or not is_valid_youtube_channel_url(req.channel_url):
        raise HTTPException(status_code=400, detail="올바른 유튜브 채널 URL(예: @채널명 또는 https://youtube.com/@...)을 입력해주세요.")
    safe_max = min(max(1, int(req.max_results or 15)), 50)
    videos = get_channel_videos(req.channel_url, max_results=safe_max)
    return {"videos": videos}

# ============================================================
# 🎧 edge-tts 오디오북 엔드포인트
# ============================================================
@app.get("/api/tts/voices")
def get_tts_voices(lang: Optional[str] = None):
    """사용 가능한 신경망 음성 목록 반환 (언어별 필터링 지원)"""
    return {"voices": list_available_voices(lang=lang)}

@app.post("/api/tts/generate")
async def generate_tts_endpoint(req: TTSRequest):
    """마크다운 노트를 자연스러운 한국어 오디오북 MP3로 생성/캐싱"""
    text = req.markdown or ""
    title = (req.title or "").strip()
    if req.note_id:
        note = await run_in_threadpool(get_note, req.note_id)
        if note:
            if not text.strip():
                text = note.get("markdown", "")
            if not title:
                title = note.get("metadata", {}).get("title", "")

    if not title and text:
        m = re.search(r"^#+\s*(.+)$", text.strip(), re.MULTILINE)
        if m:
            title = m.group(1).strip()

    if not text.strip():
        raise HTTPException(status_code=400, detail="음성 변환할 노트 내용이 없습니다.")
    
    res = await generate_note_audio(
        note_id=req.note_id or "temp_note",
        markdown_text=text,
        voice_key=req.voice or "injoon",
        speed=req.speed or "+0%"
    )
    if not res.get("success"):
        raise HTTPException(status_code=500, detail=res.get("error", "음성 변환 실패"))

    res["short_title"] = abbreviate_note_title(title)
    res["download_filename"] = get_audiobook_download_filename(title)
    if req.note_id and req.note_id not in ("temp_note", "current_note"):
        try:
            await run_in_threadpool(
                update_note_audiobook,
                req.note_id,
                None,
                {"filename": res["filename"], "voice_key": res.get("voice_key", req.voice or "injoon")},
                None,
            )
        except Exception:
            pass
    return res

@app.post("/api/tts/subtitles")
async def generate_subtitles_tts_endpoint(req: SubtitleTTSRequest):
    """자막 대사를 자연스러운 더빙 오디오북 MP3로 생성/캐싱"""
    subs = req.subtitles or []
    title = (req.title or "").strip()
    lookup_id = req.note_id or req.video_id
    if lookup_id and (not subs or not title or title in ("자막", "학습노트", "subtitles", "study_note")):
        note = await run_in_threadpool(get_note, lookup_id)
        if note:
            if not subs:
                subs = note.get("metadata", {}).get("subtitles", [])
            if not title or title in ("자막", "학습노트", "subtitles", "study_note"):
                title = note.get("metadata", {}).get("title", "") or title
    
    if not subs:
        raise HTTPException(status_code=400, detail="음성 변환할 자막 데이터가 없습니다.")

    res = await generate_subtitles_audio(
        subtitles=subs,
        video_id=req.video_id or req.note_id or "subtitles",
        title=title or "자막",
        mode=req.mode or "ko",
        voice_key=req.voice or "injoon",
        speed=req.speed or "+0%"
    )
    if not res.get("success"):
        raise HTTPException(status_code=500, detail=res.get("error", "자막 음성 변환 실패"))

    res["short_title"] = abbreviate_note_title(title or "자막")
    res["download_filename"] = get_audiobook_download_filename(title or "자막", is_subtitles=True)
    if req.note_id or req.video_id:
        try:
            await run_in_threadpool(
                update_note_audiobook,
                req.note_id,
                req.video_id,
                None,
                {
                    "filename": res["filename"],
                    "voice_key": res.get("voice_key", req.voice or "injoon"),
                    "mode": res.get("mode", "dub"),
                },
            )
        except Exception:
            pass
    return res

@app.get("/api/tts/audio/{filename}")
def get_tts_audio_file(
    filename: str,
    download: Optional[bool] = False,
    title: Optional[str] = None
):
    """생성된 MP3 파일 서빙 (재생 시 inline 스트리밍 및 기본 파일명 헤더 제공, 다운로드 시 attachment 적용)"""
    safe_filename = os.path.basename(filename)
    if not safe_filename or not safe_filename.endswith(".mp3"):
        raise HTTPException(status_code=400, detail="오디오 파일(.mp3)만 접근할 수 있습니다.")
    filepath = os.path.join(AUDIO_DIR, safe_filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="오디오 파일을 찾을 수 없습니다.")

    resolved_title = (title or "").strip()
    is_sub = safe_filename.startswith("sub_")
    if not resolved_title or resolved_title in ("자막", "학습노트", "subtitles", "study_note", "temp_note"):
        # 파일명 앞부분에서 note_id 또는 video_id 추출하여 보관함 제목 탐색
        for v in list_available_voices():
            v_token = f"_{v['key']}_"
            if v_token in safe_filename:
                possible_nid = safe_filename.split(v_token)[0]
                if possible_nid.startswith("sub_"):
                    possible_nid = re.sub(r'_(?:dub|orig|ko|bilingual|original)$', '', possible_nid[4:])
                note = get_note(possible_nid)
                if note:
                    resolved_title = note.get("metadata", {}).get("title", "") or resolved_title
                break

    dl_filename = get_audiobook_download_filename(
        resolved_title or ("자막" if is_sub else "학습노트"),
        is_subtitles=is_sub,
    )
    disposition = "attachment" if download else "inline"
    return FileResponse(
        filepath,
        media_type="audio/mpeg",
        filename=dl_filename,
        content_disposition_type=disposition,
    )

@app.post("/api/system/browser-close")
def browser_close_signal():
    """브라우저 창/탭 닫힘 시 3.0초 후 프로세스 종료 (F5 새로고침인 경우 다음 요청 수신 시 취소)"""
    global _shutdown_timer
    with _shutdown_lock:
        if _shutdown_timer is not None:
            _shutdown_timer.cancel()
        _shutdown_timer = threading.Timer(3.0, _perform_exit)
        _shutdown_timer.daemon = True
        _shutdown_timer.start()
    return {"status": "closing"}

@app.post("/api/system/heartbeat")
def system_heartbeat():
    """브라우저 활성 생존 신호 수신 (브라우저 창 종료 감지용)"""
    global _last_heartbeat, _heartbeat_received
    _last_heartbeat = time.time()
    _heartbeat_received = True
    cancel_shutdown()
    return {"status": "ok"}

@app.post("/api/system/shutdown")
def shutdown_app():
    """웹 UI에서 안전하게 애플리케이션 종료"""
    def _shutdown():
        time.sleep(0.5)
        os._exit(0)
    threading.Thread(target=_shutdown, daemon=True).start()
    return {"success": True, "message": "TubeScholar 서버가 종료됩니다."}

@app.get("/api/prompts/templates")
def api_list_prompt_templates():
    """사용 가능한 마크다운 템플릿 목록 및 커스텀 상태 반환"""
    return {
        "success": True,
        "templates": list_available_templates(),
        "user_prompts_dir": get_user_prompts_dir()
    }

@app.post("/api/prompts/open-folder")
def api_open_prompts_folder():
    """사용자 커스텀 프롬프트 마크다운 폴더를 윈도우 탐색기로 엽니다."""
    folder = get_user_prompts_dir()
    try:
        if os.name == "nt":
            os.startfile(folder)
        else:
            import subprocess
            subprocess.run(["xdg-open", folder])
        return {"success": True, "path": folder}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

# 프론트엔드 정적 파일 서빙
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"), headers={"Cache-Control": "no-cache"})

    @app.get("/favicon.ico")
    def serve_favicon():
        fav_path = os.path.join(FRONTEND_DIR, "favicon.ico")
        if os.path.exists(fav_path):
            return FileResponse(fav_path, media_type="image/x-icon", headers={"Cache-Control": "no-cache, must-revalidate"})
        return JSONResponse(status_code=404, content={"detail": "Not found"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
