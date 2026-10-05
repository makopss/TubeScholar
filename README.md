# 🎓 TubeScholar - 유튜브 & 로컬 비디오 LLM 심층 지식 확장 학습기

**한국어** | [🇺🇸 English](README_EN.md)

유튜브(전문 기술 세미나, 학술 강의, 교양 등) 및 로컬 영상의 자막과 음성을 추출하고, **Google Gemini LLM**을 활용하여 단순 번역을 뛰어넘는 **[자막 오류 교정 + 타임라인별 핵심 요약 + Deep Dive(심화 배경지식 보충) + 전문용어 해설 + 신경망 오디오북]**을 제공하는 맞춤형 인터랙티브 학습 시스템입니다.

---

## 🌟 주요 핵심 기능

### 1. ⏱️ 타임스탬프 연동 인터랙티브 스플릿 뷰 (Split-View)
- **좌측**: YouTube 플레이어 및 내 PC의 로컬 영상(`.mp4`, `.webm`, `.mkv`)과 자막(`.srt`) 완벽 시청 지원.
- **우측**: 마크다운 학습 노트 (타임스탬프 `[03:25]` 클릭 시 해당 영상 위치로 즉시 점프).
- **실시간 드래그 자막 오버레이**: 마우스로 원하는 위치에 배치 가능한 CC 자막, 글자 크기 조절, `[` / `]` 단축키 싱크 미세 보정.

### 2. 🧠 단순 번역을 초월한 LLM 심층 지식 확장 (Deep Dive)
- **자막 오류 교정**: 자동 생성 자막의 고유명사, 전문용어, 음성 인식 오인식 교정.
- **지식 보충 해설 (Deep Dive)**: 영상에서 스쳐 지나가는 원리, 수식, 배경 맥락을 친절한 보충 설명 박스로 상세 해설.
- **핵심 어휘 사전 (Glossary)**: 영상에 사용된 주요 전문 표현 및 맥락 해설 표 제공.
- **이해도 점검 퀴즈**: 핵심 질문 및 셀프 체크.
- **17개 다국어 노트 생성 지원**: 한국어, 영어, 일본어 등 원하는 언어로 학습 노트를 즉시 생성 및 재작성(`🔄`).

### 3. 💬 인터랙티브 자막 스튜디오
- **3대 뷰 모드**: `원문`, `번역문`, `모두`(병기) 3가지 모드로 대사 시청.
- **실시간 싱크 자동 스크롤**: 영상 재생 위치에 맞춰 현재 자막이 자동으로 스크롤 및 하이라이트 (컴팩트 `📜` 체크박스 토글).
- **실시간 검색 및 내보내기**: 자막 키워드 검색, `.SRT` 및 `.TXT` 파일 다운로드.

### 4. 🎧 AI 신경망 오디오북 (edge-tts)
- 마크다운 학습 노트를 Microsoft 고품질 신경망 음성으로 읽어주는 오디오북 플레이어 탑재.
- 배속 조절, 음성 모델 선택 및 원클릭 `.mp3` 다운로드 지원.

### 5. 📖 집중 독서 모드 (Zen Reader View)
- 영상과 패널을 접고 책처럼 편안하게 읽는 집중 독서 모드 (단축키: `Z`).
- 다크 / 세피아(종이책) / 라이트 테마 지원, 글자 크기 조절, 자동 목차(TOC) 패널 제공.

### 6. 🌐 직관적인 UI 및 영구 보관
- **한국어 / 영어 2개 공식 UI** 언어 지원 (헤더 드롭다운으로 즉시 전환).
- 생성된 모든 학습 문서는 로컬 `data/notes/` 폴더에 표준 `.md` 파일로 영구 보관되며, **Obsidian**, **Logseq**, **Notion** 등에 즉시 복사/연동 가능.
- 보관함 드로어(Drawer)를 통해 과거 학습한 영상을 빠르게 검색 및 복원.

---

## 🚀 빠른 시작 방법

### A. Windows 설치 프로그램 사용 (일반 사용자 추천)
[GitHub Releases](https://github.com/makopss/TubeScholar/releases)에서 `TubeScholar-Setup-v1.0.0.exe`를 다운로드하여 실행하시면 Python 설치 없이 즉시 사용할 수 있습니다.

### B. 소스코드 직접 실행 (개발자용)
1. **저장소 클론**:
   ```bash
   git clone https://github.com/makopss/TubeScholar.git
   cd TubeScholar
   ```

2. **가상환경 생성 및 의존성 설치**:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate      # Windows
   # source .venv/bin/activate # macOS/Linux
   pip install -r requirements.txt
   ```

3. **프론트엔드 스타일 빌드 (수정 시 필요)**:
   ```bash
   npm install
   npm run build:css
   ```

4. **실행**:
   ```bash
   python run.py
   ```
   실행하면 기본 웹 브라우저에서 `http://127.0.0.1:8000`이 자동으로 열립니다.

---

## ⚙️ API 키 설정

웹 화면 우측 상단의 ⚙️ **설정** 아이콘을 클릭하여 설정합니다:
- **Gemini API 키**: 무료 [Google AI Studio](https://aistudio.google.com/)에서 발급받은 API 키를 입력합니다. (로컬 `.env`에 안전하게 보관됩니다)
- **모델 선택**: `Gemini 2.5 Flash`(추천, 초고속) 또는 `Gemini 2.5 Pro`(심층 분석) 선택 가능.
- **Groq API 키 (선택 사항)**: 고속 음성 변환 Whisper 엔진 사용 시 등록.

---

## 📁 디렉토리 구조

```
TubeScholar/
├── backend/
│   ├── app.py              # FastAPI 메인 서버 & API 라우터
│   ├── extractor.py        # 유튜브 자막 및 채널 메타데이터 추출기
│   ├── analyzer.py         # Gemini API 지식 확장 프롬프트 엔진
│   ├── storage.py          # 마크다운 노트 및 라이브러리 저장소 관리
│   └── tts.py              # edge-tts 신경망 오디오북 생성기
├── frontend/
│   ├── index.html          # 스플릿 뷰 대시보드 HTML
│   ├── app.js              # 통합 인터랙티브 클라이언트 JS
│   ├── i18n.js             # 다국어(i18n) 번역 카탈로그
│   └── style.css           # 다크 테마 및 전용 UI 스타일
├── data/
│   ├── notes/              # 생성된 마크다운(.md) 문서 보관 폴더
│   └── library.json        # 저장된 영상 메타데이터 인덱스
├── run.py                  # 원클릭 실행 & 워치독 스크립트
├── requirements.txt        # Python 의존성 목록
└── installer.iss           # Windows 인스톨러 빌드 스크립트
```

---

## 📄 라이선스

이 프로젝트는 MIT 라이선스에 따라 자유롭게 사용 및 수정할 수 있습니다.
오픈소스 커뮤니티의 기여와 PR을 환영합니다!
