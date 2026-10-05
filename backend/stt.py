import os
from typing import Optional, Dict, Any, List
from groq import Groq
try:
    from extractor import format_srt_time, convert_to_srt
except ImportError:
    from backend.extractor import format_srt_time, convert_to_srt

import re

def split_long_segments(
    subtitles: List[Dict[str, Any]], 
    max_duration: float = 4.2, 
    max_chars: int = 50
) -> List[Dict[str, Any]]:
    """
    4초를 초과하거나 지나치게 긴 세그먼트를 쉼표, 접속사 기준으로
    2~3초 단위의 리드미컬하고 읽기 편한 자막 큐로 세분화합니다.
    """
    refined: List[Dict[str, Any]] = []

    for sub in subtitles:
        start = sub["start"]
        end = sub["end"]
        duration = end - start
        text = sub["text"].strip()

        if duration <= max_duration and len(text) <= max_chars:
            refined.append(sub)
            continue

        parts = re.split(r'([,;]|\s+(?:and|but|so|then|because|or)\s+)', text, flags=re.IGNORECASE)
        chunks = []
        curr = ""
        for p in parts:
            if not p:
                continue
            if p.strip() in [",", ";"]:
                curr += p
                if len(curr) >= 15:
                    chunks.append(curr.strip())
                    curr = ""
            elif p.strip().lower() in ["and", "but", "so", "then", "because", "or"]:
                if len(curr) >= 20:
                    chunks.append(curr.strip())
                    curr = p
                else:
                    curr += " " + p.strip()
            else:
                curr = (curr + " " + p).strip() if curr else p.strip()

        if curr:
            chunks.append(curr.strip())

        if len(chunks) <= 1:
            words = text.split()
            if len(words) >= 8 and duration > 3.5:
                mid = len(words) // 2
                chunks = [" ".join(words[:mid]), " ".join(words[mid:])]
            else:
                refined.append(sub)
                continue

        total_len = sum(len(c) for c in chunks)
        if total_len == 0:
            refined.append(sub)
            continue

        curr_time = start
        for c in chunks:
            c_dur = round(duration * (len(c) / total_len), 2)
            c_end = round(min(end, curr_time + c_dur), 2)
            refined.append({
                "start": round(curr_time, 2),
                "end": c_end,
                "duration": round(max(0.1, c_end - curr_time), 2),
                "timestamp": format_timestamp(curr_time),
                "text": c
            })
            curr_time = c_end

    return refined

def format_timestamp(seconds: float) -> str:
    sec = int(seconds)
    m = sec // 60
    s = sec % 60
    return f"{m:02d}:{s:02d}"

def transcribe_audio_groq(
    audio_path: str,
    api_key: Optional[str] = None,
    model: str = "whisper-large-v3"
) -> Dict[str, Any]:
    """
    Groq Cloud LPU의 Whisper-large-v3 모델을 사용하여 
    오디오 파일에서 타임스탬프 자막(SRT/큐)을 신속하게 추출합니다.
    """
    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        return {"success": False, "error": "Groq API 키가 설정되지 않았습니다."}

    if not os.path.exists(audio_path):
        return {"success": False, "error": f"오디오 파일을 찾을 수 없습니다: {audio_path}"}

    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    if file_size_mb > 25.0:
        return {
            "success": False, 
            "error": f"파일 크기({file_size_mb:.1f}MB)가 Groq 무료 업로드 한도(25MB)를 초과했습니다."
        }

    try:
        client = Groq(api_key=key)
        filename = os.path.basename(audio_path)

        with open(audio_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(filename, f.read()),
                model=model,
                response_format="verbose_json",
                temperature=0.0,
                prompt="Transcribe into concise, natural subtitle sentences."
            )

        segments = getattr(transcription, "segments", []) or []
        raw_subtitles: List[Dict[str, Any]] = []

        for seg in segments:
            if isinstance(seg, dict):
                start = float(seg.get("start", 0.0))
                end = float(seg.get("end", start + 2.0))
                text = str(seg.get("text", "")).strip()
            else:
                start = float(getattr(seg, "start", 0.0))
                end = float(getattr(seg, "end", start + 2.0))
                text = str(getattr(seg, "text", "")).strip()

            if not text:
                continue

            raw_subtitles.append({
                "start": round(start, 2),
                "end": round(end, 2),
                "duration": round(max(0.1, end - start), 2),
                "timestamp": format_timestamp(start),
                "text": text
            })

        # 4초 초과 세그먼트 스마트 분절 적용 (음성과 긴밀한 싱크 유지)
        subtitles = split_long_segments(raw_subtitles)

        full_text = getattr(transcription, "text", "") or " ".join(s["text"] for s in subtitles)
        srt_content = convert_to_srt(subtitles, lang_mode="original")

        return {
            "success": True,
            "subtitles": subtitles,
            "srt_text": srt_content,
            "full_text": full_text,
            "model_used": f"Groq {model}",
            "segment_count": len(subtitles)
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Groq Whisper 전사 실패: {str(e)}"
        }
