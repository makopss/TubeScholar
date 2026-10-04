import os
import sys
import multiprocessing
import webbrowser
import threading
import time
import warnings
import uvicorn

# Google GenAI SDK의 무해한 AFC 권고 logger.warning 원천 차단
try:
    from google.genai.models import Models
    Models._logged_afc_warning = True
except Exception:
    pass
warnings.filterwarnings("ignore", message=".*Automatic function calling.*")
warnings.filterwarnings("ignore", message=".*Direct use of automatic function calling.*")
warnings.filterwarnings("ignore", category=UserWarning, module="google.genai.*")

# PyInstaller 윈도우 멀티프로세싱 지원 필수
multiprocessing.freeze_support()

# 윈도우 no-console (GUI) 모드로 실행 시 stdout/stderr가 None이 되어 uvicorn/logging 등에서 충돌하는 현상 방지
if sys.stdout is None or sys.stderr is None:
    try:
        log_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "TubeScholar")
        os.makedirs(log_dir, exist_ok=True)
        log_file = open(os.path.join(log_dir, "tubescholar.log"), "a", encoding="utf-8", buffering=1)
        if sys.stdout is None:
            sys.stdout = log_file
        if sys.stderr is None:
            sys.stderr = log_file
    except Exception:
        try:
            devnull = open(os.devnull, "w", encoding="utf-8")
            if sys.stdout is None:
                sys.stdout = devnull
            if sys.stderr is None:
                sys.stderr = devnull
        except Exception:
            pass
elif sys.platform == "win32":
    try:
        if sys.stdout is not None:
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr is not None:
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import urllib.request

def check_already_running(port=8000):
    """서버가 이미 다른 프로세스에서 구동 중인지 확인"""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/notes", headers={"x-tubescholar": "1"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False

def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:8000")

def heartbeat_watchdog():
    """브라우저가 모두 닫혀 하트비트가 일정 시간 이상 끊기면 백그라운드 프로세스 자동 종료"""
    # 최초 기동 시 브라우저가 열리고 첫 신호를 보낼 때까지 충분한 여유(35초) 제공
    time.sleep(35)
    while True:
        time.sleep(5)
        try:
            import app as app_module
            last_hb = getattr(app_module, "_last_heartbeat", time.time())
            if time.time() - last_hb > 25:
                # 25초 이상 브라우저 탭으로부터 신호가 없으면 사용자 브라우저 종료로 간주하고 안전 종료
                os._exit(0)
        except Exception:
            pass

if __name__ == "__main__":
    # 이미 백그라운드에서 TubeScholar 서버가 실행 중이면 브라우저 창만 새로 띄우고 즉시 종료
    if check_already_running(8000):
        webbrowser.open("http://127.0.0.1:8000")
        sys.exit(0)

    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    backend_dir = os.path.join(base_dir, "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    print("=" * 60)
    print("🚀 TubeScholar - 유튜브 LLM 심층 지식 확장 학습기 실행 중...")
    print("📍 브라우저가 자동으로 열리지 않을 경우 아래 주소로 접속하세요:")
    print("   👉 http://127.0.0.1:8000")
    print("=" * 60)

    # FastAPI app 인스턴스 직접 임포트 (PyInstaller 환경 안정성)
    from app import app

    # 브라우저 자동 실행 쓰레드
    threading.Thread(target=open_browser, daemon=True).start()

    # 브라우저 종료 감지 워치독 쓰레드
    threading.Thread(target=heartbeat_watchdog, daemon=True).start()

    # FastAPI 서버 구동
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=False, log_level="info")
