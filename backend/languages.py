"""자막 원문/번역 언어 공통 정의 (백엔드·프론트엔드가 같은 목록을 사용)."""
from typing import Optional

# 번역 대상 언어 (코드 → 한국어 표시명). 순서 = 화면 표시 순서
TARGET_LANGUAGES = {
    "ko": "한국어",
    "en": "영어",
    "ja": "일본어",
    "zh-Hans": "중국어(간체)",
    "zh-Hant": "중국어(번체)",
    "es": "스페인어",
    "fr": "프랑스어",
    "de": "독일어",
    "pt": "포르투갈어",
    "ru": "러시아어",
    "it": "이탈리아어",
    "vi": "베트남어",
    "th": "태국어",
    "id": "인도네시아어",
    "ar": "아랍어",
    "hi": "힌디어",
    "tr": "터키어",
}
DEFAULT_TARGET_LANG = "ko"

# 중국어는 간체/번체가 서로 다른 글자이므로 같은 언어로 취급하면 안 됨
_ZH_SCRIPT_ALIASES = {
    "zh-hans": {"zh-hans", "zh-cn", "zh-sg", "zh-my"},
    "zh-hant": {"zh-hant", "zh-tw", "zh-hk", "zh-mo"},
}

# 유튜브가 쓰는 옛 언어 코드 → 표준 코드
_LEGACY_CODES = {"iw": "he", "in": "id", "ji": "yi", "jw": "jv"}


def base_lang(code: Optional[str]) -> str:
    """'en-US' → 'en', 'iw' → 'he'"""
    b = (code or "").split("-")[0].lower()
    return _LEGACY_CODES.get(b, b)


def zh_script(code: Optional[str]) -> Optional[str]:
    """중국어 코드의 글자 체계('zh-hans'/'zh-hant'), 판단 불가/중국어 아님이면 None."""
    c = (code or "").lower()
    for script, aliases in _ZH_SCRIPT_ALIASES.items():
        if c in aliases:
            return script
    return None


def lang_match_level(track_code: Optional[str], wanted: Optional[str]) -> int:
    """
    트랙 언어가 원하는 언어와 얼마나 맞는지: 2=정확(별칭 포함), 1=같은 언어(지역만 다름), 0=불일치.
    중국어는 간체/번체가 다르면 불일치로 봄.
    """
    if not track_code or not wanted:
        return 0
    t, w = track_code.lower(), wanted.lower()
    if t == w:
        return 2
    ts, ws = zh_script(t), zh_script(w)
    if ts and ws:
        return 2 if ts == ws else 0
    if base_lang(t) != base_lang(w):
        return 0
    if base_lang(w) == "zh" and (ts or ws):
        # 한쪽만 글자 체계가 명시된 중국어('zh' 등)는 약한 일치
        return 1
    return 1


def is_same_language(a: Optional[str], b: Optional[str]) -> bool:
    return lang_match_level(a, b) > 0


def language_name(code: Optional[str]) -> str:
    if not code:
        return "번역"
    if code in TARGET_LANGUAGES:
        return TARGET_LANGUAGES[code]
    for k, v in TARGET_LANGUAGES.items():
        if lang_match_level(code, k) == 2:
            return v
    for k, v in TARGET_LANGUAGES.items():
        if lang_match_level(code, k) > 0:
            return v
    return code


def normalize_target_lang(code: Optional[str]) -> str:
    """허용 목록에 있는 번역 언어만 사용 (그 외는 기본값)."""
    return code if code in TARGET_LANGUAGES else DEFAULT_TARGET_LANG
