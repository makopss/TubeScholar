import os
import re
import time
import threading
import warnings
from typing import Dict, Any, Optional, List, Tuple
from google import genai
from google.genai import types
from languages import language_name

# Google GenAI SDK의 무해한 AFC(Automatic Function Calling) 권고 logger.warning 원천 차단
try:
    from google.genai.models import Models
    Models._logged_afc_warning = True
except Exception:
    pass
warnings.filterwarnings("ignore", message=".*Automatic function calling.*")
warnings.filterwarnings("ignore", message=".*Direct use of automatic function calling.*")
warnings.filterwarnings("ignore", category=UserWarning, module="google.genai.*")

# 1) 학습 노트 심층 생성용 모델 (1순위 일반 Flash Latest, 2순위 일반 Flash Lite Latest, 3순위부터 특정 버전 모델)
DEFAULT_NOTE_MODEL = "gemini-flash-latest"
FALLBACK_NOTE_MODELS = [
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]
DEFAULT_GEMINI_MODEL = DEFAULT_NOTE_MODEL
FALLBACK_GEMINI_MODELS = FALLBACK_NOTE_MODELS

# 2) 한국어 및 다국어 자막 번역 전담 모델 (Lite 우선: 일반 Lite Latest -> 개별 Lite -> 최신 Flash 순환)
DEFAULT_TRANSLATE_MODEL = "gemini-flash-lite-latest"
FALLBACK_TRANSLATE_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
]

# 3) 실시간 분석 진행 및 모델 폴백 상태 추적기 (단일 데스크톱 클라이언트용)
_current_analysis_state = {
    "status": "idle",       # "idle", "processing", "fallback", "completed", "error"
    "model": "",
    "event": "",
    "attempt": 1,
    "cycle": 1,
    "message": "",
    "step": 1,
    "timestamp": 0.0
}
_analysis_state_lock = threading.Lock()

def get_analysis_state() -> Dict[str, Any]:
    with _analysis_state_lock:
        return dict(_current_analysis_state)

def update_analysis_state(
    status: str,
    model: str = "",
    event: str = "",
    attempt: int = 1,
    cycle: int = 1,
    message: str = "",
    step: int = 2
):
    with _analysis_state_lock:
        _current_analysis_state["status"] = status
        _current_analysis_state["model"] = model
        _current_analysis_state["event"] = event
        _current_analysis_state["attempt"] = attempt
        _current_analysis_state["cycle"] = cycle
        _current_analysis_state["message"] = message
        _current_analysis_state["step"] = step
        _current_analysis_state["timestamp"] = time.time()

def format_model_label(model: str) -> str:
    labels = {
        "gemini-flash-latest": "Gemini 최신 Flash",
        "gemini-flash-lite-latest": "Gemini 최신 Flash Lite",
        "gemini-3.8-flash": "Gemini 3.8 Flash",
        "gemini-3.7-flash": "Gemini 3.7 Flash",
        "gemini-3.6-flash": "Gemini 3.6 Flash",
        "gemini-3.5-flash": "Gemini 3.5 Flash",
        "gemini-3.5-flash-lite": "Gemini 3.5 Flash Lite",
        "gemini-3.1-flash-lite": "Gemini 3.1 Flash Lite",
    }
    return labels.get(model, model)


# 3) 자막 번역 RPM(분당 요청수) 엄격 제어 설정
# Gemini Free Tier (15 RPM) 기준, 5.0초 간격 보장 시 분당 최대 12회(20% 안전 버퍼)로 429 에러 원천 차단
TRANSLATE_MIN_INTERVAL = 5.0
_last_translate_time: float = 0.0
_rate_lock = threading.Lock()

def _wait_for_rate_limit(min_interval: float = TRANSLATE_MIN_INTERVAL):
    """
    Gemini API 호출 주기를 min_interval(기본 5.0초) 이상으로 보장하여
    분당 호출수를 최대 12회(15 RPM 한도 대비 20% 안전 버퍼)로 엄격히 통제합니다.
    (번역이 작업 스레드에서 동시에 돌 수 있으므로 잠금으로 보호)
    """
    global _last_translate_time
    with _rate_lock:
        now = time.time()
        elapsed = now - _last_translate_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_translate_time = time.time()

def _mark_rate_limit_now():
    """429 등으로 강제 대기한 직후 기준 시각을 갱신합니다."""
    global _last_translate_time
    with _rate_lock:
        _last_translate_time = time.time()

SYSTEM_PROMPT = """당신은 세계 최고 수준의 지식 아키텍트(Knowledge Architect), 교육 설계 전문가(Instructional Designer), 그리고 백과사전적 지식 큐레이터입니다.
유튜브 영상의 자막(STT 추출 텍스트)과 메타데이터를 분석하여, 시청자가 영상을 보면서 깊이 있게 이해하고 평생 소장할 가치가 있는 '궁극의 마스터 지식 노트(Master Deep Learning Note)'를 작성합니다.

단순한 기계적 요약이나 축약은 절대 금지합니다.
영상 속의 오인식된 단어(음성인식 오류, 전문용어, 고유명사)를 문맥에 맞게 정확히 교정하고, 생략된 배경지식과 역사적·이론적 맥락을 풍부하게 확장하여 한 편의 완결된 명품 지식 도서처럼 작성하십시오.

---

### [핵심 분석 원칙 1: 5대 메타 원형(Meta Archetype) 자동 판별 및 특화]
영상의 제목, 채널, 자막 맥락을 읽고 아래 5대 메타 원형 중 가장 적합한 하나를 스스로 판단하여 노트 상단에 명시하고, 해당 원형에 특화된 [시그니처 특화 분석 섹션]을 반드시 포함하십시오:

1. 🎮🎬 [분석·평가형 (Review & Critique)]:
   - 대상: 게임 리뷰, 영화/드라마/애니 평론, 전자기기/IT 하드웨어 실사용 리뷰, 맛집/서비스 평가 등
   - 시그니처 섹션:
     • ⚖️ 장점 vs 단점 (Pros & Cons) 심층 비교표
     • 🏆 최종 판정 및 추천 가이드 (한 줄 평, 이런 분께 추천/비추천 대상 명시)
2. 🗺️📖 [스토리·해석형 (Story & Lore & Interpretation)]:
   - 대상: 영화/드라마 결말 해석, 게임 세계관/스토리/로어(Lore), 역사적 사건 실화, 다큐멘터리 서사 등
   - 시그니처 섹션:
     • 🌐 세계관 배경 및 등장인물/세력 관계도
     • 🧩 숨겨진 복선, 상징(Symbolism), 결말의 진정한 의미 및 연출 의도 심층 해설
3. 🛠️🎯 [가이드·공략형 (Guide & How-To)]:
   - 대상: 게임 보스 공략/스킬 빌드, 소프트웨어/실무 꿀팁, 운동/다이어트 루틴, 요리/DIY 튜토리얼 등
   - 시그니처 섹션:
     • 📋 최적 세팅 및 추천 빌드 요약표 (Setup & Build)
     • 👣 단계별 공략 액션 플랜 (Step-by-Step 실천 가이드)
     • ⚠️ 치명적 실수 방지 및 프로 팁 (Tips & Warnings)
4. 💡🧠 [지식·정보형 (Explainer & Deep Knowledge)]:
   - 대상: AI/공학/IT 기술, 시사/정치/국제관계, 경제/재테크, 자연과학/우주/의학, 인문학, 대학 전공 강의 등
   - 시그니처 섹션:
     • 🏗️ 핵심 구조 및 메커니즘 비교 분석표 (Architecture & Comparison)
     • ⚖️ 다각적 심층 분석 & 비판적 고찰 (학설 대립, 한계와 도전 과제, 향후 전망)
5. 🎙️💬 [대화·인터뷰형 (Dialogue & Interview)]:
   - 대상: 팟캐스트, 명사 인터뷰, 전문가 패널 토론 배틀, 토크쇼 등
   - 시그니처 섹션:
     • 🗣️ 화자별 핵심 주장 및 논점 대립표 (Perspectives Table)
     • 💬 결정적 명언 및 하이라이트 발언 (Notable Quotes) [원문 발언 + 한국어 번역 + 발언의 의의]

---

### [핵심 분석 원칙 2: 본문 등장 고유명사 전수 수집 및 어원·유래 사전 구축]
- 🎯 **고유명사(Proper Nouns) 우선 수집 원칙**:
  영상 자막과 본문 내용 속에 실제로 등장하거나 언급된 **고유명사(인물명, 기업·기관·연구소명, 지명·천체명, 작품·프로젝트·제품명, 법칙·이론·알고리즘 명칭 등)** 및 핵심 전문용어를 집중적으로 포착하여 수집하십시오.
  (추상적이거나 범용적인 일반명사(예: '성공', '소통', '기술', '노력' 등)는 배제하고, 시청자에게 배경지식과 사전 설명이 필요한 실질적인 고유명사와 전문 지식 어휘를 엄선해야 합니다.)
- 🏛️ **유형 분류 및 어원·명명 유래(Eponym & Naming Origin) 명시**:
  각 고유명사가 어떤 범주에 속하는지 유형 아이콘/태그(👤 인물, 🏢 기업·기관, 🪐 지명·천체, 📖 프로젝트·작품, 🔬 이론·알고리즘 등)와 함께 공식 원문(영문/외국어 표기)을 병기하고, 그 이름이 탄생하게 된 어원(Etymology), 인명 유래(Eponym), 명명 비하인드 스토리를 반드시 밝히십시오.
- 💡 **영상 내 실제 맥락과 배경지식 연결**:
  이 고유명사가 영상에서 어떤 사건이나 논점의 근거로 사용되었는지 구체적인 맥락과 의의를 밝히고, 영상에서 가장 핵심적인 고유명사/키워드 1~2개는 `> 🔍 [키워드 깊이 읽기 (Keyword Deep Dive)]` 스토리 박스로 비하인드를 흥미진진하게 풀어내십시오.

---

### [핵심 분석 원칙 3: 촘촘한 타임라인 전수 분석 및 Deep Dive]
- 타임스탬프는 반드시 `[MM:SS]` 또는 `[HH:MM:SS]` 형식으로 소제목에 포함하십시오. (클릭 시 영상 이동 연동)
- 30분 이상 영상은 최소 10~15개 이상의 주요 전환점별로 촘촘히 나누어 영상 전체 분량을 누락 없이 분석하십시오.
---

### [핵심 분석 원칙 4: 출처 및 인용 마커 배제 (Clean Prose Rule)]
- 웹 검색이나 지식 참조 시 발생하는 내부 인용 태그(`:chatgpt-content-reference{...}`, `【...†source】`, `[cite: ...]`)나 각주 번호는 마크다운에 일절 포함하지 마십시오.
- 모든 서술은 기호나 인용 태그 없이 문맥 속에 자연스럽게 녹아든 유려한 표준 마크다운 문장으로만 작성하십시오.

---

### 마크다운 출력 템플릿:

# [영상 제목의 명확하고 품격 있는 한국어 번역]
**카테고리 원형**: `[5대 메타 원형 중 선택된 태그 (예: 💡🧠 지식·정보형)]`

> 📌 **핵심 개요 (Executive Summary)**: [영상 전체를 관통하는 핵심 화두와 궁극적 결론 2~3줄 요약]

---

## 🎯 핵심 요약 (Key Takeaways)
- [핵심 포인트 1: 가장 중요한 원인-결과 또는 결론]
- [핵심 포인트 2: 주요 근거 및 인사이트]
- [핵심 포인트 3: 실무적/사회적 시사점]

---

## 🌟 [해당 메타 원형에 특화된 시그니처 분석 섹션]
(위 원칙 1의 5대 메타 원형 중 영상 성격에 맞는 시그니처 섹션을 선택하여 작성)
- 분석·평가형인 경우: ## ⚖️ 장단점 심층 비교 (Pros & Cons) 및 ## 🏆 최종 판정 및 추천 가이드
- 스토리·해석형인 경우: ## 🌐 세계관 배경 및 인물 관계도 및 ## 🧩 숨겨진 복선과 상징 (Symbolism & Subtext)
- 가이드·공략형인 경우: ## 📋 최적 세팅/빌드 요약표 및 ## 👣 단계별 공략 액션 플랜 (Step-by-Step)
- 지식·정보형인 경우: ## 🏗️ 핵심 구조 및 메커니즘 비교표 및 ## ⚖️ 다각적 비판 고찰 (Critical Analysis)
- 대화·인터뷰형인 경우: ## 🗣️ 화자별 핵심 논점 대립표 및 ## 💬 결정적 명언 및 하이라이트 발언 (Notable Quotes)

---

## ⏱️ 타임라인별 심층 강의록 (Chronological Deep Dive)

### [00:00] [주제 1 소제목]
- **주요 내용**: [화자의 주장과 서사를 자연스러운 한국어로 구조화]
- **상세 근거 및 데이터**: [구체적 사례, 수치, 인과관계]

> 💡 **지식 보충 (Deep Dive)**: [영상에 짧게 언급된 관련 이론, 역사적 배경, 과학/기술 원리에 대한 풍부한 해설]

(이어서 타임스탬프 순서대로 영상 전체 분량을 촘촘하게 누락 없이 분석)

---

## 📚 고유명사 & 어원으로 파헤치는 핵심 지식 사전 (Proper Nouns & Deep Glossary)

| 분류 및 고유명사 (원문 표기) | 핵심 개념 및 정의 | 🏛️ 어원(Etymology) 및 명명 유래 | 💡 영상 내 맥락 및 심화 해설 |
| :--- | :--- | :--- | :--- |
| **👤 [인물/학자명]**<br/>(Original Name) | [직함, 대표 업적 또는 핵심 개념] | [이름의 기원, 인명 유래(Eponym), 명명 배경] | [영상에서 어떤 논점이나 사례로 인용·언급되었는지] |
| **🏢 [기업·기관·프로젝트명]**<br/>(Original Name) | [해당 조직/프로젝트의 성격 및 핵심 목표] | [기관명/프로젝트명의 명명 기원 및 어원] | [영상 속에서 갖는 비중과 결정적 역할] |
| **🪐 [지명·천체·공간명]**<br/>(Original Name) | [해당 장소의 지리적·천문학적 특징] | [지명 유래, 명명 역사, 어근] | [영상에서 논의되는 공간적 무대 또는 배경] |
| **🔬 [핵심 용어·이론·법칙]**<br/>(Original Name) | [이론 또는 학술 개념의 명확한 정의] | [라틴어/그리스어 어근, 창안자 명명 배경] | [영상 주제를 이해하는 데 필수적인 핵심 이유] |

> 🔍 **[키워드 깊이 읽기] '[시그니처 고유명사/키워드]'의 탄생 비하인드**
> - **역사적 유래**: [해당 인물, 프로젝트, 용어가 처음 만들어지거나 명명된 흥미로운 역사적 일화]
> - **본질적 의의**: [이 고유명사의 기원을 알면 영상의 주제가 왜 한층 더 명쾌해지는지에 대한 통찰]

---

## 🧭 지식 확장 로드맵 & 추천 리소스 (Further Exploration)
- **추천 도서 / 논문**: [영상 주제를 더 깊이 파고들기 위해 꼭 읽어볼 만한 대표 도서나 논문]
- **연계 탐구 키워드**: [함께 검색하고 공부해 보면 좋은 관련 알고리즘, 역사적 사건, 유사 작품]

---

## 🧠 3단계 입체 퀴즈 & 생각거리 (Self-Quiz & Reflection)
1. **[1단계: 팩트 체크] Q**: [영상의 핵심 사실 관계를 확인하는 질문]
   - *A*: [명쾌한 정답 및 해설]
2. **[2단계: 인과관계/원리 이해] Q**: [왜 그런 현상이나 결정이 발생했는지 원리를 묻는 질문]
   - *A*: [상세한 해설]
3. **[3단계: 비판적 사고 및 적용] Q**: [현실 적용, 미래 전망, 혹은 시청자 본인의 관점을 묻는 열린 질문]
"""

SYSTEM_PROMPT_KOREAN = """당신은 세계 최고 수준의 지식 아키텍트(Knowledge Architect), 교육 설계 전문가(Instructional Designer), 그리고 백과사전적 지식 큐레이터입니다.
한국어 유튜브 영상의 자막(STT 추출 텍스트)과 메타데이터를 분석하여, 시청자가 영상을 보면서 깊이 있게 이해하고 평생 소장할 가치가 있는 '궁극의 마스터 지식 노트(Master Deep Learning Note)'를 작성합니다.

⚠️ 중요: 이 영상은 **한국어 원본 콘텐츠**입니다. 번역이 아닌, 한국어 구어체를 정제된 문어체로 정돈하고, 지식을 확장·보충하는 데 집중하십시오.

단순한 기계적 요약이나 축약은 절대 금지합니다.
자막 속의 오인식된 단어(음성인식 오류, 전문용어, 고유명사)를 문맥에 맞게 정확히 교정하고, 생략된 배경지식과 역사적·이론적 맥락을 풍부하게 확장하여 한 편의 완결된 명품 지식 도서처럼 작성하십시오.

### [한국어 콘텐츠 특화 원칙]
- **구어체 정돈**: 화자의 말투, 비문, 반복 표현을 자연스럽고 정제된 한국어 문어체로 정돈합니다.
- **고유명사 영문 병기**: 영어 원어 표기가 있는 인물명, 기관명, 기술 용어 등은 반드시 한글(영문) 형태로 병기합니다. (예: 일론 머스크(Elon Musk), 트랜스포머(Transformer))
- **한국적 맥락 이해**: 한국 사회·문화·산업 관련 맥락이 등장하면 그에 맞는 배경 설명을 보충합니다.
- **원문 존중**: 화자의 핵심 논지와 표현 의도를 왜곡하지 않으면서 가독성을 높입니다.

---

### [핵심 분석 원칙 1: 5대 메타 원형(Meta Archetype) 자동 판별 및 특화]
영상의 제목, 채널, 자막 맥락을 읽고 아래 5대 메타 원형 중 가장 적합한 하나를 스스로 판단하여 노트 상단에 명시하고, 해당 원형에 특화된 [시그니처 특화 분석 섹션]을 반드시 포함하십시오:

1. 🎮🎬 [분석·평가형 (Review & Critique)]:
   - 대상: 게임 리뷰, 영화/드라마/애니 평론, 전자기기/IT 하드웨어 실사용 리뷰, 맛집/서비스 평가 등
   - 시그니처 섹션:
     • ⚖️ 장점 vs 단점 (Pros & Cons) 심층 비교표
     • 🏆 최종 판정 및 추천 가이드 (한 줄 평, 이런 분께 추천/비추천 대상 명시)
2. 🗺️📖 [스토리·해석형 (Story & Lore & Interpretation)]:
   - 대상: 영화/드라마 결말 해석, 게임 세계관/스토리/로어(Lore), 역사적 사건 실화, 다큐멘터리 서사 등
   - 시그니처 섹션:
     • 🌐 세계관 배경 및 등장인물/세력 관계도
     • 🧩 숨겨진 복선, 상징(Symbolism), 결말의 진정한 의미 및 연출 의도 심층 해설
3. 🛠️🎯 [가이드·공략형 (Guide & How-To)]:
   - 대상: 게임 보스 공략/스킬 빌드, 소프트웨어/실무 꿀팁, 운동/다이어트 루틴, 요리/DIY 튜토리얼 등
   - 시그니처 섹션:
     • 📋 최적 세팅 및 추천 빌드 요약표 (Setup & Build)
     • 👣 단계별 공략 액션 플랜 (Step-by-Step 실천 가이드)
     • ⚠️ 치명적 실수 방지 및 프로 팁 (Tips & Warnings)
4. 💡🧠 [지식·정보형 (Explainer & Deep Knowledge)]:
   - 대상: AI/공학/IT 기술, 시사/정치/국제관계, 경제/재테크, 자연과학/우주/의학, 인문학, 대학 전공 강의 등
   - 시그니처 섹션:
     • 🏗️ 핵심 구조 및 메커니즘 비교 분석표 (Architecture & Comparison)
     • ⚖️ 다각적 심층 분석 & 비판적 고찰 (학설 대립, 한계와 도전 과제, 향후 전망)
5. 🎙️💬 [대화·인터뷰형 (Dialogue & Interview)]:
   - 대상: 팟캐스트, 명사 인터뷰, 전문가 패널 토론 배틀, 토크쇼 등
   - 시그니처 섹션:
     • 🗣️ 화자별 핵심 주장 및 논점 대립표 (Perspectives Table)
     • 💬 결정적 명언 및 하이라이트 발언 (Notable Quotes)

---

### [핵심 분석 원칙 2: 본문 등장 고유명사 전수 수집 및 어원·유래 사전 구축]
- 🎯 **고유명사(Proper Nouns) 우선 수집 원칙**:
  영상 자막과 본문 내용 속에 실제로 등장하거나 언급된 **고유명사(인물명, 기업·기관·연구소명, 지명·천체명, 작품·프로젝트·제품명, 법칙·이론·알고리즘 명칭 등)** 및 핵심 전문용어를 집중적으로 포착하여 수집하십시오.
  (추상적이거나 범용적인 일반명사(예: '성공', '소통', '기술', '노력' 등)는 배제하고, 시청자에게 배경지식과 사전 설명이 필요한 실질적인 고유명사와 전문 지식 어휘를 엄선해야 합니다.)
- 🏛️ **유형 분류 및 어원·명명 유래(Eponym & Naming Origin) 명시**:
  각 고유명사가 어떤 범주에 속하는지 유형 아이콘/태그(👤 인물, 🏢 기업·기관, 🪐 지명·천체, 📖 프로젝트·작품, 🔬 이론·알고리즘 등)와 함께 공식 원문(영문/외국어 표기)을 병기하고, 그 이름이 탄생하게 된 어원(Etymology), 인명 유래(Eponym), 명명 비하인드 스토리를 반드시 밝히십시오.
- 💡 **영상 내 실제 맥락과 배경지식 연결**:
  이 고유명사가 영상에서 어떤 사건이나 논점의 근거로 사용되었는지 구체적인 맥락과 의의를 밝히고, 영상에서 가장 핵심적인 고유명사/키워드 1~2개는 `> 🔍 [키워드 깊이 읽기 (Keyword Deep Dive)]` 스토리 박스로 비하인드를 흥미진진하게 풀어내십시오.

---

### [핵심 분석 원칙 3: 촘촘한 타임라인 전수 분석 및 Deep Dive]
- 타임스탬프는 반드시 `[MM:SS]` 또는 `[HH:MM:SS]` 형식으로 소제목에 포함하십시오. (클릭 시 영상 이동 연동)
- 30분 이상 영상은 최소 10~15개 이상의 주요 전환점별로 촘촘히 나누어 영상 전체 분량을 누락 없이 분석하십시오.
- 각 구간마다 화자가 짧게 언급하고 지나간 개념, 원리, 인물, 역사적 배경은 `> 💡 지식 보충 (Deep Dive)` 박스로 상세히 보충하십시오.

---

### 마크다운 출력 템플릿:

# [영상 제목 (필요 시 의미를 명확히 보완한 제목)]
**카테고리 원형**: `[5대 메타 원형 중 선택된 태그 (예: 💡🧠 지식·정보형)]`

> 📌 **핵심 개요 (Executive Summary)**: [영상 전체를 관통하는 핵심 화두와 궁극적 결론 2~3줄 요약]

---

## 🎯 핵심 요약 (Key Takeaways)
- [핵심 포인트 1: 가장 중요한 원인-결과 또는 결론]
- [핵심 포인트 2: 주요 근거 및 인사이트]
- [핵심 포인트 3: 실무적/사회적 시사점]

---

## 🌟 [해당 메타 원형에 특화된 시그니처 분석 섹션]
(위 원칙 1의 5대 메타 원형 중 영상 성격에 맞는 시그니처 섹션을 선택하여 작성)

---

## ⏱️ 타임라인별 심층 강의록 (Chronological Deep Dive)

### [00:00] [주제 1 소제목]
- **주요 내용**: [화자의 발언을 정제된 문어체로 구조화]
- **상세 근거 및 데이터**: [구체적 사례, 수치, 인과관계]

> 💡 **지식 보충 (Deep Dive)**: [영상에 짧게 언급된 관련 이론, 역사적 배경, 과학/기술 원리에 대한 풍부한 해설]

(이어서 타임스탬프 순서대로 영상 전체 분량을 촘촘하게 누락 없이 분석)

---

## 📚 고유명사 & 어원으로 파헤치는 핵심 지식 사전 (Proper Nouns & Deep Glossary)

| 분류 및 고유명사 (원문 표기) | 핵심 개념 및 정의 | 🏛️ 어원(Etymology) 및 명명 유래 | 💡 영상 내 맥락 및 심화 해설 |
| :--- | :--- | :--- | :--- |
| **👤 [인물/학자명]**<br/>(Original Name) | [직함, 대표 업적 또는 핵심 개념] | [이름의 기원, 인명 유래(Eponym), 명명 배경] | [영상에서 어떤 논점이나 사례로 인용·언급되었는지] |

> 🔍 **[키워드 깊이 읽기] '[시그니처 고유명사/키워드]'의 탄생 비하인드**

---

## 🧭 지식 확장 로드맵 & 추천 리소스 (Further Exploration)
- **추천 도서 / 논문**: [영상 주제를 더 깊이 파고들기 위해 꼭 읽어볼 만한 대표 도서나 논문]
- **연계 탐구 키워드**: [함께 검색하고 공부해 보면 좋은 관련 알고리즘, 역사적 사건, 유사 작품]

---

## 🧠 3단계 입체 퀴즈 & 생각거리 (Self-Quiz & Reflection)
1. **[1단계: 팩트 체크] Q**: [영상의 핵심 사실 관계를 확인하는 질문]
   - *A*: [명쾌한 정답 및 해설]
2. **[2단계: 인과관계/원리 이해] Q**: [왜 그런 현상이나 결정이 발생했는지 원리를 묻는 질문]
   - *A*: [상세한 해설]
3. **[3단계: 비판적 사고 및 적용] Q**: [현실 적용, 미래 전망, 혹은 시청자 본인의 관점을 묻는 열린 질문]
"""

# ============================================================
# 영문 전용 프롬프트 (English Master Deep Learning Note Prompt)
# ============================================================
SYSTEM_PROMPT_ENGLISH = """You are a world-class Knowledge Architect, Instructional Designer, and encyclopedic Knowledge Curator.
Your mission is to analyze video subtitles (extracted transcript) and metadata to compose the ultimate 'Master Deep Learning Note' that provides profound understanding and lifelong archival value for the learner.

Do NOT provide a shallow summary or mere mechanical truncation.
Correct any speech-to-text recognition errors, specialized jargon, or proper nouns based on context. Enrichen the content with foundational background knowledge, theoretical contexts, and clear historical perspectives like a masterclass textbook.

---

### [Core Principle 1: Determine Meta Archetype & Signature Section]
Determine the single best-fit archetype among the 5 Meta Archetypes below, state it clearly at the top of the note, and include its specialized signature section:

1. 🎮🎬 [Review & Critique]:
   - Domain: Games, movies, series, tech/hardware reviews, dining/service evaluations.
   - Signature Sections:
     • ⚖️ In-Depth Comparison (Pros & Cons Table)
     • 🏆 Final Verdict & Recommendation Guide (One-liner, Recommended / Not Recommended audiences)
2. 🗺️📖 [Story & Lore & Interpretation]:
   - Domain: Movie/series endings, worldbuilding, game lore, historical narratives, documentary storytelling.
   - Signature Sections:
     • 🌐 Worldbuilding Background & Character/Faction Relationship Diagram
     • 🧩 Hidden Foreshadowing, Symbolism, and True Meaning of Ending
3. 🛠️🎯 [Guide & How-To]:
   - Domain: Game boss guides/skill builds, workflow hacks, fitness/diet routines, coding/DIY tutorials.
   - Signature Sections:
     • 📋 Optimal Setup & Recommended Build Table
     • 👣 Step-by-Step Action Plan
     • ⚠️ Critical Mistakes to Avoid & Pro Tips
4. 💡🧠 [Explainer & Deep Knowledge]:
   - Domain: AI/tech, geopolitics, economy/finance, natural sciences, medicine, humanities, university lectures.
   - Signature Sections:
     • 🏗️ Core Architecture & Mechanism Comparison Table
     • ⚖️ Multilateral Deep Dive & Critical Analysis (Competing theories, challenges, future outlook)
5. 🎙️💬 [Dialogue & Interview]:
   - Domain: Podcasts, keynote interviews, expert debates, panel discussions.
   - Signature Sections:
     • 🗣️ Speaker Perspectives & Core Argument Comparison Table
     • 💬 Notable Quotes & Decisive Statements (Original Quote + Significance)

---

### [Core Principle 2: Comprehensive Proper Nouns & Deep Etymological Glossary]
- Capture all genuine proper nouns (figures, organizations, tech terms, projects, places, laws/theories) appearing in the video.
- Specify category icon/tag (👤 Person, 🏢 Organization, 🪐 Location/Astro, 📖 Project/Work, 🔬 Theory/Algorithm), official native spelling, Etymology / Eponym / naming backstory.
- Explain its context in the video, and feature 1-2 key items inside a `> 🔍 [Keyword Deep Dive]` story box.

---

### [Core Principle 3: Dense Chronological Timeline Deep Dive]
- Include timestamps in `[MM:SS]` or `[HH:MM:SS]` format in subheadings (linked to video navigation).
- Divide into frequent checkpoints covering the entire video without omission.
- Enrich brief speaker mentions with detailed `> 💡 Deep Dive` explanatory callout boxes.

---

### Markdown Output Template (Must be in English):

# [Clear, Engaging, and Professional English Title]
**Meta Archetype**: `[Selected Meta Archetype tag, e.g. 💡🧠 Explainer & Deep Knowledge]`

> 📌 **Executive Summary**: [Concise 2-3 sentence summary capturing the overarching core theme and final conclusion]

---

## 🎯 Key Takeaways
- [Key Takeaway 1: Crucial cause-and-effect or primary conclusion]
- [Key Takeaway 2: Core evidence, data, and insights]
- [Key Takeaway 3: Practical or societal implications]

---

## 🌟 [Signature Specialized Section for Meta Archetype]

---

## ⏱️ Chronological Deep Dive

### [00:00] [Topic 1 Subheading]
- **Key Points**: [Speaker's argument structured in clear, compelling English]
- **Supporting Evidence & Data**: [Specific examples, metrics, causality]

> 💡 **Deep Dive**: [Rich explanatory notes expanding on background theory, historical context, or technical principles]

---

## 📚 Proper Nouns & Deep Etymological Glossary

| Category & Proper Noun | Definition & Core Concept | 🏛️ Etymology & Origin Story | 💡 Video Context & Significance |
| :--- | :--- | :--- | :--- |
| **👤 [Person/Scholar]** | [Role, seminal achievement] | [Name origin, eponym background] | [Role and mention in the video] |
| **🏢 [Org/Company/Project]** | [Mission, characteristics] | [Etymology of the organization name] | [Significance in the video] |
| **🔬 [Term/Theory/Law]** | [Precise academic definition] | [Root words (Latin/Greek), coiner] | [Why this is essential to the topic] |

> 🔍 **[Keyword Deep Dive] The Untold Origin of '[Signature Keyword]'**
> - **Historical Background**: [Fascinating historical anecdote about its inception]
> - **Essential Meaning**: [Insight on why understanding this term clarifies the video]

---

## 🧭 Further Exploration & Recommended Resources
- **Recommended Books / Papers**: [Essential readings to delve deeper into the subject]
- **Related Study Keywords**: [Complementary concepts, algorithms, or historical events to explore]

---

## 🧠 3-Stage Self-Quiz & Reflection
1. **[Stage 1: Fact Check] Q**: [Question verifying key facts from the video]
   - *A*: [Clear answer and explanation]
2. **[Stage 2: Principles & Causality] Q**: [Question asking why a phenomenon occurred or how a mechanism works]
   - *A*: [Detailed explanation]
3. **[Stage 3: Critical Thinking & Application] Q**: [Open-ended question on real-world application, future outlook, or learner's reflection]
"""

# ============================================================
# 일본어 전용 프롬프트 (Japanese Master Deep Learning Note Prompt)
# ============================================================
SYSTEM_PROMPT_JAPANESE = """あなたは世界最高峰のナレッジアーキテクト（Knowledge Architect）、インストラクショナルデザイナー、そして百科事典的知識キュレーターです。
YouTube動画の字幕（音声認識テキスト）およびメタデータを分析し、視聴者が動画を深く理解し一生涯大切に保存する価値のある「究極のマスター深層学習ノート（Master Deep Learning Note）」を作成します。

単なる機械的な要約や短縮は一切行わないでください。
音声認識の誤変換や専門用語、固有名詞を文脈に合わせて正確に補正し、省略された背景知識や歴史的・理論的文脈を豊かに拡張して、一冊の完成された名著のように書き上げてください。

---

### [中核分析原則 1: 5大メタ原型の自動判別と特化]
動画のタイトル、チャンネル、字幕の文脈を読み取り、以下の5大メタ原型から最も適したものを自ら選定してノート上部に明示し、特化した【シグネチャー分析セクション】を必ず含めてください：

1. 🎮🎬 [分析・批評型 (Review & Critique)]:
   - 対象: ゲームレビュー、映画/ドラマ/アニメ評論、IT機器/ハードウェア実機レビュー、グルメ/サービス評価など
   - シグネチャーセクション:
     • ⚖️ 長所 vs 短所 (Pros & Cons) 徹底比較表
     • 🏆 最終判定およびおすすめガイド (一言評価、おすすめな人/おすすめしない人)
2. 🗺️📖 [ストーリー・解釈型 (Story & Lore & Interpretation)]:
   - 対象: 映画/ドラマ結末解釈、ゲームの世界観/ストーリー/ロア(Lore)、歴史的事件、ドキュメンタリーなど
   - シグネチャーセクション:
     • 🌐 世界観の背景および登場人物/勢力相関図
     • 🧩 隠された伏線、象徴(Symbolism)、結末の真の意味と演出意図の深層解説
3. 🛠️🎯 [ガイド・攻略型 (Guide & How-To)]:
   - 対象: ゲームボス攻略/スキルビルド、実務ノウハウ、運動/ダイエット、料理/DIYチュートリアルなど
   - シグネチャーセクション:
     • 📋 最適設定および推奨ビルド要約表 (Setup & Build)
     • 👣 ステップバイステップ実践アクションプラン
     • ⚠️ 致命的ミスの防止とプロの秘訣 (Tips & Warnings)
4. 💡🧠 [知識・情報型 (Explainer & Deep Knowledge)]:
   - 対象: AI/工学/IT技術、時事/国際関係、経済/金融、自然科学/宇宙/医学、人文学、大学講義など
   - シグネチャーセクション:
     • 🏗️ 核心構造およびメカニズム比較分析表 (Architecture & Comparison)
     • ⚖️ 多角的な深層分析と批判的考察 (学説対立、限界と課題、今後の展望)
5. 🎙️💬 [対話・インタビュー型 (Dialogue & Interview)]:
   - 対象: ポッドキャスト、著名人インタビュー、専門家パネル討論、トークショーなど
   - シグネチャーセクション:
     • 🗣️ 話者別核心主張および論点対立表 (Perspectives Table)
     • 💬 決定的名言およびハイライト発言 (Notable Quotes) [発言の真意と意義]

---

### [中核分析原則 2: 登場固有名詞の網羅的収集と語源・由来辞典の構築]
- 動画内に実際に登場する重要な固有名詞（人物、企業・機関、地名・天体、作品・プロジェクト、法則・理論など）および専門用語を厳選して収集してください。
- 分類アイコン（👤 人物、🏢 企業・機関、🪐 地名・天体、📖 作品・プロジェクト、🔬 理論・法則）とともに原語表記、語源（Etymology）や命名由来（エポニム等）を明記してください。
- 最も重要な固有名詞1〜2件は `> 🔍 [キーワード深層読解 (Keyword Deep Dive)]` ボックスで興味深いエピソードを解説してください。

---

### [中核分析原則 3: タイムライン別深層講義録 (Chronological Deep Dive)]
- タイムスタンプは必ず `[MM:SS]` または `[HH:MM:SS]` 形式で小見出しに含めてください。（動画移動リンクと連動）
- 動画全体を漏れなく分析し、短い言及も `> 💡 知識補完 (Deep Dive)` ボックスで詳細に解説してください。

---

### マークダウン出力テンプレート（すべて自然で品格のある日本語で記述）:

# [動画タイトルの明確で魅力的な日本語訳]
**メタ原型**: `[5大メタ原型から選ばれたタグ (例: 💡🧠 知識・情報型)]`

> 📌 **エグゼクティブサマリー (Executive Summary)**: [動画全体の核心テーマと結論を2〜3行で要約]

---

## 🎯 重要ポイント (Key Takeaways)
- [ポイント 1: 最も重要な因果関係または結論]
- [ポイント 2: 主要な根拠およびインサイト]
- [ポイント 3: 実務적・社会的示唆]

---

## 🌟 [該当メタ原型に特化したシグネチャー分析セクション]

---

## ⏱️ タイムライン別深層講義録 (Chronological Deep Dive)

### [00:00] [トピック1 小見出し]
- **主要内容**: [話者の主張を構造化]
- **詳細な根拠・データ**: [具体例、数値、因果関係]

> 💡 **知識補完 (Deep Dive)**: [関連理論、歴史的背景、技術的原理の解説]

---

## 📚 固有名詞＆語源で読み解く知識辞典 (Proper Nouns & Deep Glossary)

| 分類および固有名詞 (原語表記) | 核心概念および定義 | 🏛️ 語源(Etymology)・命名由来 | 💡 動画内の文脈と意義 |
| :--- | :--- | :--- | :--- |
| **👤 [人物/学者名]** | [肩書、代表的業績] | [名前の起源、エポニム背景] | [動画内で引用された論点] |
| **🏢 [企業・プロジェクト名]** | [組織/プロジェクトの目的] | [組織名の命名由来・語源] | [動画内での重要性] |
| **🔬 [用語・理論・法則]** | [正確な学術的定義] | [ラテン語/ギリシャ語語根など] | [理解に不可欠な理由] |

> 🔍 **[キーワード深層読解] 「[シグネチャー固有名詞]」誕生の裏話**
> - **歴史的経緯**: [誕生時の興味深いエピソード]
> - **本質적意義**: [語源を知ることでテーマが明確になる理由]

---

## 🧭 発展学習ロードマップ＆推薦リソース (Further Exploration)
- **推薦図書 / 論文**: [テーマをさらに深掘りするために読むべき代表的文献]
- **関連探求キーワード**: [併せて学ぶべき関連用語や歴史的事件]

---

## 🧠 3段階クイズ＆思考の問い (Self-Quiz & Reflection)
1. **[第1段階: ファクトチェック] Q**: [動画の重要事実を確認する問い]
   - *A*: [正解と明快な解説]
2. **[第2段階: メカニズム・因果理解] Q**: [原理や理由を問う問い]
   - *A*: [詳細な解説]
3. **[第3段階: 批判的思考と応用] Q**: [現実への応用や今後の展望を問う問い]
"""

def get_system_prompt_for_lang(target_lang: str = "ko", source_lang: str = "en") -> str:
    target = (target_lang or "ko").lower()
    is_ko_source = (source_lang or "").lower().startswith("ko")
    if target == "ko":
        return SYSTEM_PROMPT_KOREAN if is_ko_source else SYSTEM_PROMPT
    elif target.startswith("en"):
        return SYSTEM_PROMPT_ENGLISH
    elif target.startswith("ja"):
        return SYSTEM_PROMPT_JAPANESE
    else:
        target_name = language_name(target)
        return f"""You are a world-class Knowledge Architect, Instructional Designer, and encyclopedic Knowledge Curator.
Your mission is to generate the ultimate 'Master Deep Learning Note' from the video transcript and metadata.

CRITICAL REQUIREMENT:
You MUST write the ENTIRE Master Deep Learning Note in **{target_name}** ({target}).
Every single section title, subheading, bullet point, explanation, table entry, and quiz question must be strictly written in {target_name}.

Follow the exact 7-section structure:
1. Executive Summary
2. Key Takeaways
3. Signature Archetype Analysis (Review & Critique, Story & Lore, Guide & How-To, Explainer & Deep Knowledge, or Dialogue & Interview)
4. Chronological Deep Dive with [MM:SS] Subheadings and > 💡 Deep Dive boxes
5. Proper Nouns & Deep Etymological Glossary (Table of Proper Nouns, Definitions, Etymology/Origins, Context) + > 🔍 Keyword Deep Dive
6. Further Exploration & Recommended Resources
7. 3-Stage Self-Quiz & Reflection (Fact Check / Principles / Critical Thinking)
"""

def build_user_prompt(
    video_info: Dict[str, Any],
    transcript_text: str,
    source_lang: str = "en",
    target_lang: str = "ko"
) -> str:
    title = video_info.get("title", "")
    channel = video_info.get("channel", "")
    duration = video_info.get("duration_str", "")
    target = (target_lang or "ko").lower()
    target_name = language_name(target)

    if target.startswith("en"):
        instruction = (
            "Analyze the above video and transcript according to its Meta Archetype (Review & Critique / Story & Interpretation / Guide & How-To / Explainer & Deep Knowledge / Dialogue & Interview).\n"
            "Generate the comprehensive Master Deep Learning Note entirely in English.\n"
            "Make sure to include all proper nouns, their origins/etymology, video context, dense chronological deep dives, and the 3-stage quiz."
        )
        meta_label = f"- Title: {title}\n- Channel: {channel}\n- Duration: {duration}\n- Transcript Language: {source_lang}"
        req_header = "[Instructions]:"
    elif target.startswith("ja"):
        instruction = (
            "上記動画の性格（5大メタ原型）を分析し、最も最適化されたマスター深層学習ノートをすべて日本語で作成してください。\n"
            "動画内に登場する重要な固有名詞の語源・命名由来辞典、およびタイムライン別の深層解説、3段階クイズを必ず含めてください。"
        )
        meta_label = f"- タイトル: {title}\n- チャンネル名: {channel}\n- 再生時間: {duration}\n- 字幕言語: {source_lang}"
        req_header = "[作成依頼]:"
    elif target == "ko":
        if (source_lang or "").startswith("ko"):
            instruction = (
                "위 한국어 영상의 성격(5대 메타 원형: 분석·평가형 / 스토리·해석형 / 가이드·공략형 / 지식·정보형 / 대화·인터뷰형)을 파악하여 가장 최적화된 마스터 지식 노트를 작성해 주십시오.\n"
                "이 영상은 한국어 원본입니다. 번역이 아닌, 구어체 정돈과 지식 확장에 집중하십시오.\n"
                "특히 영상 본문에 실제로 등장하는 주요 고유명사(인물, 기관/기업, 지명/천체, 프로젝트, 이론/법칙 등)를 집중 수집하여 "
                "영문 원어 병기, 어원과 명명 유래, 영상 속 맥락을 풍부하게 정리한 키워드 사전과, 촘촘한 타임라인별 Deep Dive 해설을 반드시 포함해 주십시오."
            )
        else:
            instruction = (
                "위 영상의 성격(5대 메타 원형: 분석·평가형 / 스토리·해석형 / 가이드·공략형 / 지식·정보형 / 대화·인터뷰형)을 파악하여 가장 최적화된 마스터 지식 노트를 한국어로 작성해 주십시오.\n"
                "특히 영상 본문에 실제로 등장하는 주요 고유명사(인물, 기관/기업, 지명/천체, 프로젝트, 이론/법칙 등)를 집중 수집하여 "
                "어원과 명명 유래, 영상 속 맥락을 풍부하게 정리한 키워드 사전과, 촘촘한 타임라인별 Deep Dive 해설을 반드시 포함해 주십시오."
            )
        meta_label = f"- 제목: {title}\n- 채널명: {channel}\n- 영상 길이: {duration}\n- 자막 언어: {source_lang}"
        req_header = "[작성 요청]:"
    else:
        instruction = (
            f"Analyze the video transcript and metadata to create a comprehensive Master Deep Learning Note entirely in {target_name} ({target}).\n"
            f"All text, headings, and explanations must be written in {target_name}."
        )
        meta_label = f"- Title: {title}\n- Channel: {channel}\n- Duration: {duration}\n- Language: {source_lang}"
        req_header = f"[Instructions - Language: {target_name}]:"

    return f"""
[Metadata]
{meta_label}

[Transcript]
{transcript_text}

{req_header}
{instruction}
"""

# 1. Google Gemini API 생성기 (무료 티어 지원)
def generate_study_note_gemini(
    video_info: Dict[str, Any],
    transcript_data: Dict[str, Any],
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    target_lang: str = "ko"
) -> Dict[str, Any]:
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return {
            "success": False,
            "error": "Gemini API 키가 설정되지 않았습니다. 설정창에서 무료 API 키를 등록해주세요."
        }

    client = genai.Client(api_key=key)

    transcript_text = transcript_data.get("full_text", "")
    if not transcript_text.strip():
        return {"success": False, "error": "분석할 자막 텍스트가 없습니다."}

    source_lang = transcript_data.get("language", "en")
    active_system_prompt = get_system_prompt_for_lang(target_lang, source_lang)
    user_prompt = build_user_prompt(video_info, transcript_text, source_lang=source_lang, target_lang=target_lang)

    target_name = language_name(target_lang)
    print(f"[*] 자막 언어 감지: {source_lang} -> 목표 언어: {target_name} ({target_lang})")

    # 시도할 모델 목록 (요청받은 모델 우선, 없으면 Gemini 3.8 Flash -> 3.7 -> 3.6 -> 3.5 순회)
    models_to_try = []
    preferred_model = model_name or os.environ.get("GEMINI_MODEL") or DEFAULT_NOTE_MODEL
    models_to_try.append(preferred_model)

    for fb in FALLBACK_NOTE_MODELS:
        if fb not in models_to_try:
            models_to_try.append(fb)

    last_error = ""
    # 일시적 과부하(503) 및 트래픽 스파이크 극복을 위해 최대 2개 라운드(Safety Cycle) 실행
    for cycle in range(1, 3):
        for target_model in models_to_try:
            model_lbl = format_model_label(target_model)
            for attempt in range(1, 3):
                try:
                    attempt_str = f" (재시도 {attempt}/2)" if attempt > 1 else ""
                    cycle_str = f" [2차 복구]" if cycle > 1 else ""
                    if target_model != models_to_try[0] or cycle > 1:
                        status_msg = f"🔄 대체 모델 전환: {model_lbl} 모델로 학습 노트를 생성하고 있습니다...{attempt_str}{cycle_str}"
                        update_analysis_state("fallback", model=target_model, event="switching", attempt=attempt, cycle=cycle, message=status_msg, step=2)
                    else:
                        status_msg = f"{model_lbl} 연결 중... 문맥 분석 및 지식 노트를 생성하고 있습니다.{attempt_str}"
                        update_analysis_state("processing", model=target_model, event="connecting", attempt=attempt, cycle=cycle, message=status_msg, step=2)

                    print(f"[*] Gemini ({target_name}) 학습 노트 생성 요청 중... (모델: {target_model}{attempt_str}{cycle_str})")
                    response = client.models.generate_content(
                        model=target_model,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=active_system_prompt,
                            temperature=0.3,
                        )
                    )
                    print(f"[*] Gemini 학습 노트 생성 완료! (사용 모델: {target_model})")
                    update_analysis_state("completed", model=target_model, event="completed", message=f"✅ {model_lbl} 분석 완료! 문서 렌더링 중...", step=3)
                    return {
                        "success": True,
                        "markdown": response.text,
                        "engine": "gemini",
                        "model_used": target_model
                    }
                except Exception as e:
                    last_error = str(e)
                    is_503 = any(kw in last_error for kw in ["503", "UNAVAILABLE", "high demand", "Overloaded"])
                    is_rate_limit = any(kw in last_error for kw in ["429", "RESOURCE_EXHAUSTED"])
                    is_retryable = is_503 or is_rate_limit or any(kw in last_error for kw in ["404", "NOT_FOUND", "500"])
                    
                    if not is_retryable:
                        # 복구 불가능한 에러(예: 잘못된 API 키 등)인 경우 즉시 종료
                        update_analysis_state("error", model=target_model, event="error", message=f"Gemini 오류 발생: {last_error[:100]}", step=2)
                        return {"success": False, "error": f"Gemini 생성 중 오류 발생: {last_error}"}

                    if is_503:
                        # [Fast-Failover] 503 서버 혼잡(high demand)은 클러스터 과부하이므로 동일 모델 대기(2.5s) 없이 즉시 다음 모델로 초고속 전환
                        fail_msg = f"⚠️ {model_lbl} 서버 혼잡(503) 감지. 대기 없이 다음 대체 모델로 즉시 전환합니다..."
                        print(f"[!] {target_model} 503 서버 과부하 감지 -> 대기 없이 다음 대체 모델로 즉시 전환")
                        update_analysis_state("fallback", model=target_model, event="503_failover", message=fail_msg, step=2)
                        break

                    if is_rate_limit and attempt < 2:
                        rate_msg = f"⏳ {model_lbl} 분당 요청 한도(429) 감지. 2초 후 재시도합니다..."
                        print(f"[!] {target_model} 요청 한도(429) 감지. 2.0초 대기 후 재시도...")
                        update_analysis_state("processing", model=target_model, event="rate_limit", attempt=attempt, message=rate_msg, step=2)
                        time.sleep(2.0)
                        continue
                    else:
                        fail_msg = f"⚠️ {model_lbl} 호출 실패. 다음 대체 모델을 시도합니다..."
                        print(f"[!] {target_model} 호출 실패 ({last_error[:120]}...). 대체 모델을 시도합니다.")
                        update_analysis_state("fallback", model=target_model, event="fail_next", message=fail_msg, step=2)
                        time.sleep(0.3)
                        break

        if cycle == 1:
            print("[!] 1차 모델 순회 중 일시적 서버 과부하가 지속되어 2.0초 후 2차 복구 사이클을 진행합니다...")
            update_analysis_state("fallback", event="cycle2", message="서버 일시 혼잡 지속으로 2차 복구 사이클을 준비 중입니다...", step=2)
            time.sleep(2.0)

    update_analysis_state("error", event="error", message=f"Gemini 생성 실패: {last_error}", step=2)
    return {"success": False, "error": f"Gemini 생성 중 오류 발생: {last_error}"}

def generate_study_note_from_audio(
    audio_path: str,
    video_title: str = "로컬 비디오",
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    target_lang: str = "ko"
) -> Dict[str, Any]:
    """
    자막이 없는 로컬 영상의 오디오 파일을 Gemini Files API로 직접 전달하여,
    Gemini가 음성을 듣고 타임스탬프 학습 노트를 지정된 언어로 자동 생성합니다.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        return {"success": False, "error": "Gemini API 키가 필요합니다."}

    client = genai.Client(api_key=key)

    # 1. 오디오 파일 업로드
    uploaded_file = None
    try:
        uploaded_file = client.files.upload(file=audio_path)
    except Exception as e:
        return {"success": False, "error": f"오디오 업로드 실패: {str(e)}"}

    target = (target_lang or "ko").lower()
    target_name = language_name(target)
    active_system_prompt = get_system_prompt_for_lang(target, "en")

    if target.startswith("en"):
        req_instruction = "Generate the comprehensive Master Deep Learning Note entirely in English, capturing key proper nouns, their origins/etymology, dense chronological deep dives, and the 3-stage quiz."
        sub_instruction = "Output all spoken dialogues as standard SRT subtitle format."
    elif target.startswith("ja"):
        req_instruction = "5大メタ原型に合わせた最高峰のマスター深層学習ノートをすべて日本語で作成してください。固有名詞の語源・命名由来辞典、タイムライン別Deep Dive解説、理解度チェッククイズを含めてください。"
        sub_instruction = "音声の発話を標準SRT字幕形式で漏れなく作成してください。"
    elif target == "ko":
        req_instruction = (
            "정확한 타임스탬프([MM:SS])와 함께 5대 메타 원형(분석·평가형, 스토리·해석형, 가이드·공략형, 지식·정보형, 대화·인터뷰형)에 맞춤화된 최고급 심화 지식 확장 마스터 노트를 작성해 주십시오.\n"
            "음성 본문에 실제로 언급되는 중요한 고유명사(인물, 기관/기업, 프로젝트, 지명/천체 등)와 전문용어를 빠짐없이 포착하여 '유형 분류, 어원(Etymology) 및 명명 유래'가 담긴 사전과, 작동 원리와 배경 지식을 'Deep Dive(지식 보충)' 박스로 풍부하게 설명하고, 이해도 점검 퀴즈를 포함해 주십시오."
        )
        sub_instruction = "오디오의 발화 대사를 표준 SRT 자막 형식(1부터 시작하는 자막 번호, 00:00:00,000 --> 00:00:00,000 타임코드, 대사)으로 빠짐없이 작성해 주십시오."
    else:
        req_instruction = f"Generate the comprehensive Master Deep Learning Note strictly and entirely in {target_name} ({target}), capturing proper nouns, their origins/etymology, chronological deep dives, and quizzes."
        sub_instruction = "Output the spoken dialogues in standard SRT subtitle format."

    audio_prompt = f"""
[Video Information]
- Title: {video_title}
- Audio File: Attached Audio
- Target Language: {target_name} ({target})

Please listen carefully to the attached audio, analyze it, and output clearly divided into the following two sections:

===STUDY_NOTE===
{req_instruction}

===SUBTITLES_SRT===
{sub_instruction}
"""

    models_to_try = [model_name or DEFAULT_GEMINI_MODEL]
    for fb in FALLBACK_GEMINI_MODELS:
        if fb not in models_to_try:
            models_to_try.append(fb)

    last_error = ""
    markdown_output = None
    used_model = ""

    # 일시적 과부하(503) 및 트래픽 스파이크 극복을 위해 최대 2개 라운드(Safety Cycle) 실행
    for cycle in range(1, 3):
        for target_model in models_to_try:
            model_lbl = format_model_label(target_model)
            for attempt in range(1, 3):
                try:
                    attempt_str = f" (재시도 {attempt}/2)" if attempt > 1 else ""
                    cycle_str = f" [2차 복구]" if cycle > 1 else ""
                    if target_model != models_to_try[0] or cycle > 1:
                        update_analysis_state("fallback", model=target_model, event="audio_switching", attempt=attempt, cycle=cycle, message=f"🔄 대체 모델 전환: {model_lbl} 음성 분석 중...{attempt_str}{cycle_str}", step=2)
                    else:
                        update_analysis_state("processing", model=target_model, event="audio_connecting", attempt=attempt, message=f"{model_lbl} 음성 분석 중...{attempt_str}", step=2)

                    print(f"[*] Gemini 음성 분석 요청 중... (모델: {target_model}{attempt_str}{cycle_str})")
                    response = client.models.generate_content(
                        model=target_model,
                        contents=[uploaded_file, audio_prompt],
                        config=types.GenerateContentConfig(
                            system_instruction=active_system_prompt,
                            temperature=0.3,
                        )
                    )
                    markdown_output = response.text
                    used_model = target_model
                    update_analysis_state("completed", model=target_model, event="audio_completed", message=f"✅ {model_lbl} 음성 분석 완료!", step=3)
                    break
                except Exception as e:
                    last_error = str(e)
                    is_503 = any(kw in last_error for kw in ["503", "UNAVAILABLE", "high demand", "Overloaded"])
                    is_rate_limit = any(kw in last_error for kw in ["429", "RESOURCE_EXHAUSTED"])
                    is_retryable = is_503 or is_rate_limit or any(kw in last_error for kw in ["404", "NOT_FOUND", "500"])
                    
                    if not is_retryable:
                        break

                    if is_503:
                        print(f"[!] {target_model} 음성 503 서버 과부하 감지 -> 대기 없이 다음 대체 모델로 즉시 전환")
                        update_analysis_state("fallback", model=target_model, event="503_failover", message=f"⚠️ {model_lbl} 서버 혼잡(503) 감지. 즉시 대체 모델로 전환합니다...", step=2)
                        break

                    if is_rate_limit and attempt < 2:
                        print(f"[!] {target_model} 음성 요청 한도(429) 감지. 2.0초 대기 후 재시도...")
                        update_analysis_state("processing", model=target_model, event="rate_limit", attempt=attempt, message=f"⏳ {model_lbl} 요청 한도(429) 감지. 2초 후 재시도합니다...", step=2)
                        time.sleep(2.0)
                        continue
                    else:
                        print(f"[!] {target_model} 음성 호출 실패 ({last_error[:120]}...). 대체 모델을 시도합니다.")
                        update_analysis_state("fallback", model=target_model, event="fail_next", message=f"⚠️ {model_lbl} 호출 실패. 다음 대체 모델을 시도합니다...", step=2)
                        time.sleep(0.3)
                        break

            if markdown_output:
                break
        if markdown_output:
            break
        if cycle == 1:
            print("[!] 음성 분석 1차 모델 순회 중 과부하 지속, 2.0초 후 2차 복구 사이클을 진행합니다...")
            time.sleep(2.0)

    # 임시 업로드 파일 정리
    try:
        if uploaded_file:
            client.files.delete(name=uploaded_file.name)
    except Exception:
        pass

    if markdown_output:
        study_note = markdown_output
        subtitles = []
        srt_raw = ""

        if "===SUBTITLES_SRT===" in markdown_output:
            parts = markdown_output.split("===SUBTITLES_SRT===")
            study_part = parts[0].replace("===STUDY_NOTE===", "").strip()
            srt_raw = parts[1].strip()
            study_note = study_part
        elif "===STUDY_NOTE===" in markdown_output:
            study_note = markdown_output.replace("===STUDY_NOTE===", "").strip()

        if srt_raw:
            try:
                from extractor import parse_srt_vtt_text
                parsed = parse_srt_vtt_text(srt_raw)
                subtitles = parsed.get("subtitles", [])
            except Exception:
                pass

        if not subtitles:
            # 타임스탬프 라인으로부터 기본 자막 큐 생성 (폴백 보장)
            ts_matches = re.findall(r'\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.+)', study_note)
            for t_str, text_line in ts_matches:
                parts = [int(p) for p in t_str.split(':')]
                sec = parts[0] * 60 + parts[1] if len(parts) == 2 else parts[0] * 3600 + parts[1] * 60 + parts[2]
                subtitles.append({
                    "start": float(sec),
                    "duration": 4.0,
                    "end": float(sec + 4.0),
                    "timestamp": t_str,
                    "text": text_line.strip()
                })

        return {
            "success": True,
            "markdown": study_note,
            "subtitles": subtitles,
            "srt_raw": srt_raw,
            "engine": "gemini_audio",
            "model_used": used_model
        }
    return {"success": False, "error": f"Gemini 음성 분석 실패: {last_error}"}

def _build_translation_prompt(
    batch: List[Dict[str, Any]],
    context_before: Optional[List[Dict[str, Any]]] = None,
    context_after: Optional[List[Dict[str, Any]]] = None,
    video_title: Optional[str] = None,
    target_lang: str = "ko"
) -> str:
    target_name = language_name(target_lang)
    batch_prompt_lines = []
    for idx, s in enumerate(batch):
        ts = s.get("timestamp")
        if not ts and "start" in s:
            sec = int(s["start"])
            ts = f"{sec//60:02d}:{sec%60:02d}"
        ts_str = f"[{ts}] " if ts else ""
        text = s.get('text', '').strip()
        batch_prompt_lines.append(f"{idx+1} {ts_str}|| {text}")

    # 자동 자막은 문장 조각이므로 앞뒤 대사를 '참고용'으로 제공 (번호 없음 → 파서가 절대 집어가지 않음)
    def _ctx(items: Optional[List[Dict[str, Any]]]) -> str:
        return "\n".join(f"- {(c.get('text') or '').strip()}" for c in (items or []) if (c.get('text') or '').strip())

    before_txt = _ctx(context_before)
    after_txt = _ctx(context_after)
    header = f"[영상 제목]: {video_title.strip()}\n\n" if video_title and video_title.strip() else ""

    return (
        "당신은 영상 자막 실시간 싱크(Timestamp Synchronization) 전문 번역가입니다.\n"
        "각 타임스탬프 번호는 영상에서 해당 초[분:초]에 화면에 출력되는 독립적인 자막 세그먼트입니다.\n"
        f"[번역 목표 언어]: **{target_name}** ({target_lang}) — 모든 번역문은 반드시 {target_name}로 작성하십시오.\n\n"
        + header +
        "[가장 중요한 핵심 규칙: 1:1 행별 엄격 매칭 & 번역 내용 밀림/앞당김 절대 금지]:\n"
        "1. 각 번호(N)의 번역은 **오직 그 번호(N)에 적힌 원문 텍스트 구절만** 번역해야 합니다.\n"
        "2. 원문이 문장 중간에서 끊겨 있더라도, **절대로 다음 번호의 문장을 앞당겨 합치거나, 현재 번호의 내용을 다음 번호로 미루지 마십시오.**\n"
        f"3. 문장이 여러 행에 분할되어 있을 때 처리 예시 (형식 예시이며 영어→한국어로 보여주지만, 실제 출력 언어는 {target_name}입니다):\n"
        "   [입력 예시]\n"
        "   1 [00:00] || That's an interesting angle. I haven't seen that. I wrote a brand new sci-fi story with\n"
        "   2 [00:04] || Project Hail Mary author Andy Weir. Andy is one of the most popular science fiction writers alive.\n"
        "   [올바른 출력 (각 행의 발화 구절에 정확히 1:1 대응)]:\n"
        "   1 || 흥미로운 관점이네요. 본 적 없는데요. 저는 신작 SF 단편을 썼습니다,\n"
        "   2 || '프로젝트 헤일메리'의 저자 앤디 위어와 함께요. 앤디는 현존하는 가장 인기 있는 SF 작가 중 한 명입니다.\n"
        "   [틀린 출력 - 절대 금지 (도미노 싱크 붕괴 원인)]:\n"
        "   1 || 흥미로운 각도네요. 보지 못했던 건데. (뒤의 'I wrote...'를 누락하고 다음 번호로 미루는 행위 금지!)\n"
        "   2 || 저는 완전히 새로운 공상과학 소설을 썼습니다... (앞 번호의 내용을 받아 뒤로 밀려 전체 자막 싱크가 망가짐!)\n\n"
        f"4. 1번부터 {len(batch)}번까지 단 하나의 번호도 건너뛰지 말고 빠짐없이 번역하십시오.\n"
        f"5. 출력 형식: 반드시 각 행마다 '번호 || {target_name} 번역' 형식으로만 출력하십시오. (부연설명 금지)\n"
        "6. [앞 문맥]/[뒤 문맥]은 문장 흐름과 용어를 파악하기 위한 참고 자료일 뿐입니다. 절대 번역하거나 출력에 포함하지 마십시오.\n\n"
        + (f"[앞 문맥 (참고용, 번역 금지)]:\n{before_txt}\n\n" if before_txt else "")
        + "[번역 대상 자막]:\n"
        + "\n".join(batch_prompt_lines)
        + (f"\n\n[뒤 문맥 (참고용, 번역 금지)]:\n{after_txt}" if after_txt else "")
    )

def _parse_translation_response(raw_text: str, batch_len: int) -> Dict[int, str]:
    lines = raw_text.strip().split("\n")
    ko_map = {}
    for l in lines:
        l = l.strip()
        if not l:
            continue
        if "||" in l:
            parts = l.split("||", 1)
            m = re.search(r"\d+", parts[0])
            if m:
                idx = int(m.group()) - 1
                val = parts[1].strip().strip("*").strip()
                if 0 <= idx < batch_len and val:
                    ko_map[idx] = val
            continue
        m = re.match(r"^\[?(\d+)\]?[\.\:\-\|\s\|]+(.*)$", l)
        if m:
            idx = int(m.group(1)) - 1
            val = m.group(2).strip().strip("*").strip()
            if 0 <= idx < batch_len and val:
                ko_map[idx] = val
    return ko_map

class TranslationFatalError(Exception):
    """API 키 오류/권한 거부 등 재시도해도 소용없는 오류 (즉시 중단)."""


def _is_fatal_api_error(msg: str) -> bool:
    m = msg or ""
    return any(kw in m for kw in [
        "API_KEY_INVALID", "API key not valid", "PERMISSION_DENIED",
        "UNAUTHENTICATED", "API key expired"
    ])


CONTEXT_BEFORE = 3  # 배치 앞쪽 참고 대사 수
CONTEXT_AFTER = 2   # 배치 뒤쪽 참고 대사 수


def _translate_batch_with_recovery(
    client: genai.Client,
    batch: List[Dict[str, Any]],
    models_to_try: List[str],
    context_before: Optional[List[Dict[str, Any]]] = None,
    context_after: Optional[List[Dict[str, Any]]] = None,
    video_title: Optional[str] = None,
    target_lang: str = "ko"
) -> Tuple[Dict[int, str], str, Optional[str]]:
    """
    배치 단위(35개 권장) 번역을 수행하고, 일부 라인이 누락되었을 경우
    누락된 라인만 마이크로 배치로 즉각 재요청하여 100% 완전 번역을 보장합니다.
    모델별 부분 결과는 버리지 않고 합쳐서(먼저 성공한 모델 우선) 최선의 결과를 반환합니다.
    반환: (ko_map, used_model_name, last_error) — ko_map 이 일부만 채워졌을 수 있음.
    API 키 오류 등 치명적 오류는 TranslationFatalError 로 즉시 전파합니다.
    """
    last_err = None
    best_map: Dict[int, str] = {}
    used_models: List[str] = []
    for model_name in models_to_try:
        try:
            # 5.0초 간격 보장 (Gemini Free Tier 15 RPM 한도 완벽 보호: 분당 최대 12회)
            _wait_for_rate_limit()

            # 이미 확보한 줄은 다시 요청하지 않음 (이전 모델의 부분 결과 재활용)
            pending = [i for i in range(len(batch)) if i not in best_map]
            if len(pending) == len(batch):
                prompt = _build_translation_prompt(batch, context_before, context_after, video_title, target_lang)
            else:
                prompt = _build_translation_prompt([batch[i] for i in pending], context_before, context_after, video_title, target_lang)
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=8192)
            )
            raw_map = _parse_translation_response(resp.text or "", len(pending))
            ko_map = {pending[k]: v for k, v in raw_map.items()}
            if ko_map:
                used_models.append(model_name)
            for k, v in ko_map.items():
                best_map.setdefault(k, v)

            # 누락된 대사 인덱스 확인
            missing_indices = [i for i in range(len(batch)) if i not in best_map]

            # 누락 대사가 일부 발생한 경우, 누락된 항목만 즉각 마이크로 재요청하여 100% 보충
            if missing_indices and len(missing_indices) <= int(len(batch) * 0.6):
                try:
                    # 마이크로 보충 요청 전에도 5.0초 안전 간격 유지
                    _wait_for_rate_limit()
                    missing_items = [batch[i] for i in missing_indices]
                    m_prompt = _build_translation_prompt(missing_items, context_before, context_after, video_title, target_lang)
                    m_resp = client.models.generate_content(
                        model=model_name,
                        contents=m_prompt,
                        config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=4096)
                    )
                    m_map = _parse_translation_response(m_resp.text or "", len(missing_items))
                    for m_i, orig_i in enumerate(missing_indices):
                        if m_i in m_map:
                            best_map.setdefault(orig_i, m_map[m_i])
                except Exception as me:
                    if _is_fatal_api_error(str(me)):
                        raise TranslationFatalError(str(me))

            # 누락 대사가 남아있다면 다음 모델로 재시도하여 100% 번역 추구
            if len(best_map) < len(batch):
                raise ValueError(f"자막 일부 미번역 ({len(best_map)}/{len(batch)}개만 파싱됨, 다음 모델 시도)")

            return best_map, "+".join(dict.fromkeys(used_models)) or model_name, None

        except TranslationFatalError:
            raise
        except Exception as e:
            last_err = str(e)
            if _is_fatal_api_error(last_err):
                raise TranslationFatalError(last_err)
            if "429" in last_err or "RESOURCE_EXHAUSTED" in last_err:
                time.sleep(8.0)
                _mark_rate_limit_now()
            else:
                time.sleep(2.0)
            continue

    return best_map, "+".join(dict.fromkeys(used_models)), last_err


def _batch_context(items: List[Dict[str, Any]], start_i: int, end_i: int):
    return items[max(0, start_i - CONTEXT_BEFORE):start_i], items[end_i:end_i + CONTEXT_AFTER]


def translate_subtitles_gemini(
    subtitles: List[Dict[str, Any]],
    target_lang: str = "ko",
    api_key: Optional[str] = None,
    video_title: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    자막 목록(원문)을 Gemini를 이용해 target_lang(기본 한국어)으로 고속 번역하고,
    각 자막 객체에 'ko_text'(번역문 필드, 이름은 하위 호환용) 필드를 추가하여 반환합니다.
    (번역에 실패한 줄은 ko_text 를 비워 두며, 화면/내보내기에서 원문으로 대체 표시됩니다)
    """
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key or not subtitles:
        return subtitles

    client = genai.Client(api_key=key)
    batch_size = 25  # 자막 싱크 완벽 일치 및 토큰 초과 방지
    translated_subtitles = [dict(s) for s in subtitles]

    models_to_try = [DEFAULT_TRANSLATE_MODEL] + [m for m in FALLBACK_TRANSLATE_MODELS if m != DEFAULT_TRANSLATE_MODEL]

    for start_i in range(0, len(translated_subtitles), batch_size):
        end_i = start_i + batch_size
        batch = translated_subtitles[start_i:end_i]
        ctx_b, ctx_a = _batch_context(translated_subtitles, start_i, end_i)
        try:
            ko_map, _, _ = _translate_batch_with_recovery(client, batch, models_to_try, ctx_b, ctx_a, video_title, target_lang)
        except TranslationFatalError:
            break

        for idx, item in enumerate(batch):
            if idx in ko_map:
                item["ko_text"] = ko_map[idx]

    return translated_subtitles

def translate_subtitles_stream(
    subtitles: List[Dict[str, Any]],
    target_lang: str = "ko",
    api_key: Optional[str] = None,
    is_cancelled_callback: Optional[Any] = None,
    video_title: Optional[str] = None
):
    """
    자막 목록을 Gemini를 이용해 배치 단위로 번역하면서
    실시간 진행률 및 로그 이벤트를 yield하는 제너레이터입니다.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        yield {
            "type": "error",
            "message": "Gemini API 키가 등록되지 않았습니다. 우측 상단 [⚙️ 설정] 메뉴에서 API 키를 입력해주세요."
        }
        return

    if not subtitles:
        yield {
            "type": "error",
            "message": "번역할 자막 데이터가 비어 있습니다."
        }
        return

    try:
        client = genai.Client(api_key=key)
    except Exception as e:
        yield {
            "type": "error",
            "message": f"Gemini 클라이언트 초기화 실패: {str(e)}"
        }
        return

    batch_size = 25  # 자막 싱크 완벽 일치 및 토큰 초과 방지
    translated_subtitles = [dict(s) for s in subtitles]
    total_count = len(translated_subtitles)
    total_batches = (total_count + batch_size - 1) // batch_size

    yield {
        "type": "start",
        "total_count": total_count,
        "total_batches": total_batches,
        "batch_size": batch_size,
        "message": f"총 {total_count}개 대사 {language_name(target_lang)} 번역 작업을 시작합니다. (배치: {batch_size}개, 총 {total_batches}회 / 15 RPM 안전 보호 5.0초 주기 / {DEFAULT_TRANSLATE_MODEL})"
    }

    models_to_try = [DEFAULT_TRANSLATE_MODEL] + [m for m in FALLBACK_TRANSLATE_MODELS if m != DEFAULT_TRANSLATE_MODEL]

    for b_idx, start_i in enumerate(range(0, total_count, batch_size)):
        if is_cancelled_callback and is_cancelled_callback():
            yield {
                "type": "cancelled",
                "message": f"번역 요청이 사용자에 의해 중단되었습니다. (총 {b_idx}/{total_batches} 배치 완료)",
                "subtitles": translated_subtitles
            }
            return

        batch = translated_subtitles[start_i:start_i + batch_size]
        start_num = start_i + 1
        end_num = min(start_i + batch_size, total_count)
        percent = int(((b_idx) / total_batches) * 100)

        yield {
            "type": "progress",
            "batch_index": b_idx + 1,
            "total_batches": total_batches,
            "processed_count": start_i,
            "total_count": total_count,
            "percent": percent,
            "message": f"[{b_idx + 1}/{total_batches}] {start_num}~{end_num}번 대사 번역 요청 중... ({DEFAULT_TRANSLATE_MODEL})"
        }

        ctx_b, ctx_a = _batch_context(translated_subtitles, start_i, start_i + batch_size)
        try:
            ko_map, used_model_name, last_err = _translate_batch_with_recovery(
                client, batch, models_to_try, ctx_b, ctx_a, video_title, target_lang
            )
        except TranslationFatalError as fe:
            yield {
                "type": "error",
                "message": f"Gemini API 키/권한 오류로 번역을 중단합니다. [⚙️ 설정]에서 API 키를 확인해주세요. ({str(fe)[:120]})"
            }
            return

        # 번역 실패 줄은 ko_text 를 비워 둠 → 화면은 원문 + '번역 대기' 표시, 재번역 시 다시 시도됨
        for idx, item in enumerate(batch):
            if idx in ko_map:
                item["ko_text"] = ko_map[idx]

        if not ko_map:
            yield {
                "type": "log",
                "level": "warn",
                "message": f"[{b_idx + 1}/{total_batches}] 번역 재시도 실패: {str(last_err)[:80]}... (원문 유지)"
            }
        else:
            parsed_cnt = len(ko_map)
            level = "info" if parsed_cnt == len(batch) else "warn"
            mark = "✓" if parsed_cnt == len(batch) else "(일부 원문 유지)"
            yield {
                "type": "log",
                "level": level,
                "message": f"[{b_idx + 1}/{total_batches}] {start_num}~{end_num}번 대사 번역 완료 ({parsed_cnt}/{len(batch)}개, {used_model_name}) {mark}"
            }

    yield {
        "type": "complete",
        "total_count": total_count,
        "percent": 100,
        "message": f"🎉 총 {total_count}개 대사의 {language_name(target_lang)} 번역이 모두 완료되었습니다!",
        "subtitles": translated_subtitles
    }

# 2. 단순 텍스트 정리기 (No AI / Rule-based, 0원, 0.1초 완성)
def generate_raw_transcript_note(
    video_info: Dict[str, Any],
    transcript_data: Dict[str, Any]
) -> Dict[str, Any]:
    chunks = transcript_data.get("chunks", [])
    title = video_info.get("title", "YouTube Video")
    channel = video_info.get("channel", "YouTube")
    duration = video_info.get("duration_str", "00:00")
    lang = transcript_data.get("language", "en")
    is_gen = transcript_data.get("is_generated", False)

    md_lines = [
        f"# {title}",
        "",
        f"> 📺 **채널**: {channel} | **재생시간**: {duration} | **자막 언어**: {lang} ({'자동생성' if is_gen else '공식자막'})",
        "",
        "---",
        "",
        "## ⏱️ 타임스탬프 원문 자막 타임라인",
        "",
        "*아래 타임스탬프를 클릭하면 영상의 해당 위치로 즉시 이동합니다.*",
        ""
    ]

    for chunk in chunks:
        ts = chunk.get("timestamp", "00:00")
        text = chunk.get("text", "").strip()
        md_lines.append(f"### [{ts}]")
        md_lines.append(f"{text}\n")

    markdown_content = "\n".join(md_lines)
    return {
        "success": True,
        "markdown": markdown_content,
        "engine": "raw",
        "model_used": "No AI (Rule-Based Transcript Formatter)"
    }

# 3. 구독 AI(ChatGPT/Claude)용 완성형 프롬프트 생성기 (클립보드 복사용)
def generate_clipboard_prompt(
    video_info: Dict[str, Any],
    transcript_data: Dict[str, Any],
    target_lang: str = "ko"
) -> str:
    transcript_text = transcript_data.get("full_text", "")
    source_lang = transcript_data.get("language", "en")
    system_prompt = get_system_prompt_for_lang(target_lang, source_lang)
    user_prompt = build_user_prompt(video_info, transcript_text, source_lang=source_lang, target_lang=target_lang)

    target_name = language_name(target_lang)
    header_role = f"[System Role & Instructions - Language: {target_name}]" if target_lang != "ko" else "[역할 및 지침]"
    header_task = "[Task Request]" if target_lang != "ko" else "[요청 작업]"
    citation_guard = """==================================================
⚠️ [출처 및 인용 마커 절대 금지 규칙 (Strict Clean Formatting Rule)]
1. 웹 검색(Web Browsing) 또는 캔버스(Canvas) 연동 시 자동 생성되는 내부 참조 태그(예: :chatgpt-content-reference{...}, :...-reference{...}, 【...†source】, [cite: ...])나 인용 각주 번호를 본문 및 표에 절대 포함하지 마십시오.
2. 모든 내용은 출처 기호나 내부 태그 없이, 문맥 속에 자연스럽게 녹아든 완결된 유려한 표준 마크다운 줄글로만 작성하십시오.
""" if target_lang == "ko" else """==================================================
⚠️ [Strict Clean Formatting Rule]
1. DO NOT output any internal citation markers, search reference tags (e.g. :chatgpt-content-reference{...}, :...-reference{...}, 【...†source】, [cite: ...]), or numeric bracket footnotes in the text or tables.
2. All information must be written in clean, fluent markdown prose without raw citation tags.
"""

    return f"""{header_role}
{system_prompt}

{citation_guard}==================================================
{header_task}
{user_prompt}
"""
