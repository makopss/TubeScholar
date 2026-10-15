"""TubeScholar 백엔드 공통 환경 설정 및 경로 상수 모듈."""
import os
import sys
import warnings
from dotenv import load_dotenv


def suppress_genai_warnings() -> None:
    """Google GenAI SDK의 무해한 AFC(Automatic Function Calling) 권고 경고를 차단합니다."""
    try:
        from google.genai.models import Models
        Models._logged_afc_warning = True
    except Exception:
        pass
    warnings.filterwarnings("ignore", message=".*Automatic function calling.*")
    warnings.filterwarnings("ignore", message=".*Direct use of automatic function calling.*")
    warnings.filterwarnings("ignore", category=UserWarning, module="google.genai.*")


suppress_genai_warnings()

IS_FROZEN = getattr(sys, "frozen", False)

if IS_FROZEN:
    BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    USER_DATA_DIR = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "TubeScholar",
    )
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    ENV_PATH = os.path.join(USER_DATA_DIR, ".env")
    BASE_DIR = BUNDLE_DIR
    DEFAULT_DATA_DIR = os.path.join(USER_DATA_DIR, "data")
else:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    BUNDLE_DIR = BASE_DIR
    USER_DATA_DIR = BASE_DIR
    ENV_PATH = os.path.join(BASE_DIR, ".env")
    DEFAULT_DATA_DIR = os.path.join(BASE_DIR, "data")

load_dotenv(ENV_PATH)

DATA_DIR = os.environ.get("TUBESCHOLAR_DATA_DIR") or DEFAULT_DATA_DIR
NOTES_DIR = os.path.join(DATA_DIR, "notes")
SUBTITLES_DIR = os.path.join(DATA_DIR, "subtitles")
TRANSLATIONS_DIR = os.path.join(DATA_DIR, "translations")
PROMPTS_DIR = os.path.join(DATA_DIR, "prompts")
AUDIO_DIR = os.path.join(DATA_DIR, "audio")

LIBRARY_FILE = os.path.join(DATA_DIR, "library.json")
LIBRARY_BACKUP = LIBRARY_FILE + ".bak"

BUILTIN_PROMPTS_DIR = os.path.join(BUNDLE_DIR, "prompts")
USER_PROMPTS_DIR = PROMPTS_DIR

FRONTEND_DIR = os.path.join(BUNDLE_DIR, "frontend")
if not os.path.exists(FRONTEND_DIR) and IS_FROZEN:
    FRONTEND_DIR = os.path.join(os.path.dirname(sys.executable), "frontend")

# 로컬 영상 업로드 최대 허용 용량 (기본 2048MB = 2GB)
MAX_LOCAL_VIDEO_MB = int(os.environ.get("TUBESCHOLAR_MAX_VIDEO_MB", "2048"))
MAX_LOCAL_VIDEO_BYTES = MAX_LOCAL_VIDEO_MB * 1024 * 1024
# Includes upload, extraction, transcription, generation and saving.
ANALYSIS_TIMEOUT_SECONDS = max(1.0, float(os.environ.get("TUBESCHOLAR_ANALYSIS_TIMEOUT_SECONDS", "600")))
