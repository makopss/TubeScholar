import os
import sys
import re
import asyncio
import hashlib
from typing import List, Dict, Any
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
    'injoon': {
        'name': '인준 (차분한 남성 다큐 톤)',
        'id': 'ko-KR-InJoonNeural',
        'gender': 'male'
    },
    'sunhi': {
        'name': '선희 (명확하고 지적인 여성 톤)',
        'id': 'ko-KR-SunHiNeural',
        'gender': 'female'
    },
    'hyunsu': {
        'name': '현수 (다국어 지원 남성 톤)',
        'id': 'ko-KR-HyunsuMultilingualNeural',
        'gender': 'male'
    }
}
DEFAULT_VOICE = 'injoon'

def clean_markdown_for_tts(markdown_text: str, max_chars: int = 15000) -> str:
    if not markdown_text:
        return ''

    text = markdown_text
    # 1. YAML 프론트매터 제거
    text = re.sub(r'^---\s*[\r\n]+[\s\S]*?[\r\n]+---\s*[\r\n]*', '', text.strip())

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

    if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
        return {
            'success': True,
            'filename': filename,
            'filepath': filepath,
            'voice': voice_info,
            'cached': True
        }

    script_text = clean_markdown_for_tts(markdown_text)
    if not script_text.strip():
        return {
            'success': False,
            'error': '음성으로 변환할 텍스트 내용이 비어 있습니다.'
        }

    try:
        communicate = edge_tts.Communicate(script_text, voice_id, rate=speed)
        await communicate.save(filepath)

        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
            return {'success': False, 'error': 'MP3 파일이 정상적으로 생성되지 않았습니다.'}

        return {
            'success': True,
            'filename': filename,
            'filepath': filepath,
            'voice': voice_info,
            'cached': False
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'edge-tts 실행 실패: {str(e)}'
        }

def list_available_voices() -> List[Dict[str, Any]]:
    return [
        {'key': k, 'name': v['name'], 'gender': v['gender']}
        for k, v in VOICES.items()
    ]
