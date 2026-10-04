/**
 * TubeScholar UI 다국어(i18n) 시스템
 * 지원 언어: 한국어(ko), English(en), 日本語(ja)
 */

const TUBESCHOLAR_I18N = {
  ko: {
    // 앱 헤더 및 기본 정보
    app_title: "TubeScholar - 유튜브 & 로컬 비디오 LLM 심층 지식 확장 학습기",
    brand_subtitle: "유튜브 & 로컬 비디오 LLM 심층 학습기",
    tab_gemini: "⚡ Gemini 자동 분석",
    tab_subscription: "📋 구독 AI 연동",
    url_placeholder: "유튜브 영상 URL 또는 채널 URL 입력...",
    btn_cancel: "⏹️ 중단",
    btn_analyze: "⚡ 분석 및 생성",
    btn_copy_prompt: "📋 프롬프트 복사",
    btn_local_video: "로컬 영상",
    btn_local_video_title: "내 PC 로컬 영상 및 자막 열기",
    btn_channel: "채널 탐색",
    btn_channel_title: "채널 영상 탐색",
    btn_library: "보관함",
    btn_library_title: "저장된 학습 보관함",
    btn_settings_title: "Gemini 무료 API 키 설정",
    btn_shutdown_title: "TubeScholar 프로그램 종료",

    // 비디오 플레이어 & 오버레이
    player_placeholder_title: "학습할 유튜브 영상 URL을 입력하거나 [📁 로컬 영상]을 선택하세요.",
    player_placeholder_desc: "타임스탬프 클릭 시 해당 위치로 영상이 즉시 점프합니다.",
    overlay_drag_hint: "마우스로 잡고 원하는 위치로 드래그할 수 있습니다 (더블클릭 시 하단 복원)",
    overlay_drag_badge: "✥ 드래그 이동",
    floating_fs_title: "자막과 함께 전체화면 전환 (단축키: F)",
    btn_prev_sub_title: "이전 자막 이동 (단축키: A)",
    btn_replay_sub_title: "현재 자막 반복 재생 (단축키: S)",
    btn_next_sub_title: "다음 자막 이동 (단축키: D)",

    // 플레이어 컨트롤바
    seek_back: "⏪ -10초",
    play_pause: "재생 / 일시정지",
    seek_forward: "⏩ +10초",
    speed_label: "배속:",
    player_fs_title: "자막과 함께 전체화면으로 시청 (단축키: F)",
    fullscreen: "전체화면",
    toggle_cc_title: "화면 위 실시간 자막 켜기/끄기",
    ctrl_orig_title: "원문 자막",
    ctrl_orig_label: "원문",
    ctrl_trans_title: "번역 자막",
    ctrl_bi_title: "동시 병기 출력",
    ctrl_bi_label: "병기",
    sync_wrap_title: "자막 싱크 보정 (영상별 자동 저장)",
    sync_badge_title: "자막 싱크 보정값 (클릭 또는 \\ 키: 0초로 초기화)",
    btn_sync_slower_title: "자막을 0.2초 늦게 표시 (단축키: [ )",
    btn_sync_faster_title: "자막을 0.2초 빠르게 표시 (단축키: ] )",
    btn_sync_reset_title: "싱크 초기화 (0.0초, 단축키: \\)",
    btn_sub_font_smaller_title: "자막 글자 크기 축소",
    btn_sub_font_larger_title: "자막 글자 크기 확대",
    btn_reset_pos_title: "드래그한 자막 위치를 기본 하단 중앙으로 초기화",
    reset_position: "↺ 위치 복원",
    meta_subs_detected: "자막: 감지됨",
    view_original_video: "원본 보기",

    // 효율적인 학습 팁 배너
    tips_title: "💡 효율적인 학습 팁",
    tip_edit: "• 우측 상단의 <strong class=\"text-amber-300\">✏️ 편집</strong> 버튼을 누르면 노트를 직접 수정/필기할 수 있습니다.",
    tip_notes: "• 같은 영상을 여러 번 분석해도 각각 별도의 고유 노트로 자동 누적 보관됩니다.",
    tip_local: "• <strong class=\"text-sky-400\">📁 로컬 영상</strong>을 누르면 PC 안의 영상과 자막(.srt)도 동일하게 시청 & 연동됩니다.",

    // 상단 뷰 전환 & 툴바
    tab_note: "📖 학습 노트",
    tab_subtitles: "💬 자막 스크립트",
    status_tag_done: "완료",
    btn_edit: "✏️ 편집",
    btn_preview: "👁️ 미리보기",
    btn_copy: "복사",
    btn_download_md: ".md 다운로드",
    btn_audiobook_title: "edge-tts 고품질 신경망 음성으로 노트를 읽어줍니다",
    btn_audiobook: "오디오북",
    btn_reader_mode_title: "영상과 패널을 접고 책처럼 편안하게 읽는 집중 독서 모드 (단축키: Z)",
    btn_reader_mode: "읽기 모드",
    btn_retranslate_title: "현재 영상의 자막을 1:1 고정밀 싱크 엔진으로 다시 번역합니다",
    btn_retranslate: "자막 재번역",
    btn_download_srt_label: "📥 .SRT 다운로드",
    btn_download_txt_label: "📄 .TXT 다운로드",

    // 📖 집중 읽기 모드 (Zen Focus View)
    zen_exit: "일반 뷰로 복귀",
    theme_dark: "🌙 다크",
    theme_sepia: "📜 세피아",
    theme_light: "☀️ 라이트",
    font_dec_title: "글자 축소",
    font_inc_title: "글자 확대",
    toc_toggle_title: "목차 패널 열기/닫기",
    toc_btn: "📑 목차",
    tts_play_title: "오디오북 재생",
    audio_btn: "🎧 오디오",
    zen_toc_heading: "📑 목차 (TOC)",
    zen_toc_loading: "목차를 생성하고 있습니다...",

    // 오디오북 (TTS)
    tts_card_title: "AI 신경망 오디오북 (edge-tts)",
    tts_status_ready: "준비 완료",
    tts_status_generating: "생성 중...",
    tts_status_error: "생성 실패",
    tts_status_playing: "재생 중",
    tts_download_title: "MP3 오디오 파일 다운로드",

    // 구독 AI 인라인 카드
    paste_card_title: "📋 ChatGPT / Claude 답변 붙여넣기",
    paste_card_desc: "복사한 마크다운 답변을 아래에 넣고 적용하세요",
    paste_textarea_placeholder: "ChatGPT 또는 Claude의 답변을 여기에 붙여넣으세요 (Ctrl+V)...",
    paste_apply_btn: "노트 적용 및 영구 저장",

    // 편집 에디터
    editor_title: "📝 마크다운 직접 수정 중",
    editor_save_btn: "💾 저장 및 적용",
    editor_placeholder: "마크다운 내용을 수정하세요...",

    // 분석 로딩 오버레이
    loading_title_youtube: "유튜브 영상 분석 중...",
    loading_desc_youtube: "자막을 추출하고 학습 노트를 구성하고 있습니다.",
    loading_title_local: "로컬 영상 분석 중...",
    loading_desc_local: "음성을 추출하고 타임스탬프 노트를 생성하고 있습니다.",
    step_1: "자막 및 메타데이터 추출",
    step_2: "문맥 오류 교정 및 지식 확장 (Deep Dive)",
    step_3: "타임라인 렌더링 및 로컬 저장",
    btn_cancel_analysis: "분석 중단하기",

    // 빈 노트 플레이스홀더
    empty_note_title: "학습 노트를 생성하거나 불러오세요",
    empty_note_desc: "상단에서 <strong>[⚡ Gemini 자동 분석]</strong> 또는 <strong>[📋 구독 AI 연동]</strong>을 선택한 뒤 URL을 입력하거나 로컬 영상을 불러오세요.",

    // 자막 뷰 모드 & 자막 옵션 툴바
    mode_original: "원문",
    mode_translated: "{lang} 번역",
    mode_bilingual: "{lang} 병기",
    btn_translate_request: "{lang} 번역 요청",
    btn_translate_stop: "⏹️ 번역 중단",
    btn_translate_retranslate: "🔄 {lang} 재번역",
    btn_translate_done: "✓ {lang} 번역 완료",
    btn_translate_same: "자막 준비 완료",
    sub_source_lang_title: "원문 자막 트랙 선택",
    sub_source_auto: "원문: 자동 감지",
    sub_target_lang_title: "번역 대상 언어 선택",
    sub_translate_tooltip: "Gemini를 호출하여 번역을 명시적으로 생성합니다 (API 사용)",
    btn_sub_autoscroll_title: "영상 재생 시 현재 자막으로 목록 자동 스크롤",
    sub_autoscroll_on: "자동 스크롤 ON",
    sub_autoscroll_off: "자동 스크롤 OFF",
    search_subtitles_placeholder: "자막 검색 (원문 또는 번역문)...",
    sub_lines_count: "{count}개 대사",
    no_subtitles_title: "자막이 없습니다",
    no_subtitles_desc: "영상을 분석하거나 불러오면 인터랙티브 자막 목록이 표시됩니다. 자막을 클릭하면 해당 시간대로 즉시 이동합니다!",
    no_subtitles_found: "일치하는 자막이 없습니다.",
    subtitles_waiting_analysis: "영상을 분석하거나 불러오면 자막이 여기에 표시됩니다.",

    // 로컬 비디오 모달
    local_modal_title: "📁 내 PC 로컬 영상 및 자막 열기",
    local_video_step1: "1. 비디오 파일 선택 (.mp4, .webm, .mkv)",
    local_sub_step2: "2. 자막 파일 선택 (.srt, .vtt) <span class=\"text-sky-400 font-normal\">(자막이 없으면 비워두세요)</span>",
    local_sub_tip: "💡 자막 파일이 없으신가요? 비워두시면 <strong>Gemini가 영상의 음성을 직접 귀로 듣고</strong> 분석합니다!",
    local_title_step3: "3. 영상 제목 (선택)",
    local_title_placeholder: "영상 제목을 입력하세요...",
    local_audio_direct: "🎙️ 자막 없이 음성 직접 분석",
    local_analyze_btn: "⚡ 자막으로 분석",

    // 보관함 모달 & 드로어
    library_drawer_title: "나의 학습 보관함",
    library_count_simple: "{count}개",
    library_empty: "아직 저장된 학습 노트가 없습니다.",
    tag_local: "📁 로컬",
    library_load_btn: "열기",
    library_delete_btn: "삭제",

    // 채널 모달
    channel_modal_title: "📺 채널 최근 영상 탐색 및 변환",
    channel_url_placeholder: "예: https://www.youtube.com/@3blue1brown 또는 채널 URL...",
    channel_search_btn: "영상 불러오기",
    channel_hint_empty: "채널 URL을 입력하고 [영상 불러오기]를 눌러주세요.",

    // 설정 모달
    settings_modal_title: "Gemini API 설정",
    settings_gemini_label: "Google Gemini 무료 API 키",
    settings_gemini_link: "무료 키 발급받기 ↗",
    settings_gemini_tip: "* 신용카드 없이 구글 계정만으로 즉시 발급되며 하루 1,500회 무료입니다.",
    settings_groq_label: "⚡ Groq Cloud 무료 API 키",
    settings_groq_badge: "0.1초 칼싱크",
    settings_groq_link: "무료 키 발급받기",
    settings_groq_tip: "* 로컬 영상의 자막을 10초 만에 0.1초 단위 칼싱크(Whisper Large-v3)로 자동 생성합니다. (매일 8시간 완전 무료)",
    settings_save_btn_simple: "저장하기",

    // 자막 번역 진행 모달
    trans_modal_title: "한국어 자막 번역 진행",
    trans_modal_subtitle: "Gemini 3.5 Flash Lite (500 RPD) 모델을 통해 자막을 초고속 번역하고 있습니다.",
    trans_preparing: "번역 준비 중...",
    trans_log_title: "실시간 처리 로그",
    trans_autoscroll_label: "자동 스크롤",
    trans_log_waiting: "[대기] 번역 요청 대기 중...",
    trans_footer_hint: "* 언제든지 번역을 취소할 수 있습니다.",
    trans_abort_btn: "🛑 번역 취소",
    btn_close: "닫기",
    trans_complete_btn: "✓ 적용 및 닫기",

    // 독서 팝업 (Reader Popup Modal)
    reader_mode_badge: "집중 독서 모드",
    reader_toc_btn_title: "좌측 목차 패널 열기/닫기",
    reader_print: "🖨️ 인쇄",
    reader_print_title: "인쇄 및 PDF로 저장 (Ctrl+P)",
    reader_close: "✕ 닫기",
    reader_close_title: "팝업 닫기 (Esc)",
    reader_toc_title: "📑 목차 목록",

    // 알림 및 확인 대화상자
    copied_prompt: "구독 AI용 프롬프트가 클립보드에 복사되었습니다!\nChatGPT나 Claude 창에 붙여넣어 학습 노트를 생성하세요.",
    copied_note: "학습 노트 마크다운 전문이 클립보드에 복사되었습니다.",
    copied_clipboard: "클립보드에 복사되었습니다.",
    confirm_delete: "정말 이 학습 노트를 삭제하시겠습니까?\n삭제된 노트는 복구할 수 없습니다.",
    note_saved: "노트가 성공적으로 저장되었습니다.",
    shutdown_confirm: "TubeScholar 프로그램을 종료하시겠습니까?",
    error_empty_url: "유튜브 영상 또는 채널 URL을 입력해주세요.",
    error_api_key_required: "Gemini API 키가 등록되지 않았습니다. 우측 상단 [⚙️ 설정] 메뉴에서 API 키를 입력해주세요.",
    trans_in_progress: "자막 번역이 진행 중입니다. 잠시만 기다려주세요.",
    trans_stopped: "자막 번역이 중단되었습니다."
  },

  en: {
    // App Header & Info
    app_title: "TubeScholar - YouTube & Local Video LLM Deep Learning Note Studio",
    brand_subtitle: "YouTube & Local Video LLM Deep Learning Studio",
    tab_gemini: "⚡ Gemini Auto Note",
    tab_subscription: "📋 Subscription AI Prompt",
    url_placeholder: "Enter YouTube video or channel URL...",
    btn_cancel: "⏹️ Stop",
    btn_analyze: "⚡ Analyze & Generate",
    btn_copy_prompt: "📋 Copy Prompt",
    btn_local_video: "Local Video",
    btn_local_video_title: "Open local video & subtitles from PC",
    btn_channel: "Channel",
    btn_channel_title: "Explore channel videos",
    btn_library: "Library",
    btn_library_title: "Saved learning library",
    btn_settings_title: "Gemini API Key Settings",
    btn_shutdown_title: "Exit TubeScholar",

    // Video Player & Overlay
    player_placeholder_title: "Enter a YouTube video URL or select [📁 Local Video] to start studying.",
    player_placeholder_desc: "Clicking a timestamp jumps directly to that section in the video.",
    overlay_drag_hint: "Drag to move overlay anywhere (Double click to reset position)",
    overlay_drag_badge: "✥ Drag to move",
    floating_fs_title: "Toggle fullscreen with subtitles (Shortcut: F)",
    btn_prev_sub_title: "Previous Subtitle (Shortcut: A)",
    btn_replay_sub_title: "Replay Current Subtitle (Shortcut: S)",
    btn_next_sub_title: "Next Subtitle (Shortcut: D)",

    // Player Control Bar
    seek_back: "⏪ -10s",
    play_pause: "Play / Pause",
    seek_forward: "⏩ +10s",
    speed_label: "Speed:",
    player_fs_title: "Watch in fullscreen with subtitles (Shortcut: F)",
    fullscreen: "Fullscreen",
    toggle_cc_title: "Toggle subtitles overlay on video",
    ctrl_orig_title: "Original subtitles",
    ctrl_orig_label: "Original",
    ctrl_trans_title: "Translated subtitles",
    ctrl_bi_title: "Bilingual display",
    ctrl_bi_label: "Bilingual",
    sync_wrap_title: "Subtitle sync offset (Auto-saved per video)",
    sync_badge_title: "Subtitle sync offset (Click or \\ to reset to 0s)",
    btn_sync_slower_title: "Delay subtitles by 0.2s (Shortcut: [)",
    btn_sync_faster_title: "Advance subtitles by 0.2s (Shortcut: ])",
    btn_sync_reset_title: "Reset sync (0.0s, Shortcut: \\)",
    btn_sub_font_smaller_title: "Smaller subtitle text",
    btn_sub_font_larger_title: "Larger subtitle text",
    btn_reset_pos_title: "Reset subtitle position to bottom center",
    reset_position: "↺ Reset Pos",
    meta_subs_detected: "Subtitles: Detected",
    view_original_video: "View Original",

    // Study Tips Banner
    tips_title: "💡 Efficient Study Tips",
    tip_edit: "• Click <strong class=\"text-amber-300\">✏️ Edit</strong> in the top right to modify notes or write memos directly.",
    tip_notes: "• Even if you analyze the same video multiple times, each note is preserved as a separate version in your library.",
    tip_local: "• Click <strong class=\"text-sky-400\">📁 Local Video</strong> to watch and study local PC videos and subtitles (.srt) seamlessly.",

    // Top View Switching & Toolbar
    tab_note: "📖 Study Note",
    tab_subtitles: "💬 Subtitles",
    status_tag_done: "Done",
    btn_edit: "✏️ Edit",
    btn_preview: "👁️ Preview",
    btn_copy: "Copy",
    btn_download_md: ".md Download",
    btn_audiobook_title: "Listen to this note with high-quality edge-tts neural voice",
    btn_audiobook: "Audiobook",
    btn_reader_mode_title: "Distraction-free Reader Mode for reading like a book (Shortcut: Z)",
    btn_reader_mode: "Reader Mode",
    btn_retranslate_title: "Re-translate subtitles with 1:1 high-precision sync engine",
    btn_retranslate: "Re-translate Subtitles",
    btn_download_srt_label: "📥 Download .SRT",
    btn_download_txt_label: "📄 Download .TXT",

    // 📖 Focused Reader View (Zen Mode)
    zen_exit: "Exit Reader View",
    theme_dark: "🌙 Dark",
    theme_sepia: "📜 Sepia",
    theme_light: "☀️ Light",
    font_dec_title: "Decrease font size",
    font_inc_title: "Increase font size",
    toc_toggle_title: "Toggle table of contents panel",
    toc_btn: "📑 TOC",
    tts_play_title: "Play audiobook",
    audio_btn: "🎧 Audio",
    zen_toc_heading: "📑 Table of Contents",
    zen_toc_loading: "Generating table of contents...",

    // Audiobook (TTS)
    tts_card_title: "AI Neural Audiobook (edge-tts)",
    tts_status_ready: "Ready",
    tts_status_generating: "Generating...",
    tts_status_error: "Generation Failed",
    tts_status_playing: "Playing",
    tts_download_title: "Download MP3 Audio File",

    // Subscription AI Paste Card
    paste_card_title: "📋 Paste ChatGPT / Claude Response",
    paste_card_desc: "Paste the copied markdown response below to apply and save",
    paste_textarea_placeholder: "Paste ChatGPT or Claude's response here (Ctrl+V)...",
    paste_apply_btn: "Apply & Permanently Save Note",

    // Markdown Editor
    editor_title: "📝 Editing Markdown Directly",
    editor_save_btn: "💾 Save & Apply",
    editor_placeholder: "Edit markdown content here...",

    // Loading Overlay
    loading_title_youtube: "Analyzing YouTube Video...",
    loading_desc_youtube: "Extracting subtitles and structuring study note.",
    loading_title_local: "Analyzing Local Video...",
    loading_desc_local: "Extracting audio and generating timestamped study note.",
    step_1: "Extracting subtitles & metadata",
    step_2: "Correcting context & expanding knowledge (Deep Dive)",
    step_3: "Rendering timeline & saving locally",
    btn_cancel_analysis: "Cancel Analysis",

    // Empty Note Placeholder
    empty_note_title: "Generate or load a study note",
    empty_note_desc: "Select <strong>[⚡ Gemini Auto Note]</strong> or <strong>[📋 Subscription AI Prompt]</strong> at the top, then enter a URL or load a local video.",

    // Subtitles View & Toolbar
    mode_original: "Original",
    mode_translated: "{lang} Translation",
    mode_bilingual: "{lang} Bilingual",
    btn_translate_request: "Translate to {lang}",
    btn_translate_stop: "⏹️ Stop Translation",
    btn_translate_retranslate: "🔄 Re-translate to {lang}",
    btn_translate_done: "✓ {lang} Translated",
    btn_translate_same: "Subtitles Ready",
    sub_source_lang_title: "Select source subtitle track",
    sub_source_auto: "Source: Auto Detect",
    sub_target_lang_title: "Select target translation language",
    sub_translate_tooltip: "Call Gemini API to generate subtitle translation",
    btn_sub_autoscroll_title: "Auto-scroll list to active subtitle while playing",
    sub_autoscroll_on: "Auto Scroll ON",
    sub_autoscroll_off: "Auto Scroll OFF",
    search_subtitles_placeholder: "Search subtitles (original or translation)...",
    sub_lines_count: "{count} lines",
    no_subtitles_title: "No Subtitles Available",
    no_subtitles_desc: "Interactive subtitles will appear here once the video is loaded or analyzed. Clicking a subtitle jumps directly to that timestamp!",
    no_subtitles_found: "No matching subtitles found.",
    subtitles_waiting_analysis: "Subtitles will appear here once video is loaded or analyzed.",

    // Local Video Modal
    local_modal_title: "📁 Open Local Video & Subtitle File",
    local_video_step1: "1. Select Video File (.mp4, .webm, .mkv)",
    local_sub_step2: "2. Select Subtitle File (.srt, .vtt) <span class=\"text-sky-400 font-normal\">(Leave empty if no subtitles)</span>",
    local_sub_tip: "💡 No subtitle file? If left empty, <strong>Gemini will listen to audio directly</strong> to analyze!",
    local_title_step3: "3. Video Title (Optional)",
    local_title_placeholder: "Enter video title...",
    local_audio_direct: "🎙️ Analyze Audio Directly (No Subs)",
    local_analyze_btn: "⚡ Analyze with Subtitles",

    // Library Drawer
    library_drawer_title: "My Study Library",
    library_count_simple: "{count} notes",
    library_empty: "No saved study notes yet.",
    tag_local: "📁 Local",
    library_load_btn: "Open",
    library_delete_btn: "Delete",

    // Channel Modal
    channel_modal_title: "📺 Explore & Convert Recent Channel Videos",
    channel_url_placeholder: "e.g. https://www.youtube.com/@channel or Channel URL...",
    channel_search_btn: "Fetch Videos",
    channel_hint_empty: "Enter a channel URL and click [Fetch Videos].",

    // Settings Modal
    settings_modal_title: "Gemini API Settings",
    settings_gemini_label: "Google Gemini Free API Key",
    settings_gemini_link: "Get Free Key ↗",
    settings_gemini_tip: "* Free 1,500 requests/day with just a Google account, no credit card required.",
    settings_groq_label: "⚡ Groq Cloud Free API Key",
    settings_groq_badge: "0.1s Fast Sync",
    settings_groq_link: "Get Free Key",
    settings_groq_tip: "* Automatically generates precise 0.1s synced subtitles for local videos in 10s via Whisper Large-v3. (8 hours/day free)",
    settings_save_btn_simple: "Save",

    // Subtitle Translation Progress Modal
    trans_modal_title: "Subtitle Translation Progress",
    trans_modal_subtitle: "Translating subtitles at high speed using the Gemini Flash Lite model.",
    trans_preparing: "Preparing translation...",
    trans_log_title: "Real-time Log",
    trans_autoscroll_label: "Auto-scroll",
    trans_log_waiting: "[Waiting] Awaiting translation request...",
    trans_footer_hint: "* You can cancel the translation at any time.",
    trans_abort_btn: "🛑 Cancel Translation",
    btn_close: "Close",
    trans_complete_btn: "✓ Apply & Close",

    // Reader Popup Modal
    reader_mode_badge: "Focused Reader Mode",
    reader_toc_btn_title: "Toggle table of contents panel",
    reader_print: "🖨️ Print",
    reader_print_title: "Print and save as PDF (Ctrl+P)",
    reader_close: "✕ Close",
    reader_close_title: "Close popup (Esc)",
    reader_toc_title: "📑 Table of Contents",

    // Dialogs & Notifications
    copied_prompt: "Prompt for external AI copied to clipboard!\nPaste it into ChatGPT or Claude to generate your master study note.",
    copied_note: "Study note markdown copied to clipboard.",
    copied_clipboard: "Copied to clipboard.",
    confirm_delete: "Are you sure you want to delete this study note?\nDeleted notes cannot be recovered.",
    note_saved: "Note saved successfully.",
    shutdown_confirm: "Are you sure you want to exit TubeScholar?",
    error_empty_url: "Please enter a YouTube video or channel URL.",
    error_api_key_required: "Gemini API key is not configured. Please set your free key in [⚙️ Settings].",
    trans_in_progress: "Subtitle translation is currently in progress. Please wait.",
    trans_stopped: "Subtitle translation stopped."
  },

  ja: {
    // アプリヘッダー＆基本情報
    app_title: "TubeScholar - YouTube＆ローカル動画 LLM深層学習ノートスタジオ",
    brand_subtitle: "YouTube＆ローカル動画 LLM深層学習スタジオ",
    tab_gemini: "⚡ Gemini 自動分析",
    tab_subscription: "📋 サブスクAI連携",
    url_placeholder: "YouTube動画またはチャンネルのURLを入力...",
    btn_cancel: "⏹️ 中断",
    btn_analyze: "⚡ 分析＆生成",
    btn_copy_prompt: "📋 プロンプトをコピー",
    btn_local_video: "ローカル動画",
    btn_local_video_title: "PCのローカル動画・字幕を開く",
    btn_channel: "チャンネル",
    btn_channel_title: "チャンネル動画を探索",
    btn_library: "保管庫",
    btn_library_title: "保存済み学習ノート一覧",
    btn_settings_title: "Gemini無料APIキー設定",
    btn_shutdown_title: "TubeScholarの終了",

    // ビデオプレイヤー＆オーバーレイ
    player_placeholder_title: "学習するYouTube動画URLを入力するか、[📁 ローカル動画]を選択してください。",
    player_placeholder_desc: "タイムスタンプをクリックすると動画の該当位置に即座にジャンプします。",
    overlay_drag_hint: "ドラッグして好きな位置に移動できます（ダブルクリックで元の位置に戻す）",
    overlay_drag_badge: "✥ ドラッグ移動",
    floating_fs_title: "字幕付きで全画面表示 (ショートカット: F)",
    btn_prev_sub_title: "前の字幕へ移動 (ショートカット: A)",
    btn_replay_sub_title: "現在の字幕をリピート再生 (ショートカット: S)",
    btn_next_sub_title: "次の字幕へ移動 (ショートカット: D)",

    // プレイヤーコントロールバー
    seek_back: "⏪ -10秒",
    play_pause: "再生 / 一時停止",
    seek_forward: "⏩ +10秒",
    speed_label: "速度:",
    player_fs_title: "字幕付きで全画面視聴 (ショートカット: F)",
    fullscreen: "全画面",
    toggle_cc_title: "動画上の字幕オーバーレイのオン/オフ",
    ctrl_orig_title: "原文の字幕",
    ctrl_orig_label: "原文",
    ctrl_trans_title: "翻訳字幕",
    ctrl_bi_title: "2言語同時表示",
    ctrl_bi_label: "併記",
    sync_wrap_title: "字幕同期オフセット（動画ごとに自動保存）",
    sync_badge_title: "字幕同期補正値（クリックまたは \\ キーで0秒にリセット）",
    btn_sync_slower_title: "字幕を0.2秒遅く表示 (ショートカット: [ )",
    btn_sync_faster_title: "字幕を0.2秒早く表示 (ショートカット: ] )",
    btn_sync_reset_title: "同期リセット (0.0秒, ショートカット: \\)",
    btn_sub_font_smaller_title: "字幕の文字を小さく",
    btn_sub_font_larger_title: "字幕の文字を大きく",
    btn_reset_pos_title: "字幕の位置を下部中央にリセット",
    reset_position: "↺ 位置復元",
    meta_subs_detected: "字幕: 検出済み",
    view_original_video: "元動画を見る",

    // 学習のヒントバナー
    tips_title: "💡 効率的な学習のヒント",
    tip_edit: "• 右上の <strong class=\"text-amber-300\">✏️ 編集</strong> ボタンを押すと、ノートを直接修正・追記できます。",
    tip_notes: "• 同じ動画を複数回分析しても、個別のノートとして自動的に累積保存されます。",
    tip_local: "• <strong class=\"text-sky-400\">📁 ローカル動画</strong> を押すと、PC内の動画と字幕（.srt）も同様に視聴・連動できます。",

    // 上部ビュー切り替え＆ツールバー
    tab_note: "📖 学習ノート",
    tab_subtitles: "💬 字幕スクリプト",
    status_tag_done: "完了",
    btn_edit: "✏️ 編集",
    btn_preview: "👁️ プレビュー",
    btn_copy: "コピー",
    btn_download_md: ".md ダウンロード",
    btn_audiobook_title: "edge-tts 高品質ニューラル音声でノートを読み上げます",
    btn_audiobook: "オーディオブック",
    btn_reader_mode_title: "集中読書モードで本のように快適に読む (ショートカット: Z)",
    btn_reader_mode: "読書モード",
    btn_retranslate_title: "高精度同期エンジンで現在の動画の字幕を再翻訳します",
    btn_retranslate: "字幕再翻訳",
    btn_download_srt_label: "📥 .SRT ダウンロード",
    btn_download_txt_label: "📄 .TXT ダウンロード",

    // 📖 集中読書モード (Zen Focus View)
    zen_exit: "通常ビューに戻る",
    theme_dark: "🌙 ダーク",
    theme_sepia: "📜 セピア",
    theme_light: "☀️ ライト",
    font_dec_title: "文字縮小",
    font_inc_title: "文字拡大",
    toc_toggle_title: "目次パネルの開閉",
    toc_btn: "📑 目次",
    tts_play_title: "オーディオブック再生",
    audio_btn: "🎧 音声",
    zen_toc_heading: "📑 目次 (TOC)",
    zen_toc_loading: "目次を生成しています...",

    // オーディオブック (TTS)
    tts_card_title: "AI神経網オーディオブック (edge-tts)",
    tts_status_ready: "準備完了",
    tts_status_generating: "生成中...",
    tts_status_error: "生成失敗",
    tts_status_playing: "再生中",
    tts_download_title: "MP3オーディオファイルをダウンロード",

    // サブスクAIインライン貼り付けカード
    paste_card_title: "📋 ChatGPT / Claude 回答貼り付け",
    paste_card_desc: "コピーしたマークダウン回答を下に貼り付けて適用・保存してください",
    paste_textarea_placeholder: "ChatGPTまたはClaudeの回答をここに貼り付けてください (Ctrl+V)...",
    paste_apply_btn: "ノート適用＆永久保存",

    // マークダウンエディタ
    editor_title: "📝 マークダウン直接編集中",
    editor_save_btn: "💾 保存＆適用",
    editor_placeholder: "マークダウン内容を編集してください...",

    // 分析ローディングオーバーレイ
    loading_title_youtube: "YouTube動画を分析中...",
    loading_desc_youtube: "字幕を抽出し学習ノートを構成しています。",
    loading_title_local: "ローカル動画を分析中...",
    loading_desc_local: "音声を抽出しタイムスタンプ付きノートを生成しています。",
    step_1: "字幕およびメタデータの抽出",
    step_2: "文脈エラー校正＆知識拡張（Deep Dive）",
    step_3: "タイムライン描画＆ローカル保存",
    btn_cancel_analysis: "分析を中断する",

    // 空のノートプレースホルダー
    empty_note_title: "学習ノートを生成または読み込んでください",
    empty_note_desc: "上部で <strong>[⚡ Gemini 自動分析]</strong> または <strong>[📋 サブスクAI連携]</strong> を選択し、URLを入力するかローカル動画を読み込んでください。",

    // 字幕ビューモード＆字幕ツールバー
    mode_original: "原文",
    mode_translated: "{lang} 翻訳",
    mode_bilingual: "{lang} 併記",
    btn_translate_request: "{lang} 翻訳をリクエスト",
    btn_translate_stop: "⏹️ 翻訳を中断",
    btn_translate_retranslate: "🔄 {lang} 再翻訳",
    btn_translate_done: "✓ {lang} 翻訳完了",
    btn_translate_same: "字幕準備完了",
    sub_source_lang_title: "原文の字幕トラックを選択",
    sub_source_auto: "原文: 自動検出",
    sub_target_lang_title: "翻訳先言語を選択",
    sub_translate_tooltip: "Gemini APIを呼び出して字幕翻訳を明示的に生成します",
    btn_sub_autoscroll_title: "再生中に現在の字幕位置へ自動スクロール",
    sub_autoscroll_on: "自動スクロール ON",
    sub_autoscroll_off: "自動スクロール OFF",
    search_subtitles_placeholder: "字幕検索（原文または翻訳文）...",
    sub_lines_count: "{count} 行のセリフ",
    no_subtitles_title: "字幕がありません",
    no_subtitles_desc: "動画を分析または読み込むとインタラクティブな字幕リストが表示されます。字幕をクリックすると該当の時間へ即座に移動します！",
    no_subtitles_found: "一致する字幕が見つかりません。",
    subtitles_waiting_analysis: "動画を読み込むか分析すると字幕がここに表示されます。",

    // ローカル動画モーダル
    local_modal_title: "📁 PCのローカル動画・字幕を開く",
    local_video_step1: "1. 動画ファイルを選択 (.mp4, .webm, .mkv)",
    local_sub_step2: "2. 字幕ファイルを選択 (.srt, .vtt) <span class=\"text-sky-400 font-normal\">(字幕がない場合は空欄のままにしてください)</span>",
    local_sub_tip: "💡 字幕ファイルがありませんか？空欄にしておくと<strong>Geminiが動画の音声を直接聴き取って</strong>分析します！",
    local_title_step3: "3. 動画タイトル (任意)",
    local_title_placeholder: "動画のタイトルを入力...",
    local_audio_direct: "🎙️ 字幕なしで音声を直接分析",
    local_analyze_btn: "⚡ 字幕で分析",

    // 保管庫ドロワー
    library_drawer_title: "マイ学習保管庫",
    library_count_simple: "{count} 件",
    library_empty: "保存された学習ノートはまだありません。",
    tag_local: "📁 ローカル",
    library_load_btn: "開く",
    library_delete_btn: "削除",

    // チャンネルモーダル
    channel_modal_title: "📺 チャンネル最新動画の探索＆変換",
    channel_url_placeholder: "例: https://www.youtube.com/@3blue1brown またはチャンネルURL...",
    channel_search_btn: "動画を取得",
    channel_hint_empty: "チャンネルURLを入力し、[動画を取得]を押してください。",

    // 設定モーダル
    settings_modal_title: "Gemini API 設定",
    settings_gemini_label: "Google Gemini 無料APIキー",
    settings_gemini_link: "無料キーを取得 ↗",
    settings_gemini_tip: "* クレジットカード不要でGoogleアカウントのみで即時発行、1日1,500回無料です。",
    settings_groq_label: "⚡ Groq Cloud 無料APIキー",
    settings_groq_badge: "0.1秒 高精度同期",
    settings_groq_link: "無料キーを取得",
    settings_groq_tip: "* ローカル動画の字幕をWhisper Large-v3により0.1秒単位の高精度同期で10秒で自動生成します。(毎日8時間完全無料)",
    settings_save_btn_simple: "保存する",

    // 字幕翻訳進行モーダル
    trans_modal_title: "字幕翻訳の進行状況",
    trans_modal_subtitle: "Gemini Flash Liteモデルを使用して字幕を超高速翻訳しています。",
    trans_preparing: "翻訳を準備中...",
    trans_log_title: "リアルタイム処理ログ",
    trans_autoscroll_label: "自動スクロール",
    trans_log_waiting: "[待機] 翻訳リクエスト待機中...",
    trans_footer_hint: "* いつでも翻訳をキャンセルできます。",
    trans_abort_btn: "🛑 翻訳をキャンセル",
    btn_close: "閉じる",
    trans_complete_btn: "✓ 適用して閉じる",

    // 読書ポップアップ
    reader_mode_badge: "集中読書モード",
    reader_toc_btn_title: "目次パネルの開閉",
    reader_print: "🖨️ 印刷",
    reader_print_title: "印刷およびPDF保存 (Ctrl+P)",
    reader_close: "✕ 閉じる",
    reader_close_title: "閉じる (Esc)",
    reader_toc_title: "📑 目次リスト",

    // ダイアログ＆通知
    copied_prompt: "外部AI用のプロンプトがクリップボードにコピーされました！\nChatGPTやClaudeに貼り付けて学習ノートを生成してください。",
    copied_note: "学習ノートのマークダウン全文がクリップボードにコピーされました。",
    copied_clipboard: "クリップボードにコピーされました。",
    confirm_delete: "本当にこの学習ノートを削除しますか？\n削除されたノートは復元できません。",
    note_saved: "ノートが正常に保存されました。",
    shutdown_confirm: "TubeScholarを終了しますか？",
    error_empty_url: "YouTube動画またはチャンネルのURLを入力してください。",
    error_api_key_required: "Gemini APIキーが設定されていません。右上の[⚙️ 設定]からキーを入力してください。",
    trans_in_progress: "字幕の翻訳が進行中です。しばらくお待ちください。",
    trans_stopped: "字幕の翻訳が中断されました。"
  }
};

let currentUiLang = (function() {
  const saved = localStorage.getItem("tubescholar_ui_lang");
  if (saved && TUBESCHOLAR_I18N[saved]) return saved;
  const navLang = (navigator.language || navigator.userLanguage || "ko").toLowerCase();
  if (navLang.startsWith("ja")) return "ja";
  if (navLang.startsWith("en")) return "en";
  return "ko";
})();

function getUiLang() {
  return currentUiLang;
}

function setUiLang(lang) {
  if (!TUBESCHOLAR_I18N[lang]) lang = "ko";
  currentUiLang = lang;
  localStorage.setItem("tubescholar_ui_lang", lang);
  document.documentElement.lang = lang;

  applyI18n();
  window.dispatchEvent(new CustomEvent("tubescholar:lang_change", { detail: { lang } }));
}

function t(key, params) {
  const dict = TUBESCHOLAR_I18N[currentUiLang] || TUBESCHOLAR_I18N.ko;
  let text = dict[key] || TUBESCHOLAR_I18N.ko[key] || key;

  if (params && typeof params === "object") {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace(new RegExp(`\\{${k}\\}`, "g"), v);
    }
  }
  return text;
}

function applyI18n(root = document) {
  // 1. Text content
  root.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    if (!key) return;
    const translated = t(key);
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
      // Inputs usually don't use textContent
    } else {
      el.textContent = translated;
    }
  });

  // 2. HTML content (for elements containing formatting tags like <strong>, <span>)
  root.querySelectorAll("[data-i18n-html]").forEach(el => {
    const key = el.getAttribute("data-i18n-html");
    if (key) el.innerHTML = t(key);
  });

  // 3. Placeholders
  root.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key) el.setAttribute("placeholder", t(key));
  });

  // 4. Titles / tooltips
  root.querySelectorAll("[data-i18n-title]").forEach(el => {
    const key = el.getAttribute("data-i18n-title");
    if (key) el.setAttribute("title", t(key));
  });

  // 5. HTML document title
  if (root === document && TUBESCHOLAR_I18N[currentUiLang]?.app_title) {
    document.title = TUBESCHOLAR_I18N[currentUiLang].app_title;
  }
}

// Auto-initialize when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    document.documentElement.lang = currentUiLang;
    applyI18n();
  });
} else {
  document.documentElement.lang = currentUiLang;
  applyI18n();
}
