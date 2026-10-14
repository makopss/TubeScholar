import os
import json
import glob
import time
import re
import shutil
import threading
import functools
from typing import List, Dict, Any, Optional

from config import (
    DATA_DIR,
    NOTES_DIR,
    SUBTITLES_DIR,
    TRANSLATIONS_DIR,
    PROMPTS_DIR,
    AUDIO_DIR,
    LIBRARY_FILE,
    LIBRARY_BACKUP,
)

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
    os.makedirs(SUBTITLES_DIR, exist_ok=True)
    os.makedirs(TRANSLATIONS_DIR, exist_ok=True)
    os.makedirs(PROMPTS_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR, exist_ok=True)
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


def _subtitle_bundle_path(note_id: str) -> str:
    _require_safe_note_id(note_id)
    return os.path.join(SUBTITLES_DIR, f"{note_id}.json")


def _load_note_subtitles_bundle(note_id: str) -> Dict[str, Any]:
    """노트별 분리 저장된 자막/번역 번들(data/subtitles/{note_id}.json)을 읽습니다."""
    if not is_safe_note_id(note_id):
        return {"subtitles": [], "translations": {}}
    path = _subtitle_bundle_path(note_id)
    if not os.path.exists(path):
        return {"subtitles": [], "translations": {}}
    try:
        raw = _read_json(path)
        subs = raw.get("subtitles") if isinstance(raw.get("subtitles"), list) else []
        trans = raw.get("translations") if isinstance(raw.get("translations"), dict) else {}
        return {"subtitles": subs, "translations": trans}
    except Exception as e:
        print(f"[storage] 자막 번들 로드 실패 ({note_id}): {e}")
        return {"subtitles": [], "translations": {}}


def _save_note_subtitles_bundle(
    note_id: str,
    subtitles: Optional[List[Dict[str, Any]]],
    translations: Optional[Dict[str, Any]] = None,
):
    """노트별 자막과 다국어 번역 맵을 data/subtitles/{note_id}.json에 원자적으로 저장합니다."""
    if not is_safe_note_id(note_id):
        return
    ensure_dirs()
    payload = {
        "note_id": note_id,
        "subtitles": subtitles if isinstance(subtitles, list) else [],
        "translations": translations if isinstance(translations, dict) else {},
        "updated_at": time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    _atomic_write_json(_subtitle_bundle_path(note_id), payload)


def _migrate_inline_subtitles(data: Dict[str, Any]) -> bool:
    """library.json 내부에 인라인으로 저장된 대용량 subtitles/translations를 외부 파일로 분리합니다."""
    notes = data.get("notes")
    if not isinstance(notes, dict):
        return False
    migrated = False
    for nid, meta in list(notes.items()):
        if not isinstance(meta, dict):
            continue
        has_inline_subs = "subtitles" in meta
        has_inline_trans = "translations" in meta
        if not has_inline_subs and not has_inline_trans:
            continue

        inline_subs = meta.pop("subtitles", None)
        inline_trans = meta.pop("translations", None)
        migrated = True

        if not is_safe_note_id(nid):
            continue

        existing = _load_note_subtitles_bundle(nid)
        final_subs = inline_subs if isinstance(inline_subs, list) and inline_subs else existing["subtitles"]
        final_trans = dict(existing["translations"])
        if isinstance(inline_trans, dict):
            for lang_code, t_entry in inline_trans.items():
                if isinstance(t_entry, dict) and t_entry.get("subtitles"):
                    final_trans[lang_code] = t_entry
                    vid = meta.get("video_id")
                    if vid:
                        save_translation_cache(
                            vid,
                            lang_code,
                            t_entry["subtitles"],
                            t_entry.get("translation_source") or "gemini",
                        )

        if final_subs or final_trans:
            _save_note_subtitles_bundle(nid, final_subs, final_trans)

    return migrated


_lib_cache: Optional[Dict[str, Any]] = None
_lib_mtime: float = -1.0


def load_library() -> Dict[str, Any]:
    global _lib_cache, _lib_mtime
    with _LIB_LOCK:
        ensure_dirs()
        if _lib_cache is not None and os.path.exists(LIBRARY_FILE):
            try:
                cur_mtime = os.path.getmtime(LIBRARY_FILE)
                if cur_mtime == _lib_mtime:
                    return _lib_cache
            except Exception:
                pass

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
            del data["videos"]

        # 인라인 자막/번역 데이터가 있으면 자동으로 외부 파일(data/subtitles/)로 분리 마이그레이션
        if _migrate_inline_subtitles(data):
            save_library(data)
        else:
            _lib_cache = data
            try:
                _lib_mtime = os.path.getmtime(LIBRARY_FILE)
            except Exception:
                _lib_mtime = -1.0

        return data


def save_library(data: Dict[str, Any]):
    global _lib_cache, _lib_mtime
    with _LIB_LOCK:
        ensure_dirs()
        # 직전 정상본을 .bak 으로 보존 (원자적 교체 직전)
        if os.path.exists(LIBRARY_FILE):
            try:
                if _lib_cache is None:
                    _read_json(LIBRARY_FILE)  # 캐시가 없을 때만 파일 무결성 확인
                _retry_io(lambda: shutil.copy2(LIBRARY_FILE, LIBRARY_BACKUP))
            except Exception:
                pass
        _atomic_write_json(LIBRARY_FILE, data)
        _lib_cache = data
        try:
            _lib_mtime = os.path.getmtime(LIBRARY_FILE)
        except Exception:
            _lib_mtime = -1.0

def clean_ai_citation_artifacts(text: str) -> str:
    """ChatGPT, Claude 등의 웹 복사 시 유입되는 :chatgpt-content-reference{...}, 【...†source】 및 깨진 LaTeX 수식 블록 자동 정화"""
    if not text:
        return ""
    # 1. ChatGPT content reference: :chatgpt-content-reference{index="0"}
    text = re.sub(r':?[a-zA-Z0-9_-]*chatgpt-[a-zA-Z0-9_-]+\{[^}]*\}', '', text)
    text = re.sub(r':[a-zA-Z0-9_-]+-reference\{[^}]*\}', '', text)
    # 2. ChatGPT 웹 검색 인용 표기: 【4:0†source】, 【0†source】, 【turn0search0】
    text = re.sub(r'【[^】]*?(?:source|turn\d+|search|출처)[^】]*?】', '', text)
    # 3. 인용 태그: [cite: 1], [citation: 1] 등
    text = re.sub(r'\[cite(?:ation)?:\s*[^\]]+\]', '', text, flags=re.IGNORECASE)

    # 4. LaTeX 수식 블록 정리 (\[ ... \] 또는 $$ ... $$) -> 깔끔한 마크다운 인용 공식 블록으로 변환
    def _repl_math_block(m):
        content = (m.group(1) or m.group(2) or '').strip()
        if not content:
            return ''
        content = re.sub(r'\\([ \t])', ' ', content)
        content = re.sub(r'\\text\{([^}]+)\}', r'\1', content)
        content = re.sub(r'_\{([^}]+)\}', r'(\1)', content)
        content = content.replace(r'\times', '×').replace(r'\cdot', '·').replace(r'\to', '➔')
        content = re.sub(r'\s*\n\s*', ' ', content)
        content = re.sub(r'\s*([=+*×·➔])\s*', r' \1 ', content)
        content = re.sub(r'\s+', ' ', content).strip()
        return f'> 📐 **공식**: `{content}`'

    text = re.sub(r'\\\[\s*([\s\S]*?)\s*\\\]|\$\$\s*([\s\S]*?)\s*\$\$', _repl_math_block, text)

    # 5. 일반 텍스트 내 잔여 LaTeX 기호 정제 (\공백, _{아래첨자}, \text{...})
    text = re.sub(r'([a-zA-Z0-9가-힣])\\ ([a-zA-Z0-9가-힣])', r'\1 \2', text)
    text = re.sub(r'([a-zA-Z0-9가-힣]+)_\{([^}]+)\}', r'\1(\2)', text)
    text = re.sub(r'\\text\{([^}]+)\}', r'\1', text)

    # 6. 문장부호 앞 공백 및 줄 끝 공백 정리
    text = re.sub(r'[ \t]+([.,!?])', r'\1', text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)
    return text.strip()

def strip_frontmatter(content: str) -> str:
    """마크다운 시작 부분의 YAML Frontmatter(--- ... ---)를 제거하고 AI 인용 찌꺼기를 정화합니다."""
    text = re.sub(r'^---\s*[\r\n]+[\s\S]*?[\r\n]+---\s*[\r\n]*', '', (content or '').strip())
    return clean_ai_citation_artifacts(text)

def _normalize_subs(subtitles: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """저장 직전 자막 시간 겹침 제거 (유튜브/로컬 STT 등 모든 경로 공통 적용)."""
    if not subtitles:
        return subtitles or []
    try:
        from extractor import normalize_subtitle_timings
        return normalize_subtitle_timings(subtitles)
    except Exception:
        return subtitles

_LANG_META_KEYS = ("source_lang", "target_lang", "translation_source", "note_target_lang")


def _clean_lang_meta(lang_meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """노트에 저장할 자막 언어 정보 (허용된 키만, 짧은 문자열/None)."""
    out: Dict[str, Any] = {}
    for k in _LANG_META_KEYS:
        if lang_meta and k in lang_meta:
            v = lang_meta[k]
            out[k] = str(v)[:40] if v else None
    return out


def _safe_file_key(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(key))[:100] or "unknown"


def save_translation_cache(video_id: str, target_lang: str, subtitles: List[Dict[str, Any]], source: str = "gemini") -> bool:
    """비디오 ID 및 번역 언어 기준으로 번역 자막을 영구 캐시합니다."""
    if not video_id or not target_lang or not subtitles:
        return False
    try:
        ensure_dirs()
        vid_key = _safe_file_key(video_id)
        lang_key = _safe_file_key(target_lang).lower()
        cache_file = os.path.join(TRANSLATIONS_DIR, f"{vid_key}_{lang_key}.json")
        payload = {
            "video_id": video_id,
            "target_lang": target_lang.lower(),
            "translation_source": source,
            "subtitles": _normalize_subs(subtitles),
            "updated_at": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        _atomic_write_json(cache_file, payload)
        return True
    except Exception as e:
        print(f"[storage] 번역 캐시 저장 실패 ({video_id}, {target_lang}): {e}")
        return False


def get_translation_cache(video_id: str, target_lang: str) -> Optional[Dict[str, Any]]:
    """캐시된 번역 자막을 조회합니다."""
    if not video_id or not target_lang:
        return None
    try:
        vid_key = _safe_file_key(video_id)
        lang_key = _safe_file_key(target_lang).lower()
        cache_file = os.path.join(TRANSLATIONS_DIR, f"{vid_key}_{lang_key}.json")
        if os.path.exists(cache_file):
            data = _read_json(cache_file)
            subs = data.get("subtitles") or []
            if subs and any(bool(s.get("ko_text") and str(s.get("ko_text")).strip()) for s in subs):
                return data
    except Exception:
        pass
    return None


_HANGUL_RE = re.compile(r"[가-힣]")


def _is_predominantly_korean_text(subtitles: List[Dict[str, Any]]) -> bool:
    """자막 배열의 text 필드가 이미 한국어(한글)로 작성되어 있는지 판별합니다."""
    if not subtitles:
        return False
    sample = [s for s in subtitles[:40] if isinstance(s, dict) and str(s.get("text") or "").strip()]
    if not sample:
        return False
    ko_lines = sum(1 for s in sample if _HANGUL_RE.search(str(s.get("text") or "")))
    return (ko_lines / len(sample)) >= 0.4


def get_cached_subtitles(note_id: Optional[str], video_id: Optional[str], target_lang: str) -> Optional[Dict[str, Any]]:
    """노트 또는 비디오 ID를 기반으로 target_lang에 해당하는 번역된 자막 데이터를 찾습니다."""
    target_lang = (target_lang or "ko").lower()

    # 1. note_id 기준 검색
    if note_id and is_safe_note_id(note_id):
        lib = load_library()
        note = lib.get("notes", {}).get(note_id)
        if note:
            bundle = _load_note_subtitles_bundle(note_id)
            trans_map = bundle.get("translations") or {}
            if target_lang in trans_map and isinstance(trans_map[target_lang], dict):
                entry = trans_map[target_lang]
                subs = entry.get("subtitles") or []
                if any(bool(s.get("ko_text") and str(s.get("ko_text")).strip()) for s in subs):
                    return {
                        "subtitles": subs,
                        "translation_source": entry.get("translation_source", "gemini"),
                        "target_lang": target_lang,
                        "source_lang": note.get("source_lang"),
                    }
            cur_subs = bundle.get("subtitles") or []
            if (note.get("target_lang") or "ko").lower() == target_lang:
                if any(bool(s.get("ko_text") and str(s.get("ko_text")).strip()) for s in cur_subs):
                    return {
                        "subtitles": cur_subs,
                        "translation_source": note.get("translation_source", "gemini"),
                        "target_lang": target_lang,
                        "source_lang": note.get("source_lang"),
                    }
            if not video_id:
                video_id = note.get("video_id")

    # 2. 비디오 ID 기준 글로벌 캐시 우선 검색 (O(1))
    if video_id:
        cached = get_translation_cache(video_id, target_lang)
        if cached:
            subs = cached.get("subtitles") or []
            if any(bool(s.get("ko_text") and str(s.get("ko_text")).strip()) for s in subs):
                return {
                    "subtitles": subs,
                    "translation_source": cached.get("translation_source", "gemini"),
                    "target_lang": target_lang,
                }

    # 3. 비디오 ID 기준 저장된 모든 노트 역순 검색 (글로벌 캐시 미적중 시 백업 경로)
    if video_id:
        lib = load_library()
        for nid, item in reversed(list(lib.get("notes", {}).items())):
            if item.get("video_id") == video_id and is_safe_note_id(nid):
                bundle = _load_note_subtitles_bundle(nid)
                trans_map = bundle.get("translations") or {}
                if target_lang in trans_map and isinstance(trans_map[target_lang], dict):
                    subs = trans_map[target_lang].get("subtitles") or []
                    if any(bool(s.get("ko_text") and str(s.get("ko_text")).strip()) for s in subs):
                        return {
                            "subtitles": subs,
                            "translation_source": trans_map[target_lang].get("translation_source", "gemini"),
                            "target_lang": target_lang,
                            "source_lang": item.get("source_lang"),
                        }
                if (item.get("target_lang") or "ko").lower() == target_lang:
                    subs = bundle.get("subtitles") or []
                    if any(bool(s.get("ko_text") and str(s.get("ko_text")).strip()) for s in subs):
                        return {
                            "subtitles": subs,
                            "translation_source": item.get("translation_source", "gemini"),
                            "target_lang": target_lang,
                            "source_lang": item.get("source_lang"),
                        }

    return None


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
    자막/번역 배열은 data/subtitles/{note_id}.json으로 분리 저장하여 library.json 비대화를 방지합니다.
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

    existing_meta = dict(lib["notes"].get(note_id) or {})
    existing_bundle = _load_note_subtitles_bundle(note_id)
    existing_trans = dict(existing_bundle.get("translations", {}))
    norm_subs = _normalize_subs(subtitles) or _normalize_subs(existing_bundle.get("subtitles", []))

    meta = {
        "note_id": note_id,
        "video_id": video_id or existing_meta.get("video_id", "unknown"),
        "video_type": video_info.get("video_type") or existing_meta.get("video_type", "youtube"),
        "title": title or existing_meta.get("title", "제목 없음"),
        "channel": video_info.get("channel") or existing_meta.get("channel", "YouTube"),
        "thumbnail": video_info.get("thumbnail") or existing_meta.get("thumbnail", ""),
        "duration": video_info.get("duration") or existing_meta.get("duration", 0),
        "duration_str": video_info.get("duration_str") or existing_meta.get("duration_str", "00:00"),
        "url": video_info.get("url") or existing_meta.get("url", f"https://www.youtube.com/watch?v={video_id}"),
        "note_path": file_path,
        "created_at": existing_meta.get("created_at") or created_time,
        "updated_at": created_time,
    }
    for k in ("source_lang", "original_lang", "target_lang", "note_target_lang", "translation_source", "translation_track", "audiobook", "subtitle_audiobook"):
        if existing_meta.get(k) is not None:
            meta[k] = existing_meta[k]
    meta.update(_clean_lang_meta(lang_meta))
    
    # 번역된 자막이 포함되어 있으면 translations 및 비디오 글로벌 캐시에도 보관
    t_lang = (meta.get("target_lang") or "ko").lower()
    has_trans = any(bool(s.get("ko_text") and str(s.get("ko_text")).strip()) for s in norm_subs)
    if not has_trans and video_id:
        cached = get_cached_subtitles(note_id, video_id, t_lang)
        if cached and cached.get("subtitles"):
            norm_subs = cached["subtitles"]
            has_trans = True
            meta["translation_source"] = cached.get("translation_source") or meta.get("translation_source") or "gemini"
            meta["target_lang"] = t_lang
    if not has_trans and t_lang == "ko" and _is_predominantly_korean_text(norm_subs):
        for s in norm_subs:
            if isinstance(s, dict) and not (s.get("ko_text") and str(s.get("ko_text")).strip()):
                s["ko_text"] = s.get("text", "")
        has_trans = True
        meta["translation_source"] = meta.get("translation_source") or "youtube"
        meta["target_lang"] = "ko"

    if has_trans:
        existing_trans[t_lang] = {
            "subtitles": norm_subs,
            "translation_source": meta.get("translation_source") or "gemini",
            "target_lang": t_lang,
        }
        if video_id:
            save_translation_cache(video_id, t_lang, norm_subs, meta.get("translation_source") or "gemini")

    _save_note_subtitles_bundle(note_id, norm_subs, existing_trans)

    # 🎧 노트 저장 시 생성된 오디오북(임시 note_id로 먼저 생성된 오디오 포함)을 노트와 함께 바인딩 및 영구 기록
    note_ab = None
    sub_ab = None
    try:
        import hashlib
        from tts import bind_temp_note_audio, find_saved_note_audiobook, find_saved_subtitle_audiobook
        bind_temp_note_audio(note_id, clean_md)
        content_hash = hashlib.sha1((clean_md or "").encode("utf-8")).hexdigest()[:8]
        # 만약 기존 노트를 덮어썼는데 마크다운 해시가 달라졌다면 이전 내용의 노트 오디오 파일은 정리
        safe_note = re.sub(r'[^A-Za-z0-9_-]', '_', note_id)[:120]
        if os.path.isdir(AUDIO_DIR):
            for fn in os.listdir(AUDIO_DIR):
                if fn.startswith(f"{safe_note}_") and (fn.endswith(".mp3") or fn.endswith(".json")):
                    if not fn.endswith(f"_{content_hash}.mp3") and not fn.endswith(f"_{content_hash}.json"):
                        try:
                            os.remove(os.path.join(AUDIO_DIR, fn))
                        except Exception:
                            pass
        note_ab = find_saved_note_audiobook(note_id, clean_md, meta["title"], meta.get("audiobook"))
        if note_ab:
            meta["audiobook"] = {
                "filename": note_ab["filename"],
                "voice_key": note_ab.get("voice_key", "injoon"),
                "updated_at": created_time,
            }
        else:
            meta.pop("audiobook", None)

        sub_ab = find_saved_subtitle_audiobook(note_id, meta["video_id"], meta["title"], meta.get("subtitle_audiobook"))
        if sub_ab:
            meta["subtitle_audiobook"] = {
                "filename": sub_ab["filename"],
                "voice_key": sub_ab.get("voice_key", "injoon"),
                "mode": sub_ab.get("mode", "dub"),
                "updated_at": created_time,
            }
    except Exception:
        pass

    lib["notes"][note_id] = meta
    save_library(lib)

    full_meta = dict(meta)
    full_meta["subtitles"] = norm_subs
    full_meta["translations"] = existing_trans

    return {
        "note_id": note_id,
        "file_path": file_path,
        "metadata": full_meta,
        "markdown": clean_md,
        "audiobook": note_ab,
        "subtitle_audiobook": sub_ab,
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

    # 🎧 노트 본문 수정 시 새 본문 해시와 일치하지 않는 구버전 노트 오디오북 정리 및 재동기화
    note_ab = None
    sub_ab = None
    try:
        import hashlib
        from tts import bind_temp_note_audio, find_saved_note_audiobook, find_saved_subtitle_audiobook
        bind_temp_note_audio(note_id, clean_md)
        content_hash = hashlib.sha1((clean_md or "").encode("utf-8")).hexdigest()[:8]
        safe_note = re.sub(r'[^A-Za-z0-9_-]', '_', note_id)[:120]
        if os.path.isdir(AUDIO_DIR):
            for fn in os.listdir(AUDIO_DIR):
                if fn.startswith(f"{safe_note}_") and (fn.endswith(".mp3") or fn.endswith(".json")):
                    if not fn.endswith(f"_{content_hash}.mp3") and not fn.endswith(f"_{content_hash}.json"):
                        try:
                            os.remove(os.path.join(AUDIO_DIR, fn))
                        except Exception:
                            pass
        note_ab = find_saved_note_audiobook(note_id, clean_md, meta.get("title", ""), meta.get("audiobook"))
        if note_ab:
            meta["audiobook"] = {
                "filename": note_ab["filename"],
                "voice_key": note_ab.get("voice_key", "injoon"),
                "updated_at": time.strftime('%Y-%m-%d %H:%M:%S'),
            }
        else:
            meta.pop("audiobook", None)
        sub_ab = find_saved_subtitle_audiobook(note_id, meta.get("video_id", ""), meta.get("title", ""), meta.get("subtitle_audiobook"))
    except Exception:
        pass

    meta["updated_at"] = time.strftime('%Y-%m-%d %H:%M:%S')
    lib["notes"][note_id] = meta
    save_library(lib)

    return {
        "note_id": note_id,
        "metadata": meta,
        "markdown": clean_md,
        "audiobook": note_ab,
        "subtitle_audiobook": sub_ab,
    }


@_locked
def update_note_audiobook(
    note_id: Optional[str] = None,
    video_id: Optional[str] = None,
    audiobook_info: Optional[Dict[str, Any]] = None,
    subtitle_audiobook_info: Optional[Dict[str, Any]] = None,
) -> bool:
    """생성된 노트 오디오북 또는 자막 더빙 오디오북 메타데이터를 노트 레코드(library.json)에 저장합니다."""
    lib = load_library()
    notes = lib.get("notes", {})
    if not notes:
        return False

    now_str = time.strftime('%Y-%m-%d %H:%M:%S')
    updated = False

    if note_id and note_id in notes:
        if audiobook_info and audiobook_info.get("filename"):
            notes[note_id]["audiobook"] = {
                "filename": audiobook_info["filename"],
                "voice_key": audiobook_info.get("voice_key", "injoon"),
                "updated_at": now_str,
            }
            updated = True
        if subtitle_audiobook_info and subtitle_audiobook_info.get("filename"):
            notes[note_id]["subtitle_audiobook"] = {
                "filename": subtitle_audiobook_info["filename"],
                "voice_key": subtitle_audiobook_info.get("voice_key", "injoon"),
                "mode": subtitle_audiobook_info.get("mode", "dub"),
                "updated_at": now_str,
            }
            updated = True

    # 같은 video_id를 공유하는 노트에도 자막 더빙 오디오북 정보 연동
    target_vid = video_id or (notes.get(note_id, {}).get("video_id") if note_id else None)
    if target_vid and subtitle_audiobook_info and subtitle_audiobook_info.get("filename"):
        for nid, nmeta in notes.items():
            if nmeta.get("video_id") == target_vid:
                nmeta["subtitle_audiobook"] = {
                    "filename": subtitle_audiobook_info["filename"],
                    "voice_key": subtitle_audiobook_info.get("voice_key", "injoon"),
                    "mode": subtitle_audiobook_info.get("mode", "dub"),
                    "updated_at": now_str,
                }
                updated = True

    if updated:
        save_library(lib)
    return updated

@_locked
def update_note_subtitles(note_id: str, subtitles: List[Dict[str, Any]], lang_meta: Optional[Dict[str, Any]] = None) -> bool:
    """노트에 번역되거나 업데이트된 자막 데이터를 영구 캐싱 저장합니다. (lang_meta: 원문/번역 언어 정보)"""
    if not is_safe_note_id(note_id):
        return False
    lib = load_library()
    notes = lib.get("notes", {})
    if note_id in notes:
        clean_meta = _clean_lang_meta(lang_meta)
        target = (clean_meta.get("target_lang") or notes[note_id].get("target_lang") or "ko").lower()
        normalized = _normalize_subs(subtitles)

        bundle = _load_note_subtitles_bundle(note_id)
        trans_map = dict(bundle.get("translations") or {})

        has_trans = any(bool(s.get("ko_text") and str(s.get("ko_text")).strip()) for s in normalized)
        vid = notes[note_id].get("video_id")
        if has_trans:
            source = clean_meta.get("translation_source") or notes[note_id].get("translation_source") or "gemini"
            trans_map[target] = {
                "subtitles": normalized,
                "translation_source": source,
                "target_lang": target,
            }
            if vid:
                save_translation_cache(vid, target, normalized, source)
        elif clean_meta.get("translation_source") == "manual":
            trans_map.pop(target, None)
            if vid:
                try:
                    cache_file = os.path.join(TRANSLATIONS_DIR, f"{_safe_file_key(vid)}_{_safe_file_key(target).lower()}.json")
                    if os.path.exists(cache_file):
                        os.remove(cache_file)
                except Exception:
                    pass

        if clean_meta.get("translation_source") == "manual":
            for lang_k, entry in list(trans_map.items()):
                if lang_k == target or not isinstance(entry, dict):
                    continue
                other_subs = entry.get("subtitles") or []
                if len(other_subs) == len(normalized):
                    synced_other = []
                    for orig_row, other_row in zip(normalized, other_subs):
                        merged_row = dict(orig_row)
                        if isinstance(other_row, dict) and "ko_text" in other_row:
                            merged_row["ko_text"] = other_row["ko_text"]
                        else:
                            merged_row.pop("ko_text", None)
                        synced_other.append(merged_row)
                    entry["subtitles"] = synced_other

        _save_note_subtitles_bundle(note_id, normalized, trans_map)

        # 자막 직접 수정(manual) 또는 재번역 시 구버전 자막 더빙 오디오 파일 정리 및 메타데이터 재동기화
        if clean_meta.get("translation_source") in ("manual", "gemini"):
            try:
                from tts import cleanup_stale_subtitle_audiobooks, find_saved_subtitle_audiobook
                vid_for_sub = notes[note_id].get("video_id", "")
                extra_sets = [
                    e.get("subtitles", [])
                    for e in trans_map.values()
                    if isinstance(e, dict) and e.get("subtitles")
                ]
                cleanup_stale_subtitle_audiobooks(note_id, vid_for_sub, normalized, extra_subtitles_sets=extra_sets)
                sub_ab = find_saved_subtitle_audiobook(
                    note_id, vid_for_sub, notes[note_id].get("title", ""), notes[note_id].get("subtitle_audiobook")
                )
                now_ts = time.strftime('%Y-%m-%d %H:%M:%S')
                if sub_ab:
                    notes[note_id]["subtitle_audiobook"] = {
                        "filename": sub_ab["filename"],
                        "voice_key": sub_ab.get("voice_key", "injoon"),
                        "mode": sub_ab.get("mode", "dub"),
                        "updated_at": now_ts,
                    }
                else:
                    notes[note_id].pop("subtitle_audiobook", None)
                # 동일 video_id 공유 노트의 subtitle_audiobook 파일이 삭제된 경우 함께 동기화
                if vid_for_sub:
                    for nid, nmeta in notes.items():
                        if nid == note_id or nmeta.get("video_id") != vid_for_sub:
                            continue
                        cur_sub_ab = nmeta.get("subtitle_audiobook")
                        if isinstance(cur_sub_ab, dict) and cur_sub_ab.get("filename"):
                            ab_path = os.path.join(AUDIO_DIR, os.path.basename(str(cur_sub_ab["filename"])))
                            if not os.path.isfile(ab_path):
                                if sub_ab:
                                    nmeta["subtitle_audiobook"] = dict(notes[note_id]["subtitle_audiobook"])
                                else:
                                    nmeta.pop("subtitle_audiobook", None)
            except Exception:
                pass

        notes[note_id].update(clean_meta)
        notes[note_id]["updated_at"] = time.strftime('%Y-%m-%d %H:%M:%S')
        save_library(lib)
        return True
    return False

@_locked
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

    bundle = _load_note_subtitles_bundle(target_id)
    subs = bundle.get("subtitles") or []
    trans_map = dict(bundle.get("translations") or {})

    has_ko = any(bool(s.get("ko_text") and str(s.get("ko_text")).strip()) for s in subs if isinstance(s, dict))
    lib_updated = False
    bundle_updated = False

    t_lang = (meta.get("target_lang") or "ko").lower()
    vid = meta.get("video_id")

    # 1. 현재 번들의 subtitles에 ko_text가 없으나 translations 맵에 해당 언어 번역이 있는 경우 복원
    if not has_ko and t_lang in trans_map and isinstance(trans_map[t_lang], dict):
        t_subs = trans_map[t_lang].get("subtitles") or []
        if any(bool(s.get("ko_text") and str(s.get("ko_text")).strip()) for s in t_subs if isinstance(s, dict)):
            subs = t_subs
            has_ko = True
            bundle_updated = True

    # 2. 같은 video_id의 글로벌 번역 캐시 또는 형제 노트에 번역이 있는 경우 자동 복원
    if not has_ko and vid:
        cached = get_cached_subtitles(target_id, vid, t_lang)
        if cached and cached.get("subtitles"):
            subs = cached["subtitles"]
            source = cached.get("translation_source") or meta.get("translation_source") or "gemini"
            trans_map[t_lang] = {
                "subtitles": subs,
                "translation_source": source,
                "target_lang": t_lang,
            }
            meta["translation_source"] = source
            notes[target_id]["translation_source"] = source
            has_ko = True
            bundle_updated = True
            lib_updated = True

    # 3. 구버전 노트 등 text 필드 자체가 이미 한국어(한글)인데 ko_text가 비어있는 경우 자동 채움
    if not has_ko and t_lang == "ko" and _is_predominantly_korean_text(subs):
        for s in subs:
            if isinstance(s, dict) and not (s.get("ko_text") and str(s.get("ko_text")).strip()):
                s["ko_text"] = s.get("text", "")
        source = meta.get("translation_source") or "youtube"
        trans_map["ko"] = {
            "subtitles": subs,
            "translation_source": source,
            "target_lang": "ko",
        }
        meta["translation_source"] = source
        notes[target_id]["translation_source"] = source
        has_ko = True
        bundle_updated = True
        lib_updated = True

    if has_ko and t_lang not in trans_map:
        source = meta.get("translation_source") or "gemini"
        trans_map[t_lang] = {
            "subtitles": subs,
            "translation_source": source,
            "target_lang": t_lang,
        }
        if vid:
            save_translation_cache(vid, t_lang, subs, source)
        bundle_updated = True

    if has_ko:
        if not meta.get("target_lang"):
            meta["target_lang"] = "ko"
            notes[target_id]["target_lang"] = "ko"
            lib_updated = True
        if not meta.get("translation_source"):
            meta["translation_source"] = "gemini"
            notes[target_id]["translation_source"] = "gemini"
            lib_updated = True

    if bundle_updated:
        try:
            _save_note_subtitles_bundle(target_id, subs, trans_map)
        except Exception:
            pass

    with open(file_path, "r", encoding="utf-8") as f:
        raw_content = f.read()

    # 프론트매터 제거한 순수 마크다운 반환 (화면 렌더링 버그 방지)
    clean_md = strip_frontmatter(raw_content)

    # 🎧 저장된 노트 오디오북 및 자막 더빙 오디오북 탐색·동기화
    note_ab = None
    sub_ab = None
    try:
        from tts import find_saved_note_audiobook, find_saved_subtitle_audiobook
        note_ab = find_saved_note_audiobook(target_id, clean_md, meta.get("title", ""), meta.get("audiobook"))
        if note_ab:
            ab_summary = {
                "filename": note_ab["filename"],
                "voice_key": note_ab.get("voice_key", "injoon"),
                "updated_at": meta.get("audiobook", {}).get("updated_at") or meta.get("updated_at", ""),
            }
            if notes[target_id].get("audiobook") != ab_summary:
                notes[target_id]["audiobook"] = ab_summary
                meta["audiobook"] = ab_summary
                lib_updated = True
        elif "audiobook" in notes[target_id]:
            notes[target_id].pop("audiobook", None)
            meta.pop("audiobook", None)
            lib_updated = True

        sub_ab = find_saved_subtitle_audiobook(target_id, vid or "", meta.get("title", ""), meta.get("subtitle_audiobook"))
        if sub_ab:
            sub_ab_summary = {
                "filename": sub_ab["filename"],
                "voice_key": sub_ab.get("voice_key", "injoon"),
                "mode": sub_ab.get("mode", "dub"),
                "updated_at": meta.get("subtitle_audiobook", {}).get("updated_at") or meta.get("updated_at", ""),
            }
            if notes[target_id].get("subtitle_audiobook") != sub_ab_summary:
                notes[target_id]["subtitle_audiobook"] = sub_ab_summary
                meta["subtitle_audiobook"] = sub_ab_summary
                lib_updated = True
        elif "subtitle_audiobook" in notes[target_id]:
            notes[target_id].pop("subtitle_audiobook", None)
            meta.pop("subtitle_audiobook", None)
            lib_updated = True
    except Exception:
        pass

    if lib_updated:
        try:
            save_library(lib)
        except Exception:
            pass

    meta["subtitles"] = subs
    meta["translations"] = trans_map

    return {
        "note_id": target_id,
        "metadata": meta,
        "markdown": clean_md,
        "audiobook": note_ab,
        "subtitle_audiobook": sub_ab,
    }

def list_saved_notes() -> List[Dict[str, Any]]:
    """저장된 모든 학습 노트 목록을 최신순으로 정렬하여 반환합니다. (대용량 자막/번역 배열 제외)"""
    lib = load_library()
    try:
        from tts import has_saved_audiobook_on_disk
    except Exception:
        has_saved_audiobook_on_disk = None

    items = []
    for meta in lib.get("notes", {}).values():
        entry = {k: v for k, v in meta.items() if k not in ("subtitles", "translations")}
        nid = entry.get("note_id", "")
        vid = entry.get("video_id", "")
        has_ab = bool(entry.get("audiobook") or entry.get("subtitle_audiobook"))
        if not has_ab and has_saved_audiobook_on_disk:
            has_ab = has_saved_audiobook_on_disk(nid, vid)
        entry["has_audiobook"] = has_ab
        items.append(entry)

    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return items

@_locked
def delete_note(note_id: str) -> bool:
    """학습 노트, 자막 번들 및 관련 TTS 오디오 캐시 파일을 삭제합니다."""
    if not is_safe_note_id(note_id):
        return False
    lib = load_library()
    deleted_meta = None
    if note_id in lib.get("notes", {}):
        deleted_meta = lib["notes"].pop(note_id, None)
        save_library(lib)

    # 1. 마크다운 노트 파일 삭제
    file_path = os.path.join(NOTES_DIR, f"{note_id}.md")
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass

    # 2. 분리 저장된 자막/번역 번들 파일 삭제
    sub_path = _subtitle_bundle_path(note_id)
    if os.path.exists(sub_path):
        try:
            os.remove(sub_path)
        except Exception:
            pass

    # 3. 해당 노트에 종속된 TTS 오디오 및 타임라인 캐시 파일 정리
    if os.path.isdir(AUDIO_DIR):
        safe_note = re.sub(r'[^A-Za-z0-9_-]', '_', note_id)[:120]
        patterns = [
            os.path.join(AUDIO_DIR, f"{safe_note}_*.mp3"),
            os.path.join(AUDIO_DIR, f"{safe_note}_*.json"),
            os.path.join(AUDIO_DIR, f"sub_{safe_note}_*.mp3"),
            os.path.join(AUDIO_DIR, f"sub_{safe_note}_*.json"),
        ]
        # 만약 삭제된 노트의 video_id를 공유하는 다른 노트가 보관함에 없다면 해당 video_id 자막 더빙 파일도 함께 정리
        vid = (deleted_meta or {}).get("video_id")
        if vid:
            remaining_same_vid = any(
                isinstance(m, dict) and m.get("video_id") == vid
                for m in lib.get("notes", {}).values()
            )
            if not remaining_same_vid:
                for max_len in (80, 120):
                    safe_vid = re.sub(r'[^A-Za-z0-9_-]', '_', str(vid))[:max_len]
                    if safe_vid:
                        patterns.append(os.path.join(AUDIO_DIR, f"sub_{safe_vid}_*.mp3"))
                        patterns.append(os.path.join(AUDIO_DIR, f"sub_{safe_vid}_*.json"))

        for pattern in patterns:
            for cached_file in glob.glob(pattern):
                try:
                    os.remove(cached_file)
                except Exception:
                    pass

    return True
