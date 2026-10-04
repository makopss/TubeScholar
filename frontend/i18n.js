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

    // 비디오 플레이어
    player_placeholder_title: "학습할 유튜브 영상 URL을 입력하거나 [📁 로컬 영상]을 선택하세요.",
    player_placeholder_desc: "타임스탬프 클릭 시 해당 위치로 영상이 즉시 점프합니다.",
    overlay_drag_hint: "마우스로 잡고 원하는 위치로 드래그할 수 있습니다 (더블클릭 시 하단 복원)",
    btn_prev_sub_title: "이전 자막 이동 (단축키: A)",
    btn_replay_sub_title: "현재 자막 반복 재생 (단축키: S)",
    btn_next_sub_title: "다음 자막 이동 (단축키: D)",

    // 상단 뷰 전환
    view_note: "학습 노트",
    view_subtitles: "전체 자막",
    label_source_track: "원문(자막 트랙)",
    label_target_lang: "번역 언어",
    label_sync_offset: "싱크",
    sync_offset_tooltip: "자막 싱크 미세조정 ([ : 0.1초 빠르게, ] : 0.1초 느리게, \\ : 초기화)",
    btn_sync_faster_title: "자막 0.1초 빠르게 표시 (단축키: [)",
    btn_sync_slower_title: "자막 0.1초 느리게 표시 (단축키: ])",
    btn_sync_reset_title: "싱크 초기화 (0.0초, 단축키: \\)",
    btn_sub_font_smaller_title: "자막 글자 작게",
    btn_sub_font_larger_title: "자막 글자 크게",
    btn_sub_autoscroll_title: "영상 재생 시 현재 자막으로 목록 자동 스크롤",

    // 자막 뷰 모드
    mode_original: "원문",
    mode_translated: "{lang} 번역",
    mode_bilingual: "{lang} 병기",
    btn_translate_request: "{lang} 번역 요청",
    btn_translate_stop: "⏹️ 번역 중단",
    btn_translate_retranslate: "🔄 {lang} 재번역",
    btn_translate_done: "✓ {lang} 번역 완료",
    btn_translate_same: "자막 준비 완료",
    btn_download_srt: "SRT 다운로드",
    btn_download_txt: "TXT 다운로드",
    search_subtitles_placeholder: "자막 검색 (원문 또는 번역문)...",
    no_subtitles_found: "일치하는 자막이 없습니다.",
    subtitles_waiting_analysis: "영상을 분석하거나 불러오면 자막이 여기에 표시됩니다.",

    // 노트 툴바 및 상태
    btn_fullscreen_reader: "집중 독서 모드",
    btn_audiobook: "오디오북",
    btn_copy_note: "복사",
    btn_edit_note: "편집",
    btn_save_note: "저장",
    status_model_used: "생성 모델",
    status_words: "글자 수",
    status_saved_time: "저장 일시",
    empty_note_title: "학습 노트를 생성하거나 불러오세요",
    empty_note_desc: "상단에서 [⚡ Gemini 자동 분석] 또는 [📋 구독 AI 연동]을 선택한 뒤 URL을 입력하거나 로컬 영상을 불러오세요.",

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

    // 보관함 모달
    library_title: "저장된 학습 노트 보관함",
    library_search_placeholder: "노트 제목 또는 채널명 검색...",
    library_count: "총 {count}개의 학습 노트",
    library_empty: "저장된 학습 노트가 없습니다.",
    library_load_btn: "열기",
    library_delete_btn: "삭제",

    // 설정 모달
    settings_title: "TubeScholar 시스템 설정",
    settings_gemini_title: "Gemini API 키 (학습 노트 생성 & 자막 번역)",
    settings_gemini_placeholder: "AI Studio에서 발급받은 Gemini API 키 입력",
    settings_gemini_help: "무료 API 키 발급받기 (Google AI Studio)",
    settings_groq_title: "Groq API 키 (로컬 영상 초고속 음성인식 Whisper STT)",
    settings_groq_placeholder: "Groq Console에서 발급받은 gsk_... 키 입력",
    settings_groq_help: "무료 Groq API 키 발급받기 (Groq Console)",
    settings_save_btn: "💾 설정 저장",
    settings_close_btn: "닫기",

    // 채널 모달
    channel_modal_title: "📺 채널 최근 영상 탐색",
    channel_url_placeholder: "유튜브 채널 URL (예: https://www.youtube.com/@channel)",
    channel_search_btn: "영상 불러오기",
    channel_count_label: "영상 수:",

    // 로컬 비디오 모달
    local_modal_title: "📁 내 PC 로컬 영상 및 자막 열기",
    local_video_label: "동영상 파일 (.mp4, .webm, .mkv 등)",
    local_sub_label: "자막 파일 (.srt, .vtt) (선택 사항)",
    local_analyze_btn: "로컬 영상 불러오기",

    // 독서 팝업 (Reader Mode)
    reader_toc_title: "📑 목차 목록",
    reader_font_smaller: "A-",
    reader_font_larger: "A+",
    reader_print: "🖨️ 인쇄",
    reader_close: "✕ 닫기",

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

    // Video Player
    player_placeholder_title: "Enter a YouTube video URL or select [📁 Local Video] to start studying.",
    player_placeholder_desc: "Clicking a timestamp jumps directly to that section in the video.",
    overlay_drag_hint: "Drag to move overlay anywhere (Double click to reset position)",
    btn_prev_sub_title: "Previous Subtitle (Shortcut: A)",
    btn_replay_sub_title: "Replay Current Subtitle (Shortcut: S)",
    btn_next_sub_title: "Next Subtitle (Shortcut: D)",

    // Top View Switching
    view_note: "Study Note",
    view_subtitles: "Subtitles",
    label_source_track: "Source Track",
    label_target_lang: "Target Language",
    label_sync_offset: "Sync",
    sync_offset_tooltip: "Fine-tune subtitle sync ([ : 0.1s faster, ] : 0.1s slower, \\ : reset)",
    btn_sync_faster_title: "0.1s faster (Shortcut: [)",
    btn_sync_slower_title: "0.1s slower (Shortcut: ])",
    btn_sync_reset_title: "Reset sync (0.0s, Shortcut: \\)",
    btn_sub_font_smaller_title: "Smaller subtitle text",
    btn_sub_font_larger_title: "Larger subtitle text",
    btn_sub_autoscroll_title: "Auto-scroll list to active subtitle while playing",

    // Subtitle View Modes
    mode_original: "Original",
    mode_translated: "{lang} Translation",
    mode_bilingual: "{lang} Bilingual",
    btn_translate_request: "Translate to {lang}",
    btn_translate_stop: "⏹️ Stop Translation",
    btn_translate_retranslate: "🔄 Re-translate to {lang}",
    btn_translate_done: "✓ {lang} Translated",
    btn_translate_same: "Subtitles Ready",
    btn_download_srt: "Download SRT",
    btn_download_txt: "Download TXT",
    search_subtitles_placeholder: "Search subtitles (original or translation)...",
    no_subtitles_found: "No matching subtitles found.",
    subtitles_waiting_analysis: "Subtitles will appear here once video is loaded or analyzed.",

    // Note Toolbar & Status
    btn_fullscreen_reader: "Reader Mode",
    btn_audiobook: "Audiobook",
    btn_copy_note: "Copy",
    btn_edit_note: "Edit",
    btn_save_note: "Save",
    status_model_used: "Model Used",
    status_words: "Characters",
    status_saved_time: "Saved At",
    empty_note_title: "Generate or load a study note",
    empty_note_desc: "Select [⚡ Gemini Auto Note] or [📋 Subscription AI Prompt] at the top, then enter a URL or load a local video.",

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

    // Library Modal
    library_title: "Saved Study Notes Library",
    library_search_placeholder: "Search note title or channel...",
    library_count: "Total {count} study notes",
    library_empty: "No saved study notes.",
    library_load_btn: "Open",
    library_delete_btn: "Delete",

    // Settings Modal
    settings_title: "TubeScholar Settings",
    settings_gemini_title: "Gemini API Key (Study Notes & Subtitle Translation)",
    settings_gemini_placeholder: "Enter Gemini API Key from Google AI Studio",
    settings_gemini_help: "Get Free API Key (Google AI Studio)",
    settings_groq_title: "Groq API Key (Fast Whisper STT for local videos)",
    settings_groq_placeholder: "Enter Groq API Key (gsk_...)",
    settings_groq_help: "Get Free Groq API Key (Groq Console)",
    settings_save_btn: "💾 Save Settings",
    settings_close_btn: "Close",

    // Channel Modal
    channel_modal_title: "📺 Explore Channel Videos",
    channel_url_placeholder: "YouTube Channel URL (e.g. https://www.youtube.com/@channel)",
    channel_search_btn: "Fetch Videos",
    channel_count_label: "Videos:",

    // Local Video Modal
    local_modal_title: "📁 Open Local Video File",
    local_video_label: "Video File (.mp4, .webm, .mkv, etc.)",
    local_sub_label: "Subtitle File (.srt, .vtt) (Optional)",
    local_analyze_btn: "Load Local Video",

    // Reader Mode Popup
    reader_toc_title: "📑 Table of Contents",
    reader_font_smaller: "A-",
    reader_font_larger: "A+",
    reader_print: "🖨️ Print",
    reader_close: "✕ Close",

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

    // ビデオプレイヤー
    player_placeholder_title: "学習するYouTube動画URLを入力するか、[📁 ローカル動画]を選択してください。",
    player_placeholder_desc: "タイムスタンプをクリックすると動画の該当位置に即座にジャンプします。",
    overlay_drag_hint: "ドラッグして好きな位置に移動できます（ダブルクリックで元の位置に戻す）",
    btn_prev_sub_title: "前の字幕へ移動 (ショートカット: A)",
    btn_replay_sub_title: "現在の字幕をリピート再生 (ショートカット: S)",
    btn_next_sub_title: "次の字幕へ移動 (ショートカット: D)",

    // 上部ビュー切り替え
    view_note: "学習ノート",
    view_subtitles: "全字幕",
    label_source_track: "原文（字幕トラック）",
    label_target_lang: "翻訳言語",
    label_sync_offset: "同期",
    sync_offset_tooltip: "字幕同期の微調整 ([ : 0.1秒早く, ] : 0.1秒遅く, \\ : リセット)",
    btn_sync_faster_title: "字幕を0.1秒早く表示 (ショートカット: [)",
    btn_sync_slower_title: "字幕を0.1秒遅く表示 (ショートカット: ])",
    btn_sync_reset_title: "同期リセット (0.0秒, ショートカット: \\)",
    btn_sub_font_smaller_title: "字幕の文字を小さく",
    btn_sub_font_larger_title: "字幕の文字を大きく",
    btn_sub_autoscroll_title: "再生中に現在の字幕位置へ自動スクロール",

    // 字幕ビューモード
    mode_original: "原文",
    mode_translated: "{lang} 翻訳",
    mode_bilingual: "{lang} 併記",
    btn_translate_request: "{lang} 翻訳をリクエスト",
    btn_translate_stop: "⏹️ 翻訳を中断",
    btn_translate_retranslate: "🔄 {lang} 再翻訳",
    btn_translate_done: "✓ {lang} 翻訳完了",
    btn_translate_same: "字幕準備完了",
    btn_download_srt: "SRTダウンロード",
    btn_download_txt: "TXTダウンロード",
    search_subtitles_placeholder: "字幕検索（原文または翻訳文）...",
    no_subtitles_found: "一致する字幕が見つかりません。",
    subtitles_waiting_analysis: "動画を読み込むか分析すると字幕がここに表示されます。",

    // ノートツールバー＆ステータス
    btn_fullscreen_reader: "集中読書モード",
    btn_audiobook: "オーディオブック",
    btn_copy_note: "コピー",
    btn_edit_note: "編集",
    btn_save_note: "保存",
    status_model_used: "生成モデル",
    status_words: "文字数",
    status_saved_time: "保存日時",
    empty_note_title: "学習ノートを生成または読み込んでください",
    empty_note_desc: "上部で [⚡ Gemini 自動分析] または [📋 サブスクAI連携] を選択し、URLを入力するかローカル動画を読み込んでください。",

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

    // 保管庫モーダル
    library_title: "保存済み学習ノート保管庫",
    library_search_placeholder: "ノートタイトルまたはチャンネル名で検索...",
    library_count: "合計 {count} 件の学習ノート",
    library_empty: "保存された学習ノートはありません。",
    library_load_btn: "開く",
    library_delete_btn: "削除",

    // 設定モーダル
    settings_title: "TubeScholar システム設定",
    settings_gemini_title: "Gemini APIキー（学習ノート生成＆字幕翻訳）",
    settings_gemini_placeholder: "Google AI Studioで取得したGemini APIキーを入力",
    settings_gemini_help: "無料APIキーを取得（Google AI Studio）",
    settings_groq_title: "Groq APIキー（ローカル動画用 超高速Whisper STT）",
    settings_groq_placeholder: "Groq Consoleで取得したgsk_...キーを入力",
    settings_groq_help: "無料Groq APIキーを取得（Groq Console）",
    settings_save_btn: "💾 設定を保存",
    settings_close_btn: "閉じる",

    // チャンネルモーダル
    channel_modal_title: "📺 チャンネル最新動画を探索",
    channel_url_placeholder: "YouTubeチャンネルURL（例: https://www.youtube.com/@channel）",
    channel_search_btn: "動画を取得",
    channel_count_label: "動画数:",

    // ローカル動画モーダル
    local_modal_title: "📁 PCのローカル動画・字幕を開く",
    local_video_label: "動画ファイル (.mp4, .webm, .mkv 等)",
    local_sub_label: "字幕ファイル (.srt, .vtt) (任意)",
    local_analyze_btn: "ローカル動画を読み込む",

    // 読書モードポップアップ (Reader Mode)
    reader_toc_title: "📑 目次リスト",
    reader_font_smaller: "A-",
    reader_font_larger: "A+",
    reader_print: "🖨️ 印刷",
    reader_close: "✕ 閉じる",

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

  // 2. Placeholders
  root.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key) el.setAttribute("placeholder", t(key));
  });

  // 3. Titles / tooltips
  root.querySelectorAll("[data-i18n-title]").forEach(el => {
    const key = el.getAttribute("data-i18n-title");
    if (key) el.setAttribute("title", t(key));
  });

  // 4. HTML document title
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
