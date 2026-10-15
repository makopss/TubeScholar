import os
import re
import time
import threading
import asyncio
import logging
from typing import Dict, Any, Optional, List, Tuple
from google import genai
from google.genai import types
from config import suppress_genai_warnings
from languages import language_name
from prompt_loader import get_system_prompt_for_lang
from analysis_jobs import (
    get_analysis_state, update_analysis_state, request_analysis_cancel,
    reset_analysis_cancel, is_analysis_cancelled, interruptible_sleep as _interruptible_sleep,
    run_async_operation, check_analysis, remaining_seconds, AnalysisStopped,
)

suppress_genai_warnings()

# 1) 학습 노트 심층 생성용 모델 (응답 안정성이 검증된 3.5/3.6 Flash 및 Lite 모델을 최우선 배치하고 혼잡 모델을 후순위로 배치)
DEFAULT_NOTE_MODEL = "gemini-3.5-flash"
FALLBACK_NOTE_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
]
DEFAULT_GEMINI_MODEL = DEFAULT_NOTE_MODEL
FALLBACK_GEMINI_MODELS = FALLBACK_NOTE_MODELS

# 2) 한국어 및 다국어 자막 번역 전담 모델 (Lite 우선: 일반 Lite Latest -> 개별 Lite -> 안정적 Flash 순환)
DEFAULT_TRANSLATE_MODEL = "gemini-flash-lite-latest"
FALLBACK_TRANSLATE_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-flash-latest",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
]

log = logging.getLogger("tubescholar.analysis")


def _gemini_io(api_key, operation, timeout_sec, *, check_job=True):
    """Use cancellable async transports and close both clients on every attempt."""
    timeout_sec = remaining_seconds(timeout_sec) if check_job else timeout_sec

    async def invoke():
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=max(1, int(timeout_sec * 1000)),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        try:
            return await operation(client.aio)
        finally:
            try:
                await asyncio.wait_for(client.aio.aclose(), timeout=2.0)
            finally:
                client.close()

    return run_async_operation(invoke, timeout_sec, check_job=check_job)


def _call_generate_content_interruptible(api_key, model, contents, config, timeout_sec=65.0):
    return _gemini_io(
        api_key,
        lambda aio: aio.models.generate_content(model=model, contents=contents, config=config),
        timeout_sec,
    )


def format_model_label(model: str) -> str:
    labels = {
        "gemini-flash-latest": "Gemini 최신 Flash",
        "gemini-flash-lite-latest": "Gemini 최신 Flash Lite",
        "gemini-3.8-flash": "Gemini 3.8 Flash",
        "gemini-3.7-flash": "Gemini 3.7 Flash",
        "gemini-3.6-flash": "Gemini 3.6 Flash",
        "gemini-3.5-flash": "Gemini 3.5 Flash",
        "gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite",
        "gemini-3.1-flash-lite": "Gemini 3.1 Flash Lite",
    }
    return labels.get(model, model)


# 4) 자막 번역 RPM(분당 요청수) 엄격 제어 설정
# Gemini Free Tier (15 RPM) 기준, 5.0초 간격 보장 시 분당 최대 12회(20% 안전 버퍼)로 429 에러 원천 차단
TRANSLATE_MIN_INTERVAL = 5.0
_last_translate_time: float = 0.0
_rate_lock = threading.Lock()


def _wait_for_rate_limit(min_interval: float = TRANSLATE_MIN_INTERVAL):
    """
    Gemini API 호출 주기를 min_interval(기본 5.0초) 이상으로 보장하여
    분당 호출수를 최대 12회(15 RPM 한도 대비 20% 안전 버퍼)로 엄격히 통제합니다.
    (번역이 작업 스레드에서 동시에 돌 수 있으므로 잠금으로 보호)
    """
    global _last_translate_time
    with _rate_lock:
        now = time.time()
        elapsed = now - _last_translate_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_translate_time = time.time()


def _mark_rate_limit_now():
    """429 등으로 강제 대기한 직후 기준 시각을 갱신합니다."""
    global _last_translate_time
    with _rate_lock:
        _last_translate_time = time.time()


# 하위 호환성을 위해 prompt_loader의 get_system_prompt_for_lang을 사용합니다.
# 실제 마크다운 템플릿은 prompts/ 디렉토리 및 사용자 커스텀 data/prompts/에서 동적으로 로드됩니다.
SYSTEM_PROMPT = ''
SYSTEM_PROMPT_KOREAN = ''
SYSTEM_PROMPT_ENGLISH = ''
SYSTEM_PROMPT_JAPANESE = ''


def build_user_prompt(
    video_info: Dict[str, Any],
    transcript_text: str,
    source_lang: str = "en",
    target_lang: str = "ko"
) -> str:
    title = video_info.get("title", "")
    channel = video_info.get("channel", "")
    duration = video_info.get("duration_str", "")
    target = (target_lang or "ko").lower()
    target_name = language_name(target)

    if target.startswith("en"):
        instruction = (
            "Analyze the above video and transcript according to its Meta Archetype (Review & Critique / Story & Interpretation / Guide & How-To / Explainer & Deep Knowledge / Dialogue & Interview).\n"
            "Generate the comprehensive Master Deep Learning Note entirely in English.\n"
            "Make sure to include all proper nouns, their origins/etymology, video context, dense chronological deep dives, and the 3-stage quiz."
        )
        meta_label = f"- Title: {title}\n- Channel: {channel}\n- Duration: {duration}\n- Transcript Language: {source_lang}"
        req_header = "[Instructions]:"
    elif target.startswith("ja"):
        instruction = (
            "上記動画の性格（5大メタ原型）を分析し、最も最適化されたマスター深層学習ノートをすべて日本語で作成してください。\n"
            "動画内に登場する重要な固有名詞の語源・命名由来辞典、およびタイムライン別の深層解説、3段階クイズを必ず含めてください。"
        )
        meta_label = f"- タイトル: {title}\n- チャンネル名: {channel}\n- 再生時間: {duration}\n- 字幕言語: {source_lang}"
        req_header = "[作成依頼]:"
    elif target == "ko":
        if (source_lang or "").startswith("ko"):
            instruction = (
                "위 한국어 영상의 성격(5대 메타 원형: 분석·평가형 / 스토리·해석형 / 가이드·공략형 / 지식·정보형 / 대화·인터뷰형)을 파악하여 가장 최적화된 마스터 지식 노트를 작성해 주십시오.\n"
                "이 영상은 한국어 원본입니다. 번역이 아닌, 구어체 정돈과 지식 확장에 집중하십시오.\n"
                "특히 영상 본문에 실제로 등장하는 주요 고유명사(인물, 기관/기업, 지명/천체, 프로젝트, 이론/법칙 등)를 집중 수집하여 "
                "영문 원어 병기, 어원과 명명 유래, 영상 속 맥락을 풍부하게 정리한 키워드 사전과, 촘촘한 타임라인별 Deep Dive 해설을 반드시 포함해 주십시오."
            )
        else:
            instruction = (
                "위 영상의 성격(5대 메타 원형: 분석·평가형 / 스토리·해석형 / 가이드·공략형 / 지식·정보형 / 대화·인터뷰형)을 파악하여 가장 최적화된 마스터 지식 노트를 한국어로 작성해 주십시오.\n"
                "특히 영상 본문에 실제로 등장하는 주요 고유명사(인물, 기관/기업, 지명/천체, 프로젝트, 이론/법칙 등)를 집중 수집하여 "
                "어원과 명명 유래, 영상 속 맥락을 풍부하게 정리한 키워드 사전과, 촘촘한 타임라인별 Deep Dive 해설을 반드시 포함해 주십시오."
            )
        meta_label = f"- 제목: {title}\n- 채널명: {channel}\n- 영상 길이: {duration}\n- 자막 언어: {source_lang}"
        req_header = "[작성 요청]:"
    else:
        instruction = (
            f"Analyze the video transcript and metadata to create a comprehensive Master Deep Learning Note entirely in {target_name} ({target}).\n"
            f"All text, headings, and explanations must be written in {target_name}."
        )
        meta_label = f"- Title: {title}\n- Channel: {channel}\n- Duration: {duration}\n- Language: {source_lang}"
        req_header = f"[Instructions - Language: {target_name}]:"

    return f"""
[Metadata]
{meta_label}

[Transcript]
{transcript_text}

{req_header}
{instruction}
"""


def _build_models_to_try(preferred_model: Optional[str], fallback_models: List[str]) -> List[str]:
    models: List[str] = []
    first = preferred_model or os.environ.get("GEMINI_MODEL") or DEFAULT_NOTE_MODEL
    models.append(first)
    for fb in fallback_models:
        if fb not in models:
            models.append(fb)
    return models


def _generate_with_model_fallback(
    api_key: str,
    contents: Any,
    system_instruction: str,
    models_to_try: List[str],
    mode_label: str = "note",
    log_lang_label: str = "",
) -> Dict[str, Any]:
    """
    2라운드(Safety Cycle) × 모델 폴백 × 2회 재시도 루프를 공통 수행합니다.
    503 과부하 시 대기 없이 즉시 다음 모델로 전환(Fast-Failover)하고,
    사용자 중단(Cancel) 신호가 감지되면 즉시 루프를 탈출합니다.
    """
    is_audio = mode_label == "audio"
    last_error = ""

    for cycle in range(1, 3):
        for target_model in models_to_try:
            model_lbl = format_model_label(target_model)
            for attempt in range(1, 3):
                if is_analysis_cancelled():
                    return {
                        "success": False,
                        "cancelled": True,
                        "error": "사용자에 의해 분석이 중단되었습니다.",
                    }

                try:
                    attempt_str = f" (재시도 {attempt}/2)" if attempt > 1 else ""
                    cycle_str = " [2차 복구]" if cycle > 1 else ""
                    if target_model != models_to_try[0] or cycle > 1:
                        evt = "audio_switching" if is_audio else "switching"
                        msg = (
                            f"🔄 대체 모델 전환: {model_lbl} 음성 분석 중...{attempt_str}{cycle_str}"
                            if is_audio
                            else f"🔄 대체 모델 전환: {model_lbl} 모델로 학습 노트를 생성하고 있습니다...{attempt_str}{cycle_str}"
                        )
                        update_analysis_state("fallback", model=target_model, event=evt, attempt=attempt, cycle=cycle, message=msg, step=2)
                    else:
                        evt = "audio_connecting" if is_audio else "connecting"
                        msg = (
                            f"{model_lbl} 음성 분석 중...{attempt_str}"
                            if is_audio
                            else f"{model_lbl} 연결 중... 문맥 분석 및 지식 노트를 생성하고 있습니다.{attempt_str}"
                        )
                        update_analysis_state("processing", model=target_model, event=evt, attempt=attempt, cycle=cycle, message=msg, step=2)

                    if is_audio:
                        log.info(f"[*] Gemini 음성 분석 요청 중... (모델: {target_model}{attempt_str}{cycle_str})")
                    else:
                        log.info(f"[*] Gemini ({log_lang_label}) 학습 노트 생성 요청 중... (모델: {target_model}{attempt_str}{cycle_str})")

                    check_analysis()
                    response = _call_generate_content_interruptible(
                        api_key=api_key,
                        model=target_model,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.3,
                        ),
                        timeout_sec=95.0 if is_audio else 75.0,
                    )

                    if is_analysis_cancelled():
                        return {
                            "success": False,
                            "cancelled": True,
                            "error": "사용자에 의해 분석이 중단되었습니다.",
                        }

                    if not response or not (getattr(response, "text", None) or "").strip():
                        raise RuntimeError(f"503 Empty response from {target_model}")

                    candidates = getattr(response, "candidates", None) or []
                    finish = str(getattr(candidates[0], "finish_reason", "")) if candidates else ""
                    if "MAX_TOKENS" in finish:
                        raise RuntimeError("503 Truncated model response (MAX_TOKENS)")
                    done_evt = "audio_completed" if is_audio else "completed"
                    done_msg = f"✅ {model_lbl} 음성 분석 완료!" if is_audio else f"✅ {model_lbl} 분석 완료! 문서 렌더링 중..."
                    log.info(f"[*] Gemini {'음성 분석' if is_audio else '학습 노트 생성'} 완료! (사용 모델: {target_model})")
                    update_analysis_state("completed", model=target_model, event=done_evt, message=done_msg, step=3)
                    return {
                        "success": True,
                        "text": response.text,
                        "model_used": target_model,
                    }
                except Exception as e:
                    if is_analysis_cancelled() or "CANCELLED_BY_USER" in str(e):
                        return {
                            "success": False,
                            "cancelled": True,
                            "error": "사용자에 의해 분석이 중단되었습니다.",
                        }

                    if isinstance(e, AnalysisStopped):
                        raise
                    check_analysis()
                    last_error = str(e)
                    is_503 = any(
                        kw in last_error
                        for kw in [
                            "503",
                            "UNAVAILABLE",
                            "high demand",
                            "Overloaded",
                            "시간 초과",
                            "timed out",
                            "timeout",
                            "Timeout",
                            "Deadline",
                            "disconnected",
                            "Connection",
                            "RemoteProtocolError",
                            "Empty response",
                        ]
                    )
                    is_rate_limit = any(kw in last_error for kw in ["429", "RESOURCE_EXHAUSTED"])
                    is_retryable = is_503 or is_rate_limit or any(
                        kw in last_error for kw in ["404", "NOT_FOUND", "500", "502", "504", "INTERNAL", "ServerError"]
                    )

                    if not is_retryable:
                        update_analysis_state("error", model=target_model, event="error", message=f"Gemini 오류 발생: {last_error[:100]}", step=2)
                        return {"success": False, "error": f"Gemini 생성 중 오류 발생: {last_error}"}

                    if is_503:
                        fail_msg = f"⚠️ {model_lbl} 서버 혼잡/지연 감지. 대기 없이 다음 대체 모델로 즉시 전환합니다..."
                        log.info(f"[!] {target_model} 서버 과부하/응답 지연 감지 ({last_error[:90]}) -> 다음 대체 모델로 즉시 전환")
                        update_analysis_state("fallback", model=target_model, event="503_failover", message=fail_msg, step=2)
                        break

                    if is_rate_limit and attempt < 2:
                        rate_msg = f"⏳ {model_lbl} 분당 요청 한도(429) 감지. 2초 후 재시도합니다..."
                        log.info(f"[!] {target_model} 요청 한도(429) 감지. 2.0초 대기 후 재시도...")
                        update_analysis_state("processing", model=target_model, event="rate_limit", attempt=attempt, message=rate_msg, step=2)
                        if _interruptible_sleep(2.0):
                            return {"success": False, "cancelled": True, "error": "사용자에 의해 분석이 중단되었습니다."}
                        continue
                    else:
                        fail_msg = f"⚠️ {model_lbl} 호출 실패. 다음 대체 모델을 시도합니다..."
                        log.info(f"[!] {target_model} 호출 실패 ({last_error[:120]}...). 대체 모델을 시도합니다.")
                        update_analysis_state("fallback", model=target_model, event="fail_next", message=fail_msg, step=2)
                        if _interruptible_sleep(0.3):
                            return {"success": False, "cancelled": True, "error": "사용자에 의해 분석이 중단되었습니다."}
                        break

        if cycle == 1:
            log.info("[!] 1차 모델 순회 중 일시적 서버 과부하가 지속되어 2.0초 후 2차 복구 사이클을 진행합니다...")
            update_analysis_state("fallback", event="cycle2", message="서버 일시 혼잡 지속으로 2차 복구 사이클을 준비 중입니다...", step=2)
            if _interruptible_sleep(2.0):
                return {"success": False, "cancelled": True, "error": "사용자에 의해 분석이 중단되었습니다."}

    update_analysis_state("error", event="error", message=f"Gemini 생성 실패: {last_error[:100]}", step=2)
    return {"success": False, "error": f"Gemini 생성 중 오류 발생: {last_error}"}


# 1. Google Gemini API 생성기 (무료 티어 지원)
def generate_study_note_gemini(
    video_info: Dict[str, Any],
    transcript_data: Dict[str, Any],
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    target_lang: str = "ko"
) -> Dict[str, Any]:
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return {
            "success": False,
            "error": "Gemini API 키가 설정되지 않았습니다. 설정창에서 무료 API 키를 등록해주세요."
        }

    transcript_text = transcript_data.get("full_text", "")
    if not transcript_text.strip():
        return {"success": False, "error": "분석할 자막 텍스트가 없습니다."}

    source_lang = transcript_data.get("language", "en")
    active_system_prompt = get_system_prompt_for_lang(target_lang, source_lang)
    user_prompt = build_user_prompt(video_info, transcript_text, source_lang=source_lang, target_lang=target_lang)

    target_name = language_name(target_lang)
    log.info(f"[*] 자막 언어 감지: {source_lang} -> 목표 언어: {target_name} ({target_lang})")

    models_to_try = _build_models_to_try(model_name, FALLBACK_NOTE_MODELS)
    gen_res = _generate_with_model_fallback(
        api_key=key,
        contents=user_prompt,
        system_instruction=active_system_prompt,
        models_to_try=models_to_try,
        mode_label="note",
        log_lang_label=target_name,
    )
    if not gen_res.get("success"):
        return gen_res

    return {
        "success": True,
        "markdown": gen_res["text"],
        "engine": "gemini",
        "model_used": gen_res["model_used"],
    }


def generate_study_note_from_audio(
    audio_path: str,
    video_title: str = "로컬 비디오",
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    target_lang: str = "ko"
) -> Dict[str, Any]:
    """
    자막이 없는 로컬 영상의 오디오 파일을 Gemini Files API로 직접 전달하여,
    Gemini가 음성을 듣고 타임스탬프 학습 노트를 지정된 언어로 자동 생성합니다.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return {"success": False, "error": "Gemini API 키가 필요합니다."}

    if is_analysis_cancelled():
        return {"success": False, "cancelled": True, "error": "사용자에 의해 분석이 중단되었습니다."}

    # 1. 오디오 파일 업로드
    uploaded_file = None
    try:
        update_analysis_state(
            "processing",
            event="audio_uploading",
            message="오디오 트랙을 Gemini 멀티모달 서버로 전송 중...",
            step=1,
        )
        uploaded_file = _gemini_io(key, lambda aio: aio.files.upload(file=audio_path), 60.0)
    except Exception as e:
        return {"success": False, "error": f"오디오 업로드 실패: {str(e)}"}

    models_to_try = _build_models_to_try(model_name, FALLBACK_GEMINI_MODELS)
    try:
        while "PROCESSING" in str(getattr(uploaded_file, "state", "")):
            update_analysis_state("processing", event="audio_processing", message="업로드한 오디오 처리 대기 중...", step=2)
            _interruptible_sleep(0.5)
            uploaded_file = _gemini_io(key, lambda aio: aio.files.get(name=uploaded_file.name), 15.0)
        if "FAILED" in str(getattr(uploaded_file, "state", "")):
            return {"success": False, "error": "Gemini 서버에서 오디오 파일을 처리하지 못했습니다."}
        target = (target_lang or "ko").lower()
        target_name = language_name(target)
        active_system_prompt = get_system_prompt_for_lang(target, "en")

        if target.startswith("en"):
            req_instruction = "Generate the comprehensive Master Deep Learning Note entirely in English, capturing key proper nouns, their origins/etymology, dense chronological deep dives, and the 3-stage quiz."
            sub_instruction = "Output all spoken dialogues as standard SRT subtitle format."
        elif target.startswith("ja"):
            req_instruction = "5大メタ原型に合わせた最高峰のマスター深層学習ノートをすべて日本語で作成してください。固有名詞の語源・命名由来辞典、タイムライン別Deep Dive解説、理解度チェッククイズを含めてください。"
            sub_instruction = "音声の発話を標準SRT字幕形式で漏れなく作成してください。"
        elif target == "ko":
            req_instruction = (
                "정확한 타임스탬프([MM:SS])와 함께 5대 메타 원형(분석·평가형, 스토리·해석형, 가이드·공략형, 지식·정보형, 대화·인터뷰형)에 맞춤화된 최고급 심화 지식 확장 마스터 노트를 작성해 주십시오.\n"
                "음성 본문에 실제로 언급되는 중요한 고유명사(인물, 기관/기업, 프로젝트, 지명/천체 등)와 전문용어를 빠짐없이 포착하여 '유형 분류, 어원(Etymology) 및 명명 유래'가 담긴 사전과, 작동 원리와 배경 지식을 'Deep Dive(지식 보충)' 박스로 풍부하게 설명하고, 이해도 점검 퀴즈를 포함해 주십시오."
            )
            sub_instruction = "오디오의 발화 대사를 표준 SRT 자막 형식(1부터 시작하는 자막 번호, 00:00:00,000 --> 00:00:00,000 타임코드, 대사)으로 빠짐없이 작성해 주십시오."
        else:
            req_instruction = f"Generate the comprehensive Master Deep Learning Note strictly and entirely in {target_name} ({target}), capturing proper nouns, their origins/etymology, chronological deep dives, and quizzes."
            sub_instruction = "Output the spoken dialogues in standard SRT subtitle format."

        audio_prompt = f"""
    [Video Information]
    - Title: {video_title}
    - Audio File: Attached Audio
    - Target Language: {target_name} ({target})

    Please listen carefully to the attached audio, analyze it, and output clearly divided into the following two sections:

    ===STUDY_NOTE===
    {req_instruction}

    ===SUBTITLES_SRT===
    {sub_instruction}
    """

        gen_res = _generate_with_model_fallback(
            api_key=key,
            contents=[uploaded_file, audio_prompt],
            system_instruction=active_system_prompt,
            models_to_try=models_to_try,
            mode_label="audio",
            log_lang_label=target_name,
        )
    finally:
        # 임시 업로드 파일 정리
        try:
            if uploaded_file:
                _gemini_io(key, lambda aio: aio.files.delete(name=uploaded_file.name), 3.0, check_job=False)
        except Exception as exc:
            log.warning("Gemini upload cleanup failed: %s", type(exc).__name__)

    if not gen_res.get("success"):
        return gen_res

    markdown_output = gen_res["text"]
    used_model = gen_res["model_used"]

    study_note = markdown_output
    subtitles = []
    srt_raw = ""

    if "===SUBTITLES_SRT===" in markdown_output:
        parts = markdown_output.split("===SUBTITLES_SRT===")
        study_part = parts[0].replace("===STUDY_NOTE===", "").strip()
        srt_raw = parts[1].strip()
        study_note = study_part
    elif "===STUDY_NOTE===" in markdown_output:
        study_note = markdown_output.replace("===STUDY_NOTE===", "").strip()

    srt_raw = re.sub(r"(?m)^\s*```(?:srt|vtt)?\s*$", "", srt_raw)
    if srt_raw and re.search(r"(?m)^\s*(?:\d{1,2}:)?\d{2}:\d{2}[,.]\d{1,3}\s*-->", srt_raw):
        try:
            from extractor import parse_srt_vtt_text
            parsed = parse_srt_vtt_text(srt_raw)
            subtitles = parsed.get("subtitles", [])
            if any(not s.get("text", "").strip() or s.get("end", 0) <= s.get("start", 0) for s in subtitles):
                subtitles = []
        except Exception:
            pass

    if not study_note.strip():
        return {"success": False, "error": "음성 분석 응답에 학습 노트가 없습니다."}
    # Notes are not dialogue. Missing/invalid SRT stays explicitly unavailable.
    subtitle_status = "complete" if subtitles else "unavailable"
    warning = None if subtitles else "음성 학습 노트는 생성했으나 원문 자막을 생성하지 못했습니다. 자막 파일을 별도로 선택해 주세요."

    return {
        "success": True,
        "markdown": study_note,
        "subtitles": subtitles,
        "srt_raw": srt_raw,
        "subtitle_status": subtitle_status,
        "warning": warning,
        "engine": "gemini_audio",
        "model_used": used_model
    }

def _build_translation_prompt(
    batch: List[Dict[str, Any]],
    context_before: Optional[List[Dict[str, Any]]] = None,
    context_after: Optional[List[Dict[str, Any]]] = None,
    video_title: Optional[str] = None,
    target_lang: str = "ko"
) -> str:
    target_name = language_name(target_lang)
    batch_prompt_lines = []
    for idx, s in enumerate(batch):
        ts = s.get("timestamp")
        if not ts and "start" in s:
            sec = int(s["start"])
            ts = f"{sec//60:02d}:{sec%60:02d}"
        ts_str = f"[{ts}] " if ts else ""
        text = s.get('text', '').strip()
        batch_prompt_lines.append(f"{idx+1} {ts_str}|| {text}")

    # 자동 자막은 문장 조각이므로 앞뒤 대사를 '참고용'으로 제공 (번호 없음 → 파서가 절대 집어가지 않음)
    def _ctx(items: Optional[List[Dict[str, Any]]]) -> str:
        return "\n".join(f"- {(c.get('text') or '').strip()}" for c in (items or []) if (c.get('text') or '').strip())

    before_txt = _ctx(context_before)
    after_txt = _ctx(context_after)
    header = f"[영상 제목]: {video_title.strip()}\n\n" if video_title and video_title.strip() else ""

    return (
        "당신은 영상 자막 실시간 싱크(Timestamp Synchronization) 전문 번역가입니다.\n"
        "각 타임스탬프 번호는 영상에서 해당 초[분:초]에 화면에 출력되는 독립적인 자막 세그먼트입니다.\n"
        f"[번역 목표 언어]: **{target_name}** ({target_lang}) — 모든 번역문은 반드시 {target_name}로 작성하십시오.\n\n"
        + header +
        "[가장 중요한 핵심 규칙: 1:1 행별 엄격 매칭 & 번역 내용 밀림/앞당김 절대 금지]:\n"
        "1. 각 번호(N)의 번역은 **오직 그 번호(N)에 적힌 원문 텍스트 구절만** 번역해야 합니다.\n"
        "2. 원문이 문장 중간에서 끊겨 있더라도, **절대로 다음 번호의 문장을 앞당겨 합치거나, 현재 번호의 내용을 다음 번호로 미루지 마십시오.**\n"
        f"3. 문장이 여러 행에 분할되어 있을 때 처리 예시 (형식 예시이며 영어→한국어로 보여주지만, 실제 출력 언어는 {target_name}입니다):\n"
        "   [입력 예시]\n"
        "   1 [00:00] || That's an interesting angle. I haven't seen that. I wrote a brand new sci-fi story with\n"
        "   2 [00:04] || Project Hail Mary author Andy Weir. Andy is one of the most popular science fiction writers alive.\n"
        "   [올바른 출력 (각 행의 발화 구절에 정확히 1:1 대응)]:\n"
        "   1 || 흥미로운 관점이네요. 본 적 없는데요. 저는 신작 SF 단편을 썼습니다,\n"
        "   2 || '프로젝트 헤일메리'의 저자 앤디 위어와 함께요. 앤디는 현존하는 가장 인기 있는 SF 작가 중 한 명입니다.\n"
        "   [틀린 출력 - 절대 금지 (도미노 싱크 붕괴 원인)]:\n"
        "   1 || 흥미로운 각도네요. 보지 못했던 건데. (뒤의 'I wrote...'를 누락하고 다음 번호로 미루는 행위 금지!)\n"
        "   2 || 저는 완전히 새로운 공상과학 소설을 썼습니다... (앞 번호의 내용을 받아 뒤로 밀려 전체 자막 싱크가 망가짐!)\n\n"
        f"4. 1번부터 {len(batch)}번까지 단 하나의 번호도 건너뛰지 말고 빠짐없이 번역하십시오.\n"
        f"5. 출력 형식: 반드시 각 행마다 '번호 || {target_name} 번역' 형식으로만 출력하십시오. (부연설명 금지)\n"
        "6. [앞 문맥]/[뒤 문맥]은 문장 흐름과 용어를 파악하기 위한 참고 자료일 뿐입니다. 절대 번역하거나 출력에 포함하지 마십시오.\n\n"
        + (f"[앞 문맥 (참고용, 번역 금지)]:\n{before_txt}\n\n" if before_txt else "")
        + "[번역 대상 자막]:\n"
        + "\n".join(batch_prompt_lines)
        + (f"\n\n[뒤 문맥 (참고용, 번역 금지)]:\n{after_txt}" if after_txt else "")
    )

def _parse_translation_response(raw_text: str, batch_len: int) -> Dict[int, str]:
    lines = raw_text.strip().split("\n")
    ko_map = {}
    for l in lines:
        l = l.strip()
        if not l:
            continue
        if "||" in l:
            parts = l.split("||", 1)
            m = re.search(r"\d+", parts[0])
            if m:
                idx = int(m.group()) - 1
                val = parts[1].strip().strip("*").strip()
                if 0 <= idx < batch_len and val:
                    ko_map[idx] = val
            continue
        m = re.match(r"^\[?(\d+)\]?[\.\:\-\|\s\|]+(.*)$", l)
        if m:
            idx = int(m.group(1)) - 1
            val = m.group(2).strip().strip("*").strip()
            if 0 <= idx < batch_len and val:
                ko_map[idx] = val
    return ko_map

class TranslationFatalError(Exception):
    """API 키 오류/권한 거부 등 재시도해도 소용없는 오류 (즉시 중단)."""


def _is_fatal_api_error(msg: str) -> bool:
    m = msg or ""
    return any(kw in m for kw in [
        "API_KEY_INVALID", "API key not valid", "PERMISSION_DENIED",
        "UNAUTHENTICATED", "API key expired"
    ])


CONTEXT_BEFORE = 3  # 배치 앞쪽 참고 대사 수
CONTEXT_AFTER = 2   # 배치 뒤쪽 참고 대사 수


def _translate_batch_with_recovery(
    client: genai.Client,
    batch: List[Dict[str, Any]],
    models_to_try: List[str],
    context_before: Optional[List[Dict[str, Any]]] = None,
    context_after: Optional[List[Dict[str, Any]]] = None,
    video_title: Optional[str] = None,
    target_lang: str = "ko"
) -> Tuple[Dict[int, str], str, Optional[str]]:
    """
    배치 단위(35개 권장) 번역을 수행하고, 일부 라인이 누락되었을 경우
    누락된 라인만 마이크로 배치로 즉각 재요청하여 100% 완전 번역을 보장합니다.
    모델별 부분 결과는 버리지 않고 합쳐서(먼저 성공한 모델 우선) 최선의 결과를 반환합니다.
    반환: (ko_map, used_model_name, last_error) — ko_map 이 일부만 채워졌을 수 있음.
    API 키 오류 등 치명적 오류는 TranslationFatalError 로 즉시 전파합니다.
    """
    last_err = None
    best_map: Dict[int, str] = {}
    used_models: List[str] = []
    for model_name in models_to_try:
        try:
            # 5.0초 간격 보장 (Gemini Free Tier 15 RPM 한도 완벽 보호: 분당 최대 12회)
            _wait_for_rate_limit()

            # 이미 확보한 줄은 다시 요청하지 않음 (이전 모델의 부분 결과 재활용)
            pending = [i for i in range(len(batch)) if i not in best_map]
            if len(pending) == len(batch):
                prompt = _build_translation_prompt(batch, context_before, context_after, video_title, target_lang)
            else:
                prompt = _build_translation_prompt([batch[i] for i in pending], context_before, context_after, video_title, target_lang)
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=8192,
                    http_options=types.HttpOptions(timeout=45000),
                )
            )
            raw_map = _parse_translation_response(resp.text or "", len(pending))
            ko_map = {pending[k]: v for k, v in raw_map.items()}
            if ko_map:
                used_models.append(model_name)
            for k, v in ko_map.items():
                best_map.setdefault(k, v)

            # 누락된 대사 인덱스 확인
            missing_indices = [i for i in range(len(batch)) if i not in best_map]

            # 누락 대사가 일부 발생한 경우, 누락된 항목만 즉각 마이크로 재요청하여 100% 보충
            if missing_indices and len(missing_indices) <= int(len(batch) * 0.6):
                try:
                    # 마이크로 보충 요청 전에도 5.0초 안전 간격 유지
                    _wait_for_rate_limit()
                    missing_items = [batch[i] for i in missing_indices]
                    m_prompt = _build_translation_prompt(missing_items, context_before, context_after, video_title, target_lang)
                    m_resp = client.models.generate_content(
                        model=model_name,
                        contents=m_prompt,
                        config=types.GenerateContentConfig(
                            temperature=0.0,
                            max_output_tokens=4096,
                            http_options=types.HttpOptions(timeout=45000),
                        )
                    )
                    m_map = _parse_translation_response(m_resp.text or "", len(missing_items))
                    for m_i, orig_i in enumerate(missing_indices):
                        if m_i in m_map:
                            best_map.setdefault(orig_i, m_map[m_i])
                except Exception as me:
                    if _is_fatal_api_error(str(me)):
                        raise TranslationFatalError(str(me))

            # 누락 대사가 남아있다면 다음 모델로 재시도하여 100% 번역 추구
            if len(best_map) < len(batch):
                raise ValueError(f"자막 일부 미번역 ({len(best_map)}/{len(batch)}개만 파싱됨, 다음 모델 시도)")

            return best_map, "+".join(dict.fromkeys(used_models)) or model_name, None

        except TranslationFatalError:
            raise
        except Exception as e:
            last_err = str(e)
            if _is_fatal_api_error(last_err):
                raise TranslationFatalError(last_err)
            if "429" in last_err or "RESOURCE_EXHAUSTED" in last_err:
                time.sleep(8.0)
                _mark_rate_limit_now()
            else:
                time.sleep(2.0)
            continue

    return best_map, "+".join(dict.fromkeys(used_models)), last_err


def _batch_context(items: List[Dict[str, Any]], start_i: int, end_i: int):
    return items[max(0, start_i - CONTEXT_BEFORE):start_i], items[end_i:end_i + CONTEXT_AFTER]


def translate_subtitles_gemini(
    subtitles: List[Dict[str, Any]],
    target_lang: str = "ko",
    api_key: Optional[str] = None,
    video_title: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    자막 목록(원문)을 Gemini를 이용해 target_lang(기본 한국어)으로 고속 번역하고,
    각 자막 객체에 'ko_text'(번역문 필드, 이름은 하위 호환용) 필드를 추가하여 반환합니다.
    (번역에 실패한 줄은 ko_text 를 비워 두며, 화면/내보내기에서 원문으로 대체 표시됩니다)
    """
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key or not subtitles:
        return subtitles

    client = genai.Client(api_key=key)
    batch_size = 25  # 자막 싱크 완벽 일치 및 토큰 초과 방지
    translated_subtitles = [dict(s) for s in subtitles]

    models_to_try = [DEFAULT_TRANSLATE_MODEL] + [m for m in FALLBACK_TRANSLATE_MODELS if m != DEFAULT_TRANSLATE_MODEL]

    for start_i in range(0, len(translated_subtitles), batch_size):
        end_i = start_i + batch_size
        batch = translated_subtitles[start_i:end_i]
        ctx_b, ctx_a = _batch_context(translated_subtitles, start_i, end_i)
        try:
            ko_map, _, _ = _translate_batch_with_recovery(client, batch, models_to_try, ctx_b, ctx_a, video_title, target_lang)
        except TranslationFatalError:
            break

        for idx, item in enumerate(batch):
            if idx in ko_map:
                item["ko_text"] = ko_map[idx]

    return translated_subtitles

def translate_subtitles_stream(
    subtitles: List[Dict[str, Any]],
    target_lang: str = "ko",
    api_key: Optional[str] = None,
    is_cancelled_callback: Optional[Any] = None,
    video_title: Optional[str] = None
):
    """
    자막 목록을 Gemini를 이용해 배치 단위로 번역하면서
    실시간 진행률 및 로그 이벤트를 yield하는 제너레이터입니다.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        yield {
            "type": "error",
            "message": "Gemini API 키가 등록되지 않았습니다. 우측 상단 [⚙️ 설정] 메뉴에서 API 키를 입력해주세요."
        }
        return

    if not subtitles:
        yield {
            "type": "error",
            "message": "번역할 자막 데이터가 비어 있습니다."
        }
        return

    try:
        client = genai.Client(api_key=key)
    except Exception as e:
        yield {
            "type": "error",
            "message": f"Gemini 클라이언트 초기화 실패: {str(e)}"
        }
        return

    batch_size = 25  # 자막 싱크 완벽 일치 및 토큰 초과 방지
    translated_subtitles = [dict(s) for s in subtitles]
    total_count = len(translated_subtitles)
    total_batches = (total_count + batch_size - 1) // batch_size

    yield {
        "type": "start",
        "total_count": total_count,
        "total_batches": total_batches,
        "batch_size": batch_size,
        "message": f"총 {total_count}개 대사 {language_name(target_lang)} 번역 작업을 시작합니다. (배치: {batch_size}개, 총 {total_batches}회 / 15 RPM 안전 보호 5.0초 주기 / {DEFAULT_TRANSLATE_MODEL})"
    }

    models_to_try = [DEFAULT_TRANSLATE_MODEL] + [m for m in FALLBACK_TRANSLATE_MODELS if m != DEFAULT_TRANSLATE_MODEL]

    for b_idx, start_i in enumerate(range(0, total_count, batch_size)):
        if is_cancelled_callback and is_cancelled_callback():
            yield {
                "type": "cancelled",
                "message": f"번역 요청이 사용자에 의해 중단되었습니다. (총 {b_idx}/{total_batches} 배치 완료)",
                "subtitles": translated_subtitles
            }
            return

        batch = translated_subtitles[start_i:start_i + batch_size]
        start_num = start_i + 1
        end_num = min(start_i + batch_size, total_count)
        percent = int(((b_idx) / total_batches) * 100)

        yield {
            "type": "progress",
            "batch_index": b_idx + 1,
            "total_batches": total_batches,
            "processed_count": start_i,
            "total_count": total_count,
            "percent": percent,
            "message": f"[{b_idx + 1}/{total_batches}] {start_num}~{end_num}번 대사 번역 요청 중... ({DEFAULT_TRANSLATE_MODEL})"
        }

        ctx_b, ctx_a = _batch_context(translated_subtitles, start_i, start_i + batch_size)
        try:
            ko_map, used_model_name, last_err = _translate_batch_with_recovery(
                client, batch, models_to_try, ctx_b, ctx_a, video_title, target_lang
            )
        except TranslationFatalError as fe:
            yield {
                "type": "error",
                "message": f"Gemini API 키/권한 오류로 번역을 중단합니다. [⚙️ 설정]에서 API 키를 확인해주세요. ({str(fe)[:120]})"
            }
            return

        # 번역 실패 줄은 ko_text 를 비워 둠 → 화면은 원문 + '번역 대기' 표시, 재번역 시 다시 시도됨
        for idx, item in enumerate(batch):
            if idx in ko_map:
                item["ko_text"] = ko_map[idx]

        if not ko_map:
            yield {
                "type": "log",
                "level": "warn",
                "message": f"[{b_idx + 1}/{total_batches}] 번역 재시도 실패: {str(last_err)[:80]}... (원문 유지)"
            }
        else:
            parsed_cnt = len(ko_map)
            level = "info" if parsed_cnt == len(batch) else "warn"
            mark = "✓" if parsed_cnt == len(batch) else "(일부 원문 유지)"
            yield {
                "type": "log",
                "level": level,
                "message": f"[{b_idx + 1}/{total_batches}] {start_num}~{end_num}번 대사 번역 완료 ({parsed_cnt}/{len(batch)}개, {used_model_name}) {mark}"
            }

    yield {
        "type": "complete",
        "total_count": total_count,
        "percent": 100,
        "message": f"🎉 총 {total_count}개 대사의 {language_name(target_lang)} 번역이 모두 완료되었습니다!",
        "subtitles": translated_subtitles
    }

# 2. 단순 텍스트 정리기 (No AI / Rule-based, 0원, 0.1초 완성)
def generate_raw_transcript_note(
    video_info: Dict[str, Any],
    transcript_data: Dict[str, Any]
) -> Dict[str, Any]:
    chunks = transcript_data.get("chunks", [])
    title = video_info.get("title", "YouTube Video")
    channel = video_info.get("channel", "YouTube")
    duration = video_info.get("duration_str", "00:00")
    lang = transcript_data.get("language", "en")
    is_gen = transcript_data.get("is_generated", False)

    md_lines = [
        f"# {title}",
        "",
        f"> 📺 **채널**: {channel} | **재생시간**: {duration} | **자막 언어**: {lang} ({'자동생성' if is_gen else '공식자막'})",
        "",
        "---",
        "",
        "## ⏱️ 타임스탬프 원문 자막 타임라인",
        "",
        "*아래 타임스탬프를 클릭하면 영상의 해당 위치로 즉시 이동합니다.*",
        ""
    ]

    for chunk in chunks:
        ts = chunk.get("timestamp", "00:00")
        text = chunk.get("text", "").strip()
        md_lines.append(f"### [{ts}]")
        md_lines.append(f"{text}\n")

    markdown_content = "\n".join(md_lines)
    return {
        "success": True,
        "markdown": markdown_content,
        "engine": "raw",
        "model_used": "No AI (Rule-Based Transcript Formatter)"
    }

# 3. 구독 AI(ChatGPT/Claude)용 완성형 프롬프트 생성기 (클립보드 복사용)
def generate_clipboard_prompt(
    video_info: Dict[str, Any],
    transcript_data: Dict[str, Any],
    target_lang: str = "ko"
) -> str:
    transcript_text = transcript_data.get("full_text", "")
    source_lang = transcript_data.get("language", "en")
    system_prompt = get_system_prompt_for_lang(target_lang, source_lang)
    user_prompt = build_user_prompt(video_info, transcript_text, source_lang=source_lang, target_lang=target_lang)

    target_name = language_name(target_lang)
    header_role = f"[System Role & Instructions - Language: {target_name}]" if target_lang != "ko" else "[역할 및 지침]"
    header_task = "[Task Request]" if target_lang != "ko" else "[요청 작업]"
    citation_guard = """==================================================
⚠️ [출처 마커 및 수식 표기 절대 금지/표준화 규칙 (Clean Formatting & Formula Rule)]
1. 웹 검색(Web Browsing) 또는 캔버스(Canvas) 연동 시 자동 생성되는 내부 참조 태그(예: :chatgpt-content-reference{...}, :...-reference{...}, 【...†source】, [cite: ...])나 인용 각주 번호를 본문 및 표에 절대 포함하지 마십시오.
2. 모든 내용은 출처 기호나 내부 태그 없이, 문맥 속에 자연스럽게 녹아든 완결된 유려한 표준 마크다운 줄글로만 작성하십시오.
3. [수식 및 공식 표기 규칙]: 복잡한 LaTeX 수식 문법(\\[...\\], _{...}, \\ )을 사용하지 마십시오. 공식이나 핵심 메커니즘을 표현할 때는 누구나 쉽게 읽을 수 있도록 표준 마크다운 백틱 코드 블록(```)이나 인용구(>), 볼드체를 사용하여 직관적인 표준 텍스트로 작성하십시오. (예: `최종 영상 = 움직임(비디오 참조) + 외형(이미지 참조) + 연출(프롬프트)`)
""" if target_lang == "ko" else """==================================================
⚠️ [Strict Clean Formatting & Formula Standardization Rule]
1. DO NOT output any internal citation markers, search reference tags (e.g. :chatgpt-content-reference{...}, :...-reference{...}, 【...†source】, [cite: ...]), or numeric bracket footnotes in the text or tables.
2. All information must be written in clean, fluent markdown prose without raw citation tags.
3. [Formula & Mechanism Rule]: DO NOT use raw LaTeX math syntax (\\[...\\], _{...}, \\ ). When expressing formulas or mechanisms, write them in plain text, standard markdown code blocks (```), or blockquotes (>) so that they are universally readable across any markdown editor without LaTeX rendering engines. (e.g. `Final Shot = Motion(VideoRef) + Appearance(ImageRefs) + Direction(Prompt)`)
"""

    return f"""{header_role}
{system_prompt}

{citation_guard}==================================================
{header_task}
{user_prompt}
"""
