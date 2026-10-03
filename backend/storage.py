import os
import sys
import json
import time
import re
from typing import List, Dict, Any, Optional

if getattr(sys, 'frozen', False):
    DEFAULT_DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "TubeScholar", "data")
else:
    DEFAULT_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

DATA_DIR = os.environ.get("TUBESCHOLAR_DATA_DIR") or DEFAULT_DATA_DIR
NOTES_DIR = os.path.join(DATA_DIR, "notes")
LIBRARY_FILE = os.path.join(DATA_DIR, "library.json")

def ensure_dirs():
    """데이터 및 노트 저장 디렉토리를 확인하고 생성합니다."""
    os.makedirs(NOTES_DIR, exist_ok=True)
    if not os.path.exists(LIBRARY_FILE):
        with open(LIBRARY_FILE, "w", encoding="utf-8") as f:
            json.dump({"notes": {}}, f, ensure_ascii=False, indent=2)

def load_library() -> Dict[str, Any]:
    ensure_dirs()
    try:
        with open(LIBRARY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 하위 호환성 (videos 키가 있을 경우 notes로 마이그레이션)
            if "videos" in data and "notes" not in data:
                data["notes"] = {}
                for vid, vdata in data["videos"].items():
                    nid = f"{vid}_{int(time.time())}"
                    vdata["note_id"] = nid
                    data["notes"][nid] = vdata
            return data
    except Exception:
        return {"notes": {}}

def save_library(data: Dict[str, Any]):
    ensure_dirs()
    with open(LIBRARY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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

def save_note(
    video_info: Dict[str, Any], 
    markdown_content: str, 
    note_id: Optional[str] = None,
    note_title: Optional[str] = None,
    subtitles: Optional[List[Dict[str, Any]]] = None
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
        note_id = f"{video_id}_{timestamp}"

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
    lib["notes"][note_id] = meta
    save_library(lib)

    return {
        "note_id": note_id,
        "file_path": file_path,
        "metadata": meta,
        "markdown": clean_md
    }

def update_note(note_id: str, new_markdown: str) -> Optional[Dict[str, Any]]:
    """사용자가 웹 에디터에서 직접 수정한 마크다운을 저장합니다."""
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

def update_note_subtitles(note_id: str, subtitles: List[Dict[str, Any]]) -> bool:
    """노트에 번역되거나 업데이트된 자막 데이터를 영구 캐싱 저장합니다."""
    lib = load_library()
    notes = lib.get("notes", {})
    if note_id in notes:
        notes[note_id]["subtitles"] = _normalize_subs(subtitles)
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

    if not target_id:
        return None

    meta = notes[target_id]
    file_path = os.path.join(NOTES_DIR, f"{target_id}.md")
    if not os.path.exists(file_path):
        return None

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
    items = list(lib.get("notes", {}).values())
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items

def delete_note(note_id: str) -> bool:
    """학습 노트 및 메타데이터를 삭제합니다."""
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
