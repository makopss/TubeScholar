import os
import sys
import threading
from typing import Dict, Tuple, Optional, Any, List
from languages import language_name

# 1. 기본 내장 템플릿 디렉토리 경로 (PyInstaller 패키징 및 로컬 개발 환경 호환)
if getattr(sys, 'frozen', False):
    BUILTIN_PROMPTS_DIR = os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)), "prompts")
else:
    BUILTIN_PROMPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "prompts"))

# 2. 사용자 데이터 디렉토리 내 커스텀 프롬프트 디렉토리
try:
    from storage import DATA_DIR
    USER_PROMPTS_DIR = os.path.join(DATA_DIR, "prompts")
except Exception:
    if getattr(sys, 'frozen', False):
        USER_PROMPTS_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "TubeScholar", "data", "prompts")
    else:
        USER_PROMPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "prompts"))

# 파일 수정 시간(mtime) 기반 캐시: path -> (mtime, content)
_cache_lock = threading.Lock()
_prompt_cache: Dict[str, Tuple[float, str]] = {}


def ensure_prompts_dirs() -> None:
    """사용자 커스텀 프롬프트 디렉토리가 없으면 생성합니다."""
    try:
        os.makedirs(USER_PROMPTS_DIR, exist_ok=True)
    except Exception:
        pass


def get_user_prompts_dir() -> str:
    """사용자 커스텀 프롬프트 디렉토리 절대 경로를 반환합니다."""
    ensure_prompts_dirs()
    return USER_PROMPTS_DIR


def get_builtin_prompts_dir() -> str:
    """기본 번들 프롬프트 디렉토리 절대 경로를 반환합니다."""
    return BUILTIN_PROMPTS_DIR


def _read_file_cached(file_path: str) -> Optional[str]:
    """
    파일의 최종 수정 시각(mtime)을 감지하여 캐시하고,
    파일이 수정되었을 때만 디스크에서 다시 읽어 즉각 반영합니다.
    """
    if not os.path.isfile(file_path):
        return None

    try:
        current_mtime = os.path.getmtime(file_path)
    except OSError:
        return None

    with _cache_lock:
        if file_path in _prompt_cache:
            cached_mtime, cached_content = _prompt_cache[file_path]
            if current_mtime == cached_mtime:
                return cached_content

    # 캐시 미스 또는 파일 변경 시 파일 읽기
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        with _cache_lock:
            _prompt_cache[file_path] = (current_mtime, content)
        return content
    except Exception as e:
        print(f"[!] 프롬프트 파일 읽기 실패 ({file_path}): {e}")
        return None


def load_prompt_template(filename: str) -> Optional[str]:
    """
    오버레이(Overlay) 우선순위에 따라 프롬프트 템플릿 마크다운을 로드합니다:
    1순위: 사용자 데이터 디렉토리 (USER_PROMPTS_DIR / filename) - 사용자 커스텀 마크다운
    2순위: 기본 내장 디렉토리 (BUILTIN_PROMPTS_DIR / filename) - 배포 기본 마크다운
    """
    # 1. 사용자 커스텀 템플릿 우선 조회
    user_file = os.path.join(USER_PROMPTS_DIR, filename)
    content = _read_file_cached(user_file)
    if content is not None:
        return content

    # 2. 기본 내장 템플릿 조회
    builtin_file = os.path.join(BUILTIN_PROMPTS_DIR, filename)
    content = _read_file_cached(builtin_file)
    if content is not None:
        return content

    return None


def get_system_prompt_for_lang(target_lang: str = "ko", source_lang: str = "en") -> str:
    """
    목표 언어 및 원본 자막 언어에 맞는 시스템 프롬프트(마크다운 템플릿)를 로드하여 반환합니다.
    사용자가 data/prompts/ 내의 마크다운 파일을 수정하면 즉시 수정본이 반영됩니다.
    """
    target = (target_lang or "ko").lower()
    is_ko_source = (source_lang or "").lower().startswith("ko")

    if target == "ko":
        filename = "system_ko_native.md" if is_ko_source else "system_ko.md"
        prompt = load_prompt_template(filename)
        if prompt:
            return prompt
    elif target.startswith("en"):
        prompt = load_prompt_template("system_en.md")
        if prompt:
            return prompt
    elif target.startswith("ja"):
        prompt = load_prompt_template("system_ja.md")
        if prompt:
            return prompt
    else:
        # 기타 다국어: system_default.md 로드 후 플레이스홀더 치환
        prompt = load_prompt_template("system_default.md")
        target_name = language_name(target)
        if prompt:
            return prompt.replace("${TARGET_NAME}", target_name).replace("${TARGET_LANG}", target)

    # 비상시 최후의 폴백 (파일 누락 등)
    target_name = language_name(target)
    return f"""You are a world-class Knowledge Architect and Instructional Designer.
Generate a comprehensive Master Deep Learning Note strictly in {target_name} ({target}).
Include Executive Summary, Key Takeaways, Signature Section, Chronological Deep Dive with [MM:SS], Proper Nouns Glossary, and 3-Stage Quiz.
"""


def list_available_templates() -> List[Dict[str, Any]]:
    """사용 가능한 템플릿 목록과 커스텀 파일 적용 여부를 반환합니다."""
    templates = [
        {"filename": "system_ko.md", "description": "한국어 (해외 영상 번역/심층 분석)", "lang": "ko"},
        {"filename": "system_ko_native.md", "description": "한국어 (국내 영상 구어체 정돈/심화)", "lang": "ko"},
        {"filename": "system_en.md", "description": "영어 마스터 지식 노트", "lang": "en"},
        {"filename": "system_ja.md", "description": "일본어 마스터 지식 노트", "lang": "ja"},
        {"filename": "system_default.md", "description": "기타 다국어 범용 템플릿", "lang": "other"},
    ]
    result = []
    for t in templates:
        fn = t["filename"]
        user_path = os.path.join(USER_PROMPTS_DIR, fn)
        builtin_path = os.path.join(BUILTIN_PROMPTS_DIR, fn)
        is_custom = os.path.isfile(user_path)
        active_path = user_path if is_custom else (builtin_path if os.path.isfile(builtin_path) else "")
        result.append({
            **t,
            "is_custom": is_custom,
            "active_path": active_path,
            "exists": bool(active_path)
        })
    return result
