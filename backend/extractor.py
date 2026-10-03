import re
from typing import List, Dict, Any, Optional
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp

def extract_video_id(url_or_id: str) -> Optional[str]:
    """유튜브 URL 또는 Video ID에서 11자리 Video ID를 추출합니다."""
    url_or_id = url_or_id.strip()
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url_or_id):
        return url_or_id
    
    patterns = [
        r'(?:v=|\/)([0-9A-Za-z_-]{11}).*',
        r'(?:youtu\.be\/)([0-9A-Za-z_-]{11})',
        r'(?:embed\/)([0-9A-Za-z_-]{11})',
        r'(?:shorts\/)([0-9A-Za-z_-]{11})',
        r'(?:live\/)([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return None

def format_timestamp(seconds: float) -> str:
    """초 단위 시간을 [MM:SS] 또는 [HH:MM:SS] 문자열로 변환합니다."""
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

def format_srt_time(seconds: float) -> str:
    """초 단위(실수)를 SRT 타임코드 규격 'HH:MM:SS,mmm'으로 변환합니다."""
    seconds = max(0.0, float(seconds))
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        seconds += 1
        millis = 0
    sec_int = int(seconds)
    hours = sec_int // 3600
    minutes = (sec_int % 3600) // 60
    secs = sec_int % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def normalize_subtitle_timings(
    subtitles: List[Dict[str, Any]],
    min_duration: float = 0.3
) -> List[Dict[str, Any]]:
    """
    유튜브 자동 생성 자막(롤링 캡션)은 각 세그먼트의 종료 시각이 다음 세그먼트의
    시작 시각보다 평균 약 2초 늦게 설정되어 있어 구간이 서로 겹칩니다.
    이 겹침 때문에 다음 대사(및 번역 자막)가 약 2초 늦게 표시되는 문제가 생기므로,
    각 세그먼트의 end를 다음 세그먼트의 start로 잘라 겹침을 제거합니다.
    (원본 리스트를 변경하지 않고 복사본을 반환합니다.)
    """
    if not subtitles:
        return subtitles

    items = [dict(s) for s in subtitles]
    items.sort(key=lambda s: float(s.get("start", 0.0) or 0.0))

    for i, sub in enumerate(items):
        start = float(sub.get("start", 0.0) or 0.0)
        end = sub.get("end")
        if end is None:
            end = start + float(sub.get("duration", 3.0) or 3.0)
        end = float(end)

        if i + 1 < len(items):
            next_start = float(items[i + 1].get("start", 0.0) or 0.0)
            if end > next_start:
                # 다음 대사 시작이 최우선 (시작 시각이 같을 때만 최소 표시 시간 적용)
                end = next_start if next_start > start else start + min_duration
        if end <= start:
            end = start + min_duration

        sub["start"] = round(start, 2)
        sub["end"] = round(end, 2)
        sub["duration"] = round(end - start, 2)
    return items

def convert_to_srt(subtitles: List[Dict[str, Any]], lang_mode: str = "original", sync_offset: float = 0.0) -> str:
    """
    자막 목록을 표준 .srt 포맷 문자열로 변환합니다.
    lang_mode: 'original' (원문), 'ko' (한국어 번역), 'bilingual' (한/영 병기)
    sync_offset: 싱크 보정(초). +값이면 자막이 더 빨리 표시되도록 시각을 앞당깁니다.
    """
    lines = []
    subtitles = normalize_subtitle_timings(subtitles)
    for idx, sub in enumerate(subtitles, 1):
        start_sec = float(sub.get("start", 0.0))
        end_sec = float(sub.get("end") or (start_sec + float(sub.get("duration", 3.0))))
        if end_sec <= start_sec:
            end_sec = start_sec + 2.5
        if sync_offset:
            start_sec = max(0.0, start_sec - sync_offset)
            end_sec = max(start_sec + 0.3, end_sec - sync_offset)
            
        start_str = format_srt_time(start_sec)
        end_str = format_srt_time(end_sec)
        
        orig_text = sub.get("text", "").strip()
        ko_text = sub.get("ko_text", "").strip()
        
        if lang_mode == "ko" and ko_text:
            text = ko_text
        elif lang_mode == "bilingual" and ko_text and orig_text:
            text = f"{ko_text}\n{orig_text}"
        else:
            text = orig_text or ko_text
            
        lines.append(f"{idx}\n{start_str} --> {end_str}\n{text}\n")
    return "\n".join(lines)

def convert_to_txt(subtitles: List[Dict[str, Any]], lang_mode: str = "original") -> str:
    """
    자막 목록을 타임스탬프가 포함된 텍스트 대본(.txt)으로 변환합니다.
    """
    lines = []
    for sub in subtitles:
        ts = sub.get("timestamp") or format_timestamp(sub.get("start", 0.0))
        orig_text = sub.get("text", "").strip()
        ko_text = sub.get("ko_text", "").strip()
        
        if lang_mode == "ko" and ko_text:
            lines.append(f"[{ts}] {ko_text}")
        elif lang_mode == "bilingual" and ko_text and orig_text:
            lines.append(f"[{ts}] {ko_text} ({orig_text})")
        else:
            lines.append(f"[{ts}] {orig_text or ko_text}")
    return "\n".join(lines)

def get_video_info(video_id: str) -> Dict[str, Any]:
    """yt-dlp를 사용하여 영상의 메타데이터(제목, 채널명, 썸네일, 길이 등)를 조회합니다."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        'skip_download': True,
        'extract_flat': True,
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "video_id": video_id,
                "title": info.get("title", "제목 없음"),
                "channel": info.get("uploader") or info.get("channel", "알 수 없는 채널"),
                "channel_id": info.get("channel_id", ""),
                "channel_url": info.get("channel_url", ""),
                "thumbnail": info.get("thumbnail") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                "duration": info.get("duration", 0),
                "duration_str": format_timestamp(info.get("duration", 0)),
                "view_count": info.get("view_count", 0),
                "upload_date": info.get("upload_date", ""),
                "description": (info.get("description") or "")[:500]
            }
    except Exception as e:
        return {
            "video_id": video_id,
            "title": f"YouTube Video ({video_id})",
            "channel": "YouTube",
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            "duration": 0,
            "duration_str": "00:00",
            "error": str(e)
        }

def get_video_transcript(video_id: str) -> Dict[str, Any]:
    """
    영상 자막을 추출하고, 적절한 청크(시간 간격 기준)로 묶어 반환합니다.
    한국어 자막이 존재하면 우선 선택하고, is_korean 플래그를 함께 반환합니다.
    """
    try:
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.list(video_id)
        
        # 자막 검색 전략: 한국어 수동 → 영어 수동 → 한국어 자동 → 영어 자동 → 아무거나
        transcript = None
        # 1차: 수동 생성 자막 (한국어 우선)
        for lang_codes in [['ko'], ['en', 'en-US']]:
            try:
                transcript = transcript_list.find_manually_created_transcript(lang_codes)
                break
            except Exception:
                continue
        # 2차: 자동 생성 자막 (한국어 우선)
        if transcript is None:
            for lang_codes in [['ko'], ['en', 'en-US']]:
                try:
                    transcript = transcript_list.find_generated_transcript(lang_codes)
                    break
                except Exception:
                    continue
        # 3차: find_transcript 폴백
        if transcript is None:
            try:
                transcript = transcript_list.find_transcript(['ko', 'en'])
            except Exception:
                transcript = next(iter(transcript_list))
        
        raw_items = transcript.fetch()
        language_code = transcript.language_code
        is_korean = language_code.startswith('ko')
        
        raw_subtitles = []
        grouped_chunks = []
        current_chunk_text = []
        current_chunk_start = 0.0
        
        for item in raw_items:
            text = getattr(item, 'text', '') if not isinstance(item, dict) else item.get('text', '')
            text = text.replace('\n', ' ').strip()
            start = getattr(item, 'start', 0.0) if not isinstance(item, dict) else item.get('start', 0.0)
            duration = getattr(item, 'duration', 3.0) if not isinstance(item, dict) else item.get('duration', 3.0)
            
            if text:
                # 유튜브 자동 생성 자막(ASR)의 연속 동일 대사 중복 병합
                if raw_subtitles and raw_subtitles[-1]["text"].strip() == text.strip():
                    raw_subtitles[-1]["end"] = round(start + duration, 2)
                    raw_subtitles[-1]["duration"] = round(raw_subtitles[-1]["end"] - raw_subtitles[-1]["start"], 2)
                else:
                    raw_subtitles.append({
                        "start": round(start, 2),
                        "duration": round(duration, 2),
                        "end": round(start + duration, 2),
                        "timestamp": format_timestamp(start),
                        "text": text
                    })

            if not current_chunk_text:
                current_chunk_start = start
                current_chunk_text.append(text)
            elif current_chunk_text[-1].strip() == text.strip():
                pass  # 동일 대사 연속 발생 시 청크 텍스트에서도 중복 방지
            elif (start - current_chunk_start) > 35.0:
                grouped_chunks.append({
                    "start": current_chunk_start,
                    "timestamp": format_timestamp(current_chunk_start),
                    "text": " ".join(current_chunk_text)
                })
                current_chunk_start = start
                current_chunk_text = [text]
            else:
                current_chunk_text.append(text)
                
        if current_chunk_text:
            grouped_chunks.append({
                "start": current_chunk_start,
                "timestamp": format_timestamp(current_chunk_start),
                "text": " ".join(current_chunk_text)
            })

        full_raw_text = "\n".join([f"[{c['timestamp']}] {c['text']}" for c in grouped_chunks])

        # 롤링 캡션 겹침 제거 (다음 대사 지연 표시 방지)
        raw_subtitles = normalize_subtitle_timings(raw_subtitles)

        return {
            "success": True,
            "language": language_code,
            "is_korean": is_korean,
            "is_generated": getattr(transcript, 'is_generated', False),
            "subtitles": raw_subtitles,
            "chunks": grouped_chunks,
            "full_text": full_raw_text
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"자막을 불러올 수 없습니다: {str(e)}"
        }

def get_channel_videos(channel_url: str, max_results: int = 15) -> List[Dict[str, Any]]:
    """채널 URL(또는 핸들 @...)에서 최근 영상 목록을 가져옵니다."""
    clean_url = channel_url.rstrip('/')
    if not clean_url.endswith('/videos') and not clean_url.endswith('/streams'):
        clean_url += '/videos'

    ydl_opts = {
        'extract_flat': 'in_playlist',
        'playlistend': max_results,
        'quiet': True,
        'no_warnings': True,
        'skip_download': True
    }
    
    videos = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            res = ydl.extract_info(clean_url, download=False)
            entries = res.get('entries', []) or []
            channel_name = res.get('title') or res.get('uploader') or "YouTube Channel"
            
            for item in entries:
                if not item:
                    continue
                v_id = item.get('id')
                if not v_id:
                    continue
                dur = item.get('duration') or 0
                videos.append({
                    "video_id": v_id,
                    "title": item.get('title', '제목 없음'),
                    "channel": channel_name,
                    "url": f"https://www.youtube.com/watch?v={v_id}",
                    "thumbnail": f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg",
                    "duration": dur,
                    "duration_str": format_timestamp(dur) if dur else "",
                })
    except Exception as e:
        print(f"채널 영상 파싱 실패: {e}")
    return videos

def parse_srt_vtt_text(sub_text: str) -> Dict[str, Any]:
    """로컬 SRT 또는 VTT 자막 텍스트를 분석하여 타임스탬프 청크로 변환합니다."""
    lines = sub_text.replace('\r\n', '\n').split('\n')
    time_pattern = re.compile(r'(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})')
    time_short_pattern = re.compile(r'(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2})[,.](\d{3})')

    chunks = []
    current_start = 0.0
    current_texts = []
    
    for line in lines:
        line = line.strip()
        if not line or line.isdigit() or line.startswith('WEBVTT') or line.startswith('NOTE'):
            continue
        
        m = time_pattern.search(line)
        if m:
            if current_texts:
                chunks.append({
                    "start": current_start,
                    "timestamp": format_timestamp(current_start),
                    "text": " ".join(current_texts)
                })
                current_texts = []
            h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            current_start = h * 3600 + mi * 60 + s
            continue
            
        m2 = time_short_pattern.search(line)
        if m2:
            if current_texts:
                chunks.append({
                    "start": current_start,
                    "timestamp": format_timestamp(current_start),
                    "text": " ".join(current_texts)
                })
                current_texts = []
            mi, s = int(m2.group(1)), int(m2.group(2))
            current_start = mi * 60 + s
            continue

        clean_text = re.sub(r'<[^>]+>', '', line)
        if clean_text:
            current_texts.append(clean_text)

    if current_texts:
        chunks.append({
            "start": current_start,
            "timestamp": format_timestamp(current_start),
            "text": " ".join(current_texts)
        })

    # 35초 단위로 병합
    merged_chunks = []
    curr_chunk = []
    curr_start = 0.0
    for c in chunks:
        if not curr_chunk:
            curr_start = c["start"]
            curr_chunk.append(c["text"])
        elif (c["start"] - curr_start) > 35.0:
            merged_chunks.append({
                "start": curr_start,
                "timestamp": format_timestamp(curr_start),
                "text": " ".join(curr_chunk)
            })
            curr_start = c["start"]
            curr_chunk = [c["text"]]
        else:
            curr_chunk.append(c["text"])
            
    if curr_chunk:
        merged_chunks.append({
            "start": curr_start,
            "timestamp": format_timestamp(curr_start),
            "text": " ".join(curr_chunk)
        })

    full_text = "\n".join([f"[{c['timestamp']}] {c['text']}" for c in merged_chunks])
    return {
        "success": True,
        "language": "local",
        "is_generated": False,
        "subtitles": chunks,
        "chunks": merged_chunks,
        "full_text": full_text
    }

