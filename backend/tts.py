import os
import sys
import re
import json
import asyncio
import hashlib
from typing import List, Dict, Any, Optional
import edge_tts

if getattr(sys, 'frozen', False):
    DEFAULT_DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "TubeScholar", "data")
else:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    DEFAULT_DATA_DIR = os.path.join(BASE_DIR, "data")

DATA_DIR = os.environ.get("TUBESCHOLAR_DATA_DIR") or DEFAULT_DATA_DIR
AUDIO_DIR = os.path.join(DATA_DIR, "audio")
os.makedirs(AUDIO_DIR, exist_ok=True)

VOICES = {
    # 한국어 (Korean)
    'injoon': {
        'name': '인준 (한국어 차분한 남성 다큐 톤)',
        'id': 'ko-KR-InJoonNeural',
        'gender': 'male',
        'lang': 'ko'
    },
    'sunhi': {
        'name': '선희 (한국어 명확한 지적 여성 톤)',
        'id': 'ko-KR-SunHiNeural',
        'gender': 'female',
        'lang': 'ko'
    },
    'hyunsu': {
        'name': '현수 (한국어 다국어 남성 톤)',
        'id': 'ko-KR-HyunsuMultilingualNeural',
        'gender': 'male',
        'lang': 'ko'
    },
    # 영어 (English)
    'christopher': {
        'name': 'Christopher (US Warm & Authoritative Male)',
        'id': 'en-US-ChristopherNeural',
        'gender': 'male',
        'lang': 'en'
    },
    'jenny': {
        'name': 'Jenny (US Natural & Clear Female)',
        'id': 'en-US-JennyNeural',
        'gender': 'female',
        'lang': 'en'
    },
    'guy': {
        'name': 'Guy (US Friendly & Casual Male)',
        'id': 'en-US-GuyNeural',
        'gender': 'male',
        'lang': 'en'
    },
    # 일본어 (Japanese)
    'keita': {
        'name': 'Keita / 啓太 (日本語 落ち着いた男性 語り)',
        'id': 'ja-JP-KeitaNeural',
        'gender': 'male',
        'lang': 'ja'
    },
    'nanami': {
        'name': 'Nanami / 七海 (日本語 知的で明瞭な女性)',
        'id': 'ja-JP-NanamiNeural',
        'gender': 'female',
        'lang': 'ja'
    },
    # 중국어 (Chinese)
    'yunxi': {
        'name': 'Yunxi / 云希 (中文 男声 沉稳生动)',
        'id': 'zh-CN-YunxiNeural',
        'gender': 'male',
        'lang': 'zh'
    },
    'xiaoxiao': {
        'name': 'Xiaoxiao / 晓晓 (中文 女声 清晰自然)',
        'id': 'zh-CN-XiaoxiaoNeural',
        'gender': 'female',
        'lang': 'zh'
    },
    # 스페인어 (Spanish)
    'alvaro': {
        'name': 'Alvaro (Español Voz Masculina)',
        'id': 'es-ES-AlvaroNeural',
        'gender': 'male',
        'lang': 'es'
    },
    'elvira': {
        'name': 'Elvira (Español Voz Femenina)',
        'id': 'es-ES-ElviraNeural',
        'gender': 'female',
        'lang': 'es'
    },
    # 프랑스어 (French)
    'henri': {
        'name': 'Henri (Français Voix Masculine)',
        'id': 'fr-FR-HenriNeural',
        'gender': 'male',
        'lang': 'fr'
    },
    'denise': {
        'name': 'Denise (Français Voix Féminine)',
        'id': 'fr-FR-DeniseNeural',
        'gender': 'female',
        'lang': 'fr'
    },
    # 독일어 (German)
    'conrad': {
        'name': 'Conrad (Deutsch Männliche Stimme)',
        'id': 'de-DE-ConradNeural',
        'gender': 'male',
        'lang': 'de'
    },
    'katja': {
        'name': 'Katja (Deutsch Weibliche Stimme)',
        'id': 'de-DE-KatjaNeural',
        'gender': 'female',
        'lang': 'de'
    }
}
DEFAULT_VOICE = 'injoon'

def clean_markdown_for_tts(markdown_text: str, max_chars: int = 15000) -> str:
    if not markdown_text:
        return ''

    text = markdown_text
    # 1. YAML 프론트매터 제거
    text = re.sub(r'^---\s*[\r\n]+[\s\S]*?[\r\n]+---\s*[\r\n]*', '', text.strip())

    # 1-1. AI 인용/참조 찌꺼기 태그 제거 (:chatgpt-content-reference{...}, 【...†source】 등)
    text = re.sub(r':?[a-zA-Z0-9_-]*chatgpt-[a-zA-Z0-9_-]+\{[^}]*\}', '', text)
    text = re.sub(r':[a-zA-Z0-9_-]+-reference\{[^}]*\}', '', text)
    text = re.sub(r'【[^】]*?(?:source|turn\d+|search|출처)[^】]*?】', '', text)
    text = re.sub(r'\[cite(?:ation)?:\s*[^\]]+\]', '', text, flags=re.IGNORECASE)

    # 2. 코드 블록 및 인라인 코드 제거/변환
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # 3. 마크다운 링크: [텍스트](url) -> 텍스트
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'!\[[^\]]*\]\([^\)]+\)', '', text)

    # 4. 타임스탬프 제거 ([01:23], (01:23), 01:23~04:56, 01:23 - 04:56 등 낭독 불필요)
    text = re.sub(r'\[?\b\d{1,2}:\d{2}(?::\d{2})?\b\s*[-~]\s*\b\d{1,2}:\d{2}(?::\d{2})?\b\]?', '', text)
    text = re.sub(r'\[\s*\d{1,2}:\d{2}(?::\d{2})?\s*\]', '', text)
    text = re.sub(r'\(\s*\d{1,2}:\d{2}(?::\d{2})?\s*\)', '', text)
    text = re.sub(r'^\s*#{1,6}\s*\d{1,2}:\d{2}(?::\d{2})?\s*', '', text, flags=re.MULTILINE)

    # 5. 괄호 (...) 및 （...） 안의 보조 영문, 출처, 주석 단어 완전 제거 (듣기에 매끄러운 낭독 흐름)
    text = re.sub(r'\([^)]*\)', '', text)
    text = re.sub(r'（[^）]*）', '', text)

    # 6. 각주 및 대괄호 기호 정리
    text = re.sub(r'\[\d+\]', '', text) # [1], [2] 각주 번호 제거
    text = re.sub(r'\[!(?:NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[([^\]]+)\]', r'\1', text) # [단어] -> 단어

    # 7. 마크다운 표 및 제목/강조 문법 정리
    text = re.sub(r'\|[\s\-:]+\|\n', '\n', text)
    text = re.sub(r'\|\s*', ' ', text)
    text = re.sub(r'^#{1,6}\s*(.*)$', r'\1.', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    text = re.sub(r'^\s*>\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[-*•]\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s*', '', text, flags=re.MULTILINE)

    # 8. 이모지 및 특수 장식 기호 제거
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[💡🧠📌🎯🏗️⚖️⏱️🔍⚠️✨★☆■▶●◆▲▼※]+', ' ', text)

    # 9. 문장 마침표 및 공백 표준화
    text = re.sub(r':\s*\n', '.\n', text)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    cleaned = '. '.join(lines)
    cleaned = re.sub(r'\.{2,}', '.', cleaned)
    cleaned = re.sub(r'\s+([.,!?])', r'\1', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    if len(cleaned) > max_chars:
        # 다국어 요약 마무리 문구 처리
        if re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', cleaned[:300]) and not re.search(r'[\uac00-\ud7a3]', cleaned[:300]):
            cleaned = cleaned[:max_chars] + '... 以上で主要な要約の聴取を終了します。'
        elif not re.search(r'[\uac00-\ud7a3]', cleaned[:300]):
            cleaned = cleaned[:max_chars] + '... This concludes the audio summary.'
        else:
            cleaned = cleaned[:max_chars] + '... 이상으로 주요 요약 청취를 마칩니다.'

    return cleaned

async def generate_note_audio(
    note_id: str,
    markdown_text: str,
    voice_key: str = DEFAULT_VOICE,
    speed: str = '+0%'
) -> Dict[str, Any]:
    # 🔒 파일명/edge-tts 인자로 쓰이는 값은 화이트리스트로 정규화 (경로 조작 방지)
    if voice_key not in VOICES:
        voice_key = DEFAULT_VOICE
    voice_info = VOICES[voice_key]
    voice_id = voice_info['id']

    if not re.fullmatch(r'[+-]\d{1,3}%', speed or ''):
        speed = '+0%'
    safe_note = re.sub(r'[^A-Za-z0-9_-]', '_', note_id or 'temp_note')[:120] or 'temp_note'

    # 노트 내용이 수정되면 새 오디오를 만들도록 내용 해시를 캐시 키에 포함
    content_hash = hashlib.sha1((markdown_text or '').encode('utf-8')).hexdigest()[:8]
    safe_speed = speed.replace('+', 'p').replace('-', 'm').replace('%', '')
    filename = f'{safe_note}_{voice_key}_{safe_speed}_{content_hash}.mp3'
    filepath = os.path.join(AUDIO_DIR, filename)
    json_filename = f'{safe_note}_{voice_key}_{safe_speed}_{content_hash}.json'
    json_filepath = os.path.join(AUDIO_DIR, json_filename)

    script_text = clean_markdown_for_tts(markdown_text)
    if not script_text.strip():
        return {
            'success': False,
            'error': '음성으로 변환할 텍스트 내용이 비어 있습니다.'
        }

    # 캐시 존재 여부 확인 (MP3 및 Cues JSON 동시 캐싱)
    if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
        cues = []
        if os.path.exists(json_filepath):
            try:
                with open(json_filepath, "r", encoding="utf-8") as f:
                    cues = json.load(f)
            except Exception:
                cues = []
        if cues:
            return {
                'success': True,
                'filename': filename,
                'filepath': filepath,
                'voice': voice_info,
                'cached': True,
                'cues': cues
            }

    try:
        communicate = edge_tts.Communicate(script_text, voice_id, rate=speed)
        cues = []
        with open(filepath, "wb") as audio:
            async for message in communicate.stream():
                if message["type"] == "audio":
                    audio.write(message["data"])
                elif message["type"] == "SentenceBoundary":
                    start_s = round(message["offset"] / 10_000_000, 3)
                    dur_s = round(message["duration"] / 10_000_000, 3)
                    cues.append({
                        "start": start_s,
                        "end": round(start_s + dur_s, 3),
                        "text": message.get("text", "")
                    })

        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            return {'success': False, 'error': 'MP3 파일이 정상적으로 생성되지 않았습니다.'}

        if cues:
            try:
                with open(json_filepath, "w", encoding="utf-8") as f:
                    json.dump(cues, f, ensure_ascii=False)
            except Exception as e:
                print(f"Warning: failed to write cues json: {e}")

        return {
            'success': True,
            'filename': filename,
            'filepath': filepath,
            'voice': voice_info,
            'cached': False,
            'cues': cues
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'edge-tts 실행 실패: {str(e)}'
        }

def list_available_voices(lang: Optional[str] = None) -> List[Dict[str, Any]]:
    voices_list = []
    base_lang = (lang or "").split("-")[0].lower() if lang else None
    for k, v in VOICES.items():
        if base_lang and v.get('lang') != base_lang and 'multilingual' not in v['id'].lower():
            continue
        voices_list.append({
            'key': k,
            'name': v['name'],
            'gender': v['gender'],
            'lang': v.get('lang', 'ko')
        })
    if not voices_list and base_lang:
        return list_available_voices(None)
    return voices_list

def abbreviate_note_title(title: str, max_len: int = 40) -> str:
    """다운로드 파일명용 노트/영상 제목 축약 (특수문자 및 불필요한 태그 제거, 적정 길이 축약)"""
    if not title:
        return "학습노트"
    
    # 1. 앞쪽 브래킷/태그 제거: [TED], (4K), 【강의】, [Official Video], [자막] 등
    s = re.sub(r'^[\[\(\【][^\]\)\】]+[\]\)\】]\s*', '', title.strip())
    
    # 2. 뒤쪽 채널/출처 구분자 (| 채널명, - 부제 등) 정리
    for sep in (' | ', ' - '):
        if sep in s:
            parts = s.split(sep)
            if len(parts[0].strip()) >= 8:
                s = parts[0].strip()
                break
                
    # 3. 파일명 금지 특수문자 제거 (\ / : * ? " < > | # 등)
    s = re.sub(r'[\\/:*?"<>|#\r\n\t]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    
    if not s or s.lower() in ('study_note', 'temp_note', 'note'):
        return "학습노트"
        
    # 4. 적정 길이로 축약 (단어 중간 절단 방지)
    if len(s) > max_len:
        if s[max_len] == ' ' or (max_len > 0 and s[max_len - 1] == ' '):
            s = s[:max_len].strip()
        else:
            cut = s[:max_len].strip()
            last_space = cut.rfind(' ')
            if last_space > int(max_len * 0.6):
                s = cut[:last_space].strip()
            else:
                s = cut
                
    s = re.sub(r'[._\-\s]+$', '', s).strip()
    return s or "학습노트"

def get_audiobook_download_filename(title: str, max_len: int = 40, is_subtitles: bool = False) -> str:
    """오디오북 다운로드용 최종 MP3 파일명 생성 (예: '제목축약_오디오북.mp3' 또는 '제목축약_자막_더빙.mp3')"""
    short_title = abbreviate_note_title(title, max_len=max_len)
    
    # 언어별 자연스러운 접미사
    if is_subtitles:
        if re.search(r'[\uac00-\ud7a3]', short_title):
            suffix = "_자막_더빙"
        elif re.search(r'[\u3040-\u30ff]', short_title):
            suffix = "_字幕_吹き替え"
        else:
            suffix = "_Subtitle_Dub"
    else:
        if re.search(r'[\uac00-\ud7a3]', short_title):
            suffix = "_오디오북"
        elif re.search(r'[\u3040-\u30ff]', short_title):
            suffix = "_オー디オブック"
        else:
            suffix = "_Audiobook"
        
    return f"{short_title}{suffix}.mp3"

def clean_subtitle_line_for_tts(text: str) -> str:
    """자막 한 줄을 음성 합성용으로 정제 (효과음/음악 괄호, AI 태그, HTML 태그 등 제거)"""
    if not text:
        return ""
    # 1. 효과음, 음악, 청중 반응 등 괄호 표기 제거
    text = re.sub(r'\[[^\]]*(?:music|음악|applause|laughter|박수|웃음|sound|chuckle|gasp|효과음|소음)[^\]]*\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\([^\)]*(?:music|음악|applause|laughter|박수|웃음|sound|효과음)[^\)]*\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[♪♫♬♩]', '', text)
    # 2. AI 인용 잔여물 및 참조 태그 제거
    text = re.sub(r':?[a-zA-Z0-9_-]*chatgpt-[a-zA-Z0-9_-]+\{[^}]*\}', '', text)
    text = re.sub(r':[a-zA-Z0-9_-]+-reference\{[^}]*\}', '', text)
    text = re.sub(r'【[^】]*?(?:source|turn\d+|search|출처)[^】]*?】', '', text)
    text = re.sub(r'\[cite(?:ation)?:\s*[^\]]+\]', '', text, flags=re.IGNORECASE)
    # 3. HTML 및 타임스탬프 태그 정리
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\[\s*\d{1,2}:\d{2}(?::\d{2})?\s*\]', '', text)
    # 4. 공백 및 문장부호 정리
    text = re.sub(r'\s+([.,!?])', r'\1', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

async def generate_subtitles_audio(
    subtitles: List[Dict[str, Any]],
    video_id: str = "temp_video",
    title: str = "자막",
    mode: str = "ko",
    voice_key: str = DEFAULT_VOICE,
    speed: str = "+0%"
) -> Dict[str, Any]:
    """자막 대사 전체를 자연스러운 더빙 오디오북 MP3로 생성/캐싱하고, 각 자막 인덱스별 재생 큐(Cue)를 정밀 매핑합니다."""
    if voice_key not in VOICES:
        voice_key = DEFAULT_VOICE
    voice_info = VOICES[voice_key]
    voice_id = voice_info['id']

    if not re.fullmatch(r'[+-]\d{1,3}%', speed or ''):
        speed = '+0%'

    # 유효 자막 추출 및 정제
    valid_subs = []
    for idx, s in enumerate(subtitles or []):
        if mode in ("ko", "bilingual"):
            raw = (s.get("ko_text") or s.get("text") or "").strip()
        else:
            raw = (s.get("text") or "").strip()
        
        cleaned = clean_subtitle_line_for_tts(raw)
        if not cleaned:
            continue
        
        valid_subs.append({
            "sub_index": idx,
            "video_start": float(s.get("start", 0.0)),
            "video_end": float(s.get("end", 0.0)),
            "text": cleaned
        })

    if not valid_subs:
        return {
            'success': False,
            'error': '음성으로 변환할 유효한 자막 내용이 없습니다.'
        }

    script_lines = [s["text"] for s in valid_subs]
    full_script = "\n".join(script_lines)

    content_hash = hashlib.sha1(full_script.encode('utf-8')).hexdigest()[:8]
    safe_speed = speed.replace('+', 'p').replace('-', 'm').replace('%', '')
    safe_vid = re.sub(r'[^A-Za-z0-9_-]', '_', video_id or 'subtitles')[:80] or 'subtitles'
    norm_mode = "dub" if mode in ("ko", "bilingual") else "orig"
    
    # 🔍 캐시 확인: 과거 및 현재 생성된 모드(bilingual, ko, dub) 후보 파일명을 모두 탐색하여 즉시 캐시 히트
    candidate_modes = [norm_mode, mode]
    if mode in ("ko", "bilingual"):
        candidate_modes.extend(["bilingual", "ko", "dub"])
    candidate_modes = list(dict.fromkeys(candidate_modes))

    for c_mode in candidate_modes:
        c_fn = f"sub_{safe_vid}_{c_mode}_{voice_key}_{safe_speed}_{content_hash}.mp3"
        c_fp = os.path.join(AUDIO_DIR, c_fn)
        c_jfn = f"sub_{safe_vid}_{c_mode}_{voice_key}_{safe_speed}_{content_hash}.json"
        c_jfp = os.path.join(AUDIO_DIR, c_jfn)
        if os.path.exists(c_fp) and os.path.getsize(c_fp) > 1024 and os.path.exists(c_jfp):
            try:
                with open(c_jfp, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                return {
                    'success': True,
                    'filename': c_fn,
                    'filepath': c_fp,
                    'voice': voice_info,
                    'cached': True,
                    'cues': cached_data.get("cues", []),
                    'sub_cue_map': cached_data.get("sub_cue_map", {})
                }
            except Exception:
                pass

    # 캐시가 없는 경우 생성할 기본 파일명 (번역 모드는 dub 으로 통일)
    filename = f"sub_{safe_vid}_{norm_mode}_{voice_key}_{safe_speed}_{content_hash}.mp3"
    filepath = os.path.join(AUDIO_DIR, filename)
    json_filename = f"sub_{safe_vid}_{norm_mode}_{voice_key}_{safe_speed}_{content_hash}.json"
    json_filepath = os.path.join(AUDIO_DIR, json_filename)

    try:
        communicate = edge_tts.Communicate(full_script, voice_id, rate=speed)
        raw_cues = []
        with open(filepath, "wb") as audio:
            async for message in communicate.stream():
                if message["type"] == "audio":
                    audio.write(message["data"])
                elif message["type"] == "SentenceBoundary":
                    start_s = round(message["offset"] / 10_000_000, 3)
                    dur_s = round(message["duration"] / 10_000_000, 3)
                    raw_cues.append({
                        "start": start_s,
                        "end": round(start_s + dur_s, 3),
                        "text": message.get("text", "")
                    })

        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            return {'success': False, 'error': '자막 MP3 파일이 정상적으로 생성되지 않았습니다.'}

        # raw_cues 를 valid_subs 와 순차 매핑
        cues = []
        sub_ptr = 0
        num_subs = len(valid_subs)
        sub_cue_map = {}

        for cue in raw_cues:
            c_text = cue["text"].strip()
            matched_sub = valid_subs[min(sub_ptr, num_subs - 1)]

            if sub_ptr + 1 < num_subs:
                next_sub = valid_subs[sub_ptr + 1]
                if c_text in next_sub["text"] and c_text not in matched_sub["text"]:
                    sub_ptr += 1
                    matched_sub = next_sub

            sub_idx = matched_sub["sub_index"]
            cues.append({
                "start": cue["start"],
                "end": cue["end"],
                "text": cue["text"],
                "sub_index": sub_idx,
                "video_start": matched_sub["video_start"],
                "video_end": matched_sub["video_end"]
            })

            if sub_idx not in sub_cue_map:
                sub_cue_map[sub_idx] = cue["start"]

            if sub_ptr < num_subs - 1:
                if matched_sub["text"].strip().endswith(c_text) or c_text == matched_sub["text"].strip():
                    sub_ptr += 1

        # 캐시 JSON 저장
        try:
            with open(json_filepath, "w", encoding="utf-8") as f:
                json.dump({"cues": cues, "sub_cue_map": sub_cue_map}, f, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: failed to write subtitle cues json: {e}")

        return {
            'success': True,
            'filename': filename,
            'filepath': filepath,
            'voice': voice_info,
            'cached': False,
            'cues': cues,
            'sub_cue_map': sub_cue_map
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'자막 edge-tts 실행 실패: {str(e)}'
        }

