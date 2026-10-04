import os
import sys
import json
import time
import re
import shutil
import threading
import functools
from typing import List, Dict, Any, Optional

if getattr(sys, 'frozen', False):
    DEFAULT_DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "TubeScholar", "data")
else:
    DEFAULT_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

DATA_DIR = os.environ.get("TUBESCHOLAR_DATA_DIR") or DEFAULT_DATA_DIR
NOTES_DIR = os.path.join(DATA_DIR, "notes")
LIBRARY_FILE = os.path.join(DATA_DIR, "library.json")
LIBRARY_BACKUP = LIBRARY_FILE + ".bak"

# library.json 읽기-수정-쓰기 전체를 보호하는 프로세스 전역 잠금
# (동시 요청 시 업데이트 유실 및 파일 손상 방지)
_LIB_LOCK = threading.RLock()


class LibraryCorruptedError(RuntimeError):
    """library.json 과 백업이 모두 손상되어 안전하게 읽을 수 없는 경우."""


def _locked(fn):
    """load → 수정 → save 전체를 하나의 잠금 구간으로 묶습니다."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _LIB_LOCK:
            return fn(*args, **kwargs)
    return wrapper


_NOTE_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,120}")


def is_safe_note_id(note_id: Optional[str]) -> bool:
    """파일 경로에 쓰일 note_id 검증 (경로 탈출 '..\\' 등 차단)."""
    return bool(note_id) and bool(_NOTE_ID_RE.fullmatch(note_id))


def _require_safe_note_id(note_id: str):
    if not is_safe_note_id(note_id):
        raise ValueError(f"허용되지 않는 노트 ID 형식입니다: {note_id!r}")


def ensure_dirs():
    """데이터 및 노트 저장 디렉토리를 확인하고 생성합니다."""
    os.makedirs(NOTES_DIR, exist_ok=True)
    if not os.path.exists(LIBRARY_FILE) and not os.path.exists(LIBRARY_BACKUP):
        _atomic_write_json(LIBRARY_FILE, {"notes": {}})


def _retry_io(fn, attempts: int = 6, delay: float = 0.25):
    """백신/인덱서가 잠시 파일을 잠그는 Windows 환경을 위한 재시도."""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except PermissionError as e:
            last = e
            time.sleep(delay * (i + 1))
    raise last


def _atomic_write_json(path: str, data: Dict[str, Any]):
    """임시 파일에 완전히 기록한 뒤 교체하여, 쓰는 도중 중단돼도 원본이 깨지지 않게 합니다."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    _retry_io(lambda: os.replace(tmp, path))


def _read_json(path: str) -> Dict[str, Any]:
    def _do():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    data = _retry_io(_do)
    if not isinstance(data, dict):
        raise ValueError("library root is not an object")
    return data


def load_library() -> Dict[str, Any]:
    with _LIB_LOCK:
        ensure_dirs()
        data = None
        if os.path.exists(LIBRARY_FILE):
            try:
                data = _read_json(LIBRARY_FILE)
            except (ValueError, UnicodeDecodeError):
                # 손상 파일은 지우지 않고 별도 보관 후 백업에서 복구 시도
                corrupt_copy = f"{LIBRARY_FILE}.corrupt-{time.strftime('%Y%m%d_%H%M%S')}"
                try:
                    shutil.copy2(LIBRARY_FILE, corrupt_copy)
                except Exception:
                    pass
                print(f"[storage] library.json 손상 감지 → {corrupt_copy} 보관, 백업에서 복구 시도")

        if data is None and os.path.exists(LIBRARY_BACKUP):
            try:
                data = _read_json(LIBRARY_BACKUP)
                _atomic_write_json(LIBRARY_FILE, data)
                print("[storage] library.json.bak 에서 복구 완료")
            except (ValueError, UnicodeDecodeError):
                data = None

        if data is None:
            # 절대 빈 목록을 반환하지 않음 → 다음 저장이 기존 노트를 덮어쓰는 사고 방지
            raise LibraryCorruptedError(
                "노트 라이브러리 파일(library.json)이 손상되어 읽을 수 없습니다. "
                f"데이터 폴더({DATA_DIR})의 .corrupt / .bak 파일을 확인해주세요."
            )

        data.setdefault("notes", {})
        # 하위 호환성 (videos 키가 있을 경우 notes로 마이그레이션)
        if "videos" in data and not data["notes"]:
            for vid, vdata in data["videos"].items():
                nid = vdata.get("note_id") or vid
                vdata["note_id"] = nid
                data["notes"][nid] = vdata
        return data


def save_library(data: Dict[str, Any]):
    with _LIB_LOCK:
        ensure_dirs()
        # 직전 정상본을 .bak 으로 보존 (원자적 교체 직전)
        if os.path.exists(LIBRARY_FILE):
            try:
                _read_json(LIBRARY_FILE)  # 정상 파일일 때만 백업으로 승격
                _retry_io(lambda: shutil.copy2(LIBRARY_FILE, LIBRARY_BACKUP))
            except Exception:
                pass
        _atomic_write_json(LIBRARY_FILE, data)

def strip_frontmatter(content: str) -> str:
    """마크다운 시작 부분의 YAML Frontmatter(--- ... ---)를 제거하여 순수 마크다운만 반환합니다."""
    return re.sub(r'^---\s*[\r\n]+[\s\S]*?[\r\n]+---\s*[\r\n]*', '', content.strip())

def _normalize_subs(subtitles: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """저장 직전 자막 시간 겹침 제거 (유튜브/로컬 STT 등 모든 경로 공통 적용)."""
    if not subtitles:
        return subtitles or []
    try:
        from extractor import normalize_subtitle_timings
        return normalize_subtitle_timings(subtitles)
    except Exception:
        return subtitles

_LANG_META_KEYS = ("source_lang", "target_lang", "translation_source")


def _clean_lang_meta(lang_meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """노트에 저장할 자막 언어 정보 (허용된 키만, 짧은 문자열/None)."""
    out: Dict[str, Any] = {}
    for k in _LANG_META_KEYS:
        if lang_meta and k in lang_meta:
            v = lang_meta[k]
            out[k] = str(v)[:40] if v else None
    return out


@_locked
def save_note(
    video_info: Dict[str, Any], 
    markdown_content: str, 
    note_id: Optional[str] = None,
    note_title: Optional[str] = None,
    subtitles: Optional[List[Dict[str, Any]]] = None,
    lang_meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    학습 노트를 .md 파일로 저장하고 library.json 메타데이터를 업데이트합니다.
    같은 영상이라도 매번 별도의 note_id를 발급하여 각각 독립적인 노트로 보관합니다.
    """
    ensure_dirs()
    clean_md = strip_frontmatter(markdown_content)
    video_id = video_info.get("video_id", "local_video")
    timestamp = int(time.time())
    
    # 기존 수정이 아니면 매번 고유한 note_id 생성 (같은 영상도 여러 버전 보관 가능)
    if not note_id:
        safe_vid = re.sub(r"[^A-Za-z0-9_-]", "_", str(video_id))[:100] or "note"
        note_id = f"{safe_vid}_{timestamp}"
    _require_safe_note_id(note_id)

    filename = f"{note_id}.md"
    file_path = os.path.join(NOTES_DIR, filename)

    created_time = time.strftime('%Y-%m-%d %H:%M:%S')
    title = note_title or video_info.get('title', '학습 노트')

    # 마크다운 헤더에 프론트매터 보존
    frontmatter = f"""---
note_id: "{note_id}"
title: "{title.replace('"', "'")}"
video_id: "{video_id}"
video_type: "{video_info.get('video_type', 'youtube')}"
channel: "{video_info.get('channel', '').replace('"', "'")}"
url: "{video_info.get('url', '')}"
created_at: "{created_time}"
---

"""
    full_content = frontmatter + clean_md

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(full_content)

    # 메타데이터 인덱싱
    lib = load_library()
    if "notes" not in lib:
        lib["notes"] = {}

    meta = {
        "note_id": note_id,
        "video_id": video_id,
        "video_type": video_info.get("video_type", "youtube"),
        "title": title,
        "channel": video_info.get("channel", "YouTube"),
        "thumbnail": video_info.get("thumbnail", ""),
        "duration": video_info.get("duration", 0),
        "duration_str": video_info.get("duration_str", "00:00"),
        "url": video_info.get("url", f"https://www.youtube.com/watch?v={video_id}"),
        "note_path": file_path,
        "subtitles": _normalize_subs(subtitles),
        "created_at": created_time,
        "updated_at": created_time
    }
    meta.update(_clean_lang_meta(lang_meta))
    lib["notes"][note_id] = meta
    save_library(lib)

    return {
        "note_id": note_id,
        "file_path": file_path,
        "metadata": meta,
        "markdown": clean_md
    }

@_locked
def update_note(note_id: str, new_markdown: str) -> Optional[Dict[str, Any]]:
    """사용자가 웹 에디터에서 직접 수정한 마크다운을 저장합니다."""
    _require_safe_note_id(note_id)
    lib = load_library()
    meta = lib.get("notes", {}).get(note_id)
    if not meta:
        return None

    file_path = os.path.join(NOTES_DIR, f"{note_id}.md")
    clean_md = strip_frontmatter(new_markdown)

    frontmatter = f"""---
note_id: "{note_id}"
title: "{meta.get('title', '').replace('"', "'")}"
video_id: "{meta.get('video_id', '')}"
video_type: "{meta.get('video_type', 'youtube')}"
channel: "{meta.get('channel', '').replace('"', "'")}"
url: "{meta.get('url', '')}"
created_at: "{meta.get('created_at', '')}"
updated_at: "{time.strftime('%Y-%m-%d %H:%M:%S')}"
---

"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(frontmatter + clean_md)

    meta["updated_at"] = time.strftime('%Y-%m-%d %H:%M:%S')
    lib["notes"][note_id] = meta
    save_library(lib)

    return {
        "note_id": note_id,
        "metadata": meta,
        "markdown": clean_md
    }

@_locked
def update_note_subtitles(note_id: str, subtitles: List[Dict[str, Any]], lang_meta: Optional[Dict[str, Any]] = None) -> bool:
    """노트에 번역되거나 업데이트된 자막 데이터를 영구 캐싱 저장합니다. (lang_meta: 원문/번역 언어 정보)"""
    if not is_safe_note_id(note_id):
        return False
    lib = load_library()
    notes = lib.get("notes", {})
    if note_id in notes:
        notes[note_id]["subtitles"] = _normalize_subs(subtitles)
        notes[note_id].update(_clean_lang_meta(lang_meta))
        notes[note_id]["updated_at"] = time.strftime('%Y-%m-%d %H:%M:%S')
        save_library(lib)
        return True
    return False

def get_note(note_id_or_video_id: str) -> Optional[Dict[str, Any]]:
    """저장된 노트를 note_id(우선) 또는 video_id로 조회합니다."""
    lib = load_library()
    notes = lib.get("notes", {})

    target_id = None
    if note_id_or_video_id in notes:
        target_id = note_id_or_video_id
    else:
        # video_id로 최신 노트 검색
        for nid, item in reversed(list(notes.items())):
            if item.get("video_id") == note_id_or_video_id:
                target_id = nid
                break

    if not target_id or not is_safe_note_id(target_id):
        return None

    meta = dict(notes[target_id])
    file_path = os.path.join(NOTES_DIR, f"{target_id}.md")
    if not os.path.exists(file_path):
        return None

    # 과거 생성된 노트 중 자막에 번역(ko_text)이 있으나 메타데이터 언어 설정이 누락된 경우 자동 보정
    subs = meta.get("subtitles") or []
    has_ko = any(bool(s.get("ko_text")) for s in subs if isinstance(s, dict))
    if has_ko:
        updated = False
        if not meta.get("target_lang"):
            meta["target_lang"] = "ko"
            notes[target_id]["target_lang"] = "ko"
            updated = True
        if not meta.get("translation_source"):
            meta["translation_source"] = "gemini"
            notes[target_id]["translation_source"] = "gemini"
            updated = True
        if updated:
            try:
                save_library(lib)
            except Exception:
                pass

    with open(file_path, "r", encoding="utf-8") as f:
        raw_content = f.read()

    # 프론트매터 제거한 순수 마크다운 반환 (화면 렌더링 버그 방지)
    clean_md = strip_frontmatter(raw_content)

    return {
        "note_id": target_id,
        "metadata": meta,
        "markdown": clean_md
    }

def list_saved_notes() -> List[Dict[str, Any]]:
    """저장된 모든 학습 노트 목록을 최신순으로 정렬하여 반환합니다."""
    lib = load_library()
    items = [
        {k: v for k, v in meta.items() if k != "subtitles"}
        for meta in lib.get("notes", {}).values()
    ]
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items

@_locked
def delete_note(note_id: str) -> bool:
    """학습 노트 및 메타데이터를 삭제합니다."""
    if not is_safe_note_id(note_id):
        return False
    lib = load_library()
    if note_id in lib.get("notes", {}):
        del lib["notes"][note_id]
        save_library(lib)

    file_path = os.path.join(NOTES_DIR, f"{note_id}.md")
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass
    return True
