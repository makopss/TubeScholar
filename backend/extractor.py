import re
from bisect import bisect_right
from typing import List, Dict, Any, Optional
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp
from languages import base_lang, lang_match_level, is_same_language, normalize_target_lang, DEFAULT_TARGET_LANG

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
                "description": (info.get("description") or "")[:500],
                "language": info.get("language") or ""  # 영상 기본 언어 (원문 자막 감지 힌트)
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

def _track_info(t) -> Dict[str, Any]:
    return {
        "code": t.language_code,
        "name": t.language,
        "is_generated": bool(getattr(t, "is_generated", False)),
        # 선택 상자 값: 같은 언어의 공식/자동 자막을 구분
        "value": f"{t.language_code}:auto" if getattr(t, "is_generated", False) else t.language_code,
    }


def detect_original_language(tracks: List[Any], ytdlp_lang: Optional[str] = None) -> Optional[str]:
    """
    영상의 실제(말하는) 언어를 추정합니다.
    1) yt-dlp 메타데이터의 기본 영상 언어가 있고 트랙 목록에 매칭되는 것이 있는 경우:
       - 다국어 더빙 영상(ASR이 여러 개인 경우)에서는 메타데이터 언어가 원본 언어
    2) 자동 생성 자막(ASR)이 단 1개만 존재하는 경우:
       - 단일 음성 영상에서는 YouTube가 실제 발화 언어로만 유일한 ASR을 생성하므로 그 언어 채택
    3) 자동 생성 자막이 여러 개(다국어 더빙)이고 ytdlp_lang과 일치하는 트랙이 없는 경우:
       - 영어(en) 트랙 우선, 없으면 첫 번째 ASR 트랙
    4) 자동 생성 자막이 없는 경우:
       - ytdlp_lang 일치 트랙 -> 첫 번째 자막 트랙
    """
    if not tracks:
        return ytdlp_lang

    gen = [t for t in tracks if getattr(t, "is_generated", False)]

    # 1. yt-dlp 메타데이터의 언어가 있고, 자막 트랙 중 매칭되는 것이 있는 경우
    if ytdlp_lang:
        for level in (2, 1):
            matching = [t for t in tracks if lang_match_level(t.language_code, ytdlp_lang) == level]
            if matching:
                # 공식 자막 우선, 없으면 자동 생성 자막
                manual = [t for t in matching if not getattr(t, "is_generated", False)]
                chosen = manual[0] if manual else matching[0]
                return chosen.language_code

    # 2. ASR 자동 생성 자막이 딱 1개인 경우 (단일 음성 영상: TED 등)
    if len(gen) == 1:
        return gen[0].language_code

    # 3. ASR이 여러 개(다국어 오디오)이지만 ytdlp_lang 매칭이 안 된 경우: 영어(en) 트랙 우선
    if len(gen) > 1:
        for level in (2, 1):
            en_tracks = [t for t in gen if lang_match_level(t.language_code, "en") == level]
            if en_tracks:
                return en_tracks[0].language_code
        return gen[0].language_code

    # 4. ytdlp_lang 은 있지만 매칭 트랙이 없는 경우
    if ytdlp_lang:
        return ytdlp_lang

    # 5. 마지막 fallback: 첫 번째 트랙
    return tracks[0].language_code


def pick_track(tracks: List[Any], lang: Optional[str], prefer_generated: bool = False):
    """원하는 언어의 트랙 선택: 정확 일치 > 같은 언어(지역 다름), 각각 공식 자막 우선(prefer_generated면 자동 우선)."""
    if not lang:
        return None
    for level in (2, 1):
        pool = [t for t in tracks if lang_match_level(t.language_code, lang) == level]
        if not pool:
            continue
        manual = [t for t in pool if not getattr(t, "is_generated", False)]
        gen = [t for t in pool if getattr(t, "is_generated", False)]
        ordered = (gen + manual) if prefer_generated else (manual + gen)
        return ordered[0]
    return None


def select_source_track(tracks: List[Any], source_lang: Optional[str] = None, ytdlp_lang: Optional[str] = None):
    """
    원문 트랙 결정. source_lang 은 'en' (공식 우선) 또는 'en:auto' (자동 자막 지정) 형식.
    지정이 없으면 실제 발화 언어를 감지하여 그 언어의 공식 자막 → 자동 자막 순으로 고릅니다.
    """
    if not tracks:
        return None
    if source_lang:
        code, _, flag = source_lang.partition(":")
        t = pick_track(tracks, code, prefer_generated=(flag == "auto"))
        if t:
            return t
    t = pick_track(tracks, detect_original_language(tracks, ytdlp_lang))
    return t or tracks[0]


def _cue_list(raw_items) -> List[Dict[str, Any]]:
    cues = []
    for item in raw_items:
        get = (lambda k, d: item.get(k, d)) if isinstance(item, dict) else (lambda k, d: getattr(item, k, d))
        text = (get("text", "") or "").replace("\n", " ").strip()
        if not text:
            continue
        start = float(get("start", 0.0) or 0.0)
        dur = float(get("duration", 0.0) or 0.0)
        cues.append({"start": start, "end": start + (dur if dur > 0 else 2.0), "text": text})
    cues.sort(key=lambda c: c["start"])
    return cues


def align_track_to_segments(src_rows: List[Dict[str, Any]], tgt_cues: List[Dict[str, Any]]) -> List[str]:
    """
    다른 시간표로 만들어진 번역 자막(tgt_cues)을 원문 줄(src_rows)에 시간 기준으로 정렬합니다.
    - 각 번역 줄은 '가운데 시점'이 속한 원문 줄(start_i <= mid < start_{i+1})에 배정, 같은 줄에 여러 개면 이어붙임
    - 배정이 없는 원문 줄은 그 줄의 가운데 시점을 덮는 번역 줄로 채움(긴 번역 줄이 여러 원문 줄에 걸칠 때)
    - 그래도 없으면 '' (화면에서는 원문으로 대체 표시)
    반환: 원문 줄과 같은 길이의 번역문 리스트
    """
    n = len(src_rows)
    if n == 0:
        return []
    starts = [float(r.get("start", 0.0) or 0.0) for r in src_rows]
    buckets: List[List[str]] = [[] for _ in range(n)]
    cues = sorted(tgt_cues, key=lambda c: c["start"])
    for c in cues:
        mid = (c["start"] + c["end"]) / 2.0
        i = max(0, bisect_right(starts, mid) - 1)
        if not buckets[i] or buckets[i][-1] != c["text"]:
            buckets[i].append(c["text"])

    cue_starts = [c["start"] for c in cues]
    out = []
    for i, row in enumerate(src_rows):
        if buckets[i]:
            out.append(" ".join(buckets[i]))
            continue
        r_start = starts[i]
        r_end = row.get("end")
        if r_end is None:
            r_end = r_start + float(row.get("duration", 2.0) or 2.0)
        if i + 1 < n:
            r_end = min(float(r_end), starts[i + 1])
        m = (r_start + float(r_end)) / 2.0
        j = bisect_right(cue_starts, m) - 1
        out.append(cues[j]["text"] if j >= 0 and cues[j]["start"] <= m < cues[j]["end"] else "")
    return out


def list_transcript_tracks(video_id: str, ytdlp_lang: Optional[str] = None) -> Dict[str, Any]:
    """원문 선택 상자용 자막 트랙 목록 (자막 본문은 받지 않는 가벼운 요청 1회)."""
    try:
        tracks = list(YouTubeTranscriptApi().list(video_id))
        return {
            "success": True,
            "tracks": [_track_info(t) for t in tracks],
            "original_lang": detect_original_language(tracks, ytdlp_lang),
        }
    except Exception as e:
        return {"success": False, "error": f"자막 목록을 불러올 수 없습니다: {str(e)[:200]}", "tracks": []}


def get_video_transcript(
    video_id: str,
    source_lang: Optional[str] = None,
    target_lang: Optional[str] = DEFAULT_TARGET_LANG,
    ytdlp_lang: Optional[str] = None
) -> Dict[str, Any]:
    """
    영상 자막을 추출하고, 적절한 청크(시간 간격 기준)로 묶어 반환합니다.
    - 원문: 영상의 실제 발화 언어 자막 (source_lang 으로 직접 지정 가능)
    - 번역: target_lang 의 유튜브 공식 자막이 있으면 원문 줄에 시간 정렬하여 각 줄 'ko_text'(=번역문 필드)에 채움
            원문과 번역 언어가 같으면 translation_source='same' (번역 불필요)
    is_korean 은 '원문이 한국어'인지를 뜻합니다 (학습 노트 프롬프트 선택용).
    """
    target_lang = normalize_target_lang(target_lang)
    try:
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.list(video_id)
        tracks = list(transcript_list)
        transcript = select_source_track(tracks, source_lang, ytdlp_lang)
        if transcript is None:
            raise ValueError("이 영상에는 자막 트랙이 없습니다.")

        raw_items = transcript.fetch()
        language_code = transcript.language_code
        is_korean = base_lang(language_code) == 'ko'
        
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

        # 번역문 준비: 같은 언어면 불필요, 아니면 번역 언어의 '공식' 자막을 시간 정렬하여 사용
        translation_source = None
        translation_track = None
        if is_same_language(language_code, target_lang):
            translation_source = "same"
        else:
            tgt = pick_track([t for t in tracks if not getattr(t, "is_generated", False)], target_lang)
            if tgt is not None and tgt is not transcript:
                try:
                    texts = align_track_to_segments(raw_subtitles, _cue_list(tgt.fetch()))
                    if any(texts):
                        for row, tx in zip(raw_subtitles, texts):
                            if tx:
                                row["ko_text"] = tx  # 'ko_text' = 번역문 필드 (언어는 target_lang)
                        translation_source = "youtube"
                        translation_track = tgt.language_code
                except Exception as te:
                    # 번역 자막 실패(차단 등)는 원문 제공에 영향 주지 않음 → 사용자는 Gemini 번역 가능
                    print(f"[!] 공식 번역 자막({target_lang}) 불러오기 실패: {str(te)[:120]}")

        return {
            "success": True,
            "language": language_code,
            "is_korean": is_korean,
            "is_generated": getattr(transcript, 'is_generated', False),
            "source_lang": _track_info(transcript)["value"],
            "original_lang": detect_original_language(tracks, ytdlp_lang),
            "target_lang": target_lang,
            "translation_source": translation_source,
            "translation_track": translation_track,
            "tracks": [_track_info(t) for t in tracks],
            "subtitles": raw_subtitles,
            "chunks": grouped_chunks,
            "full_text": full_raw_text
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"자막을 불러올 수 없습니다: {str(e)}"
        }

def is_valid_youtube_channel_url(channel_url: str) -> bool:
    """유효한 유튜브 채널 URL 또는 @핸들 형식인지 검증합니다."""
    u = (channel_url or "").strip()
    if re.fullmatch(r"^@[A-Za-z0-9_.-]{2,60}$", u):
        return True
    pattern = r"^https?:\/\/(?:[a-zA-Z0-9-]+\.)?youtube\.com\/(?:@|channel\/|c\/|user\/)[A-Za-z0-9_.-]+"
    return bool(re.match(pattern, u, re.IGNORECASE))

def get_channel_videos(channel_url: str, max_results: int = 15) -> List[Dict[str, Any]]:
    """채널 URL(또는 핸들 @...)에서 최근 영상 목록을 가져옵니다."""
    if not is_valid_youtube_channel_url(channel_url):
        return []

    u = channel_url.strip()
    if u.startswith('@'):
        u = f"https://www.youtube.com/{u}"
    clean_url = u.rstrip('/')
    if not clean_url.endswith('/videos') and not clean_url.endswith('/streams'):
        clean_url += '/videos'

    safe_max_results = min(max(1, int(max_results or 15)), 50)

    ydl_opts = {
        'extract_flat': 'in_playlist',
        'playlistend': safe_max_results,
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
    # HH:MM:SS,mmm 또는 MM:SS.mmm (VTT 단축형) 모두 허용, 밀리초·종료 시각까지 보존
    ts = r'(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[,.](\d{1,3})'
    cue_pattern = re.compile(ts + r'\s*-->\s*' + ts)

    def _secs(h, mi, s, ms) -> float:
        return int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, '0')) / 1000.0

    chunks = []
    current_start = 0.0
    current_end: Optional[float] = None
    current_texts = []

    def _flush():
        if current_texts:
            item = {
                "start": round(current_start, 3),
                "timestamp": format_timestamp(current_start),
                "text": " ".join(current_texts)
            }
            if current_end is not None and current_end > current_start:
                item["end"] = round(current_end, 3)
                item["duration"] = round(current_end - current_start, 3)
            chunks.append(item)

    for line in lines:
        line = line.strip()
        if not line or line.isdigit() or line.startswith('WEBVTT') or line.startswith('NOTE'):
            continue

        m = cue_pattern.search(line)
        if m:
            _flush()
            current_texts = []
            g = m.groups()
            current_start = _secs(g[0], g[1], g[2], g[3])
            current_end = _secs(g[4], g[5], g[6], g[7])
            continue

        clean_text = re.sub(r'<[^>]+>', '', line)
        if clean_text:
            current_texts.append(clean_text)

    _flush()

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

