// TubeScholar Frontend Application Logic (Dual-Mode, Local Video & Live Editor Edition)

// 🔒 로컬 서버 CSRF 방어: 같은 출처의 /api 요청에 전용 헤더를 자동 첨부
// (다른 웹사이트는 이 커스텀 헤더를 붙여 127.0.0.1 로 요청할 수 없음 → 서버가 403 거부)
(() => {
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const url = typeof input === "string" ? input : (input && input.url) || String(input || "");
    if (url.startsWith("/api/") || url.startsWith(location.origin + "/api/")) {
      const base = init.headers || (input instanceof Request ? input.headers : undefined);
      const headers = new Headers(base);
      headers.set("X-TubeScholar", "1");
      init = { ...init, headers };
    }
    return nativeFetch(input, init);
  };
})();

let ytPlayer = null;
let currentVideoId = null;
let currentNoteId = null;
let currentMarkdown = "";
let currentVideoInfo = null;
let currentAbortController = null;
let currentMode = "gemini"; // 'gemini' or 'subscription'
let isEditing = false;
let isLocalVideo = false;
let currentSubtitles = [];
let currentSubLang = "original"; // 'original', 'ko', 'bilingual'
let currentActiveView = "note"; // 'note' or 'subtitles'
let isCcEnabled = true;
let currentFontScale = 100; // 70% ~ 160%
let activeSubtitleIndex = -1;
let subtitleRowByIdx = new Map(); // 자막 인덱스 → 목록 행 요소 (renderSubtitlesList 에서 갱신)
let highlightedRowIdx = -1;
let lastOverlayRenderKey = ""; // updateActiveSubtitle 의 중복 DOM 갱신 방지용
let timeSyncTimer = null;
let isTranslatingSubtitles = false;
let transAbortController = null;
let isKoreanContent = false; // 호환용 (isSameLanguage와 동기화)
let isSameLanguage = false; // 원문 언어와 번역 대상 언어가 동일한지 여부
let currentTargetLang = localStorage.getItem("tubescholar_target_lang") || "ko";
let currentSourceLang = null;
let currentOriginalLang = null;
let currentTranslationSource = null; // 'same' | 'youtube' | 'gemini' | null
let currentTranslationTrack = null;
let currentTracks = [];
let supportedTargetLanguages = [];
let isSubtitleAutoScroll = localStorage.getItem("tubescholar_sub_autoscroll") !== "false";

const FALLBACK_TARGET_LANGUAGES = [
  { code: "ko", name: "한국어" },
  { code: "en", name: "English" },
  { code: "ja", name: "日本語" },
  { code: "zh-Hans", name: "中文(简体)" },
  { code: "zh-Hant", name: "中文(繁體)" },
  { code: "es", name: "Español" },
  { code: "fr", name: "Français" },
  { code: "de", name: "Deutsch" },
  { code: "pt", name: "Português" },
  { code: "ru", name: "Русский" },
  { code: "it", name: "Italiano" },
  { code: "vi", name: "Tiếng Việt" },
  { code: "th", name: "ไทย" },
  { code: "id", name: "Bahasa Indonesia" },
  { code: "ar", name: "العربية" },
  { code: "hi", name: "हिन्दी" },
  { code: "tr", name: "Türkçe" }
];

function getTargetLangName(code) {
  const c = code || currentTargetLang || "ko";
  const list = (supportedTargetLanguages && supportedTargetLanguages.length > 0) ? supportedTargetLanguages : FALLBACK_TARGET_LANGUAGES;
  const found = list.find(l => l.code === c);
  return found ? found.name : c;
}

window.onYouTubeIframeAPIReady = function() {
  console.log("YouTube IFrame API Ready");
};

function stripFrontmatter(md) {
  if (!md) return "";
  return md.replace(/^---\s*[\r\n]+[\s\S]*?[\r\n]+---\s*[\r\n]*/, '').trim();
}

function escapeHtmlStr(str) {
  if (!str) return '';
  return String(str).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
}

function initYouTubePlayer(videoId, onReadyCallback) {
  isLocalVideo = false;
  isKoreanContent = false;
  document.getElementById("local-video-player").classList.add("hidden");
  document.getElementById("local-video-player").pause();

  const placeholder = document.getElementById("youtube-player-placeholder");
  if (placeholder) placeholder.style.display = "none";

  const playerEl = document.getElementById("player");
  playerEl.classList.remove("hidden");

  if (ytPlayer && typeof ytPlayer.destroy === 'function') {
    try { ytPlayer.destroy(); } catch (e) {}
  }

  ytPlayer = new YT.Player("player", {
    videoId: videoId,
    playerVars: {
      autoplay: 1,
      modestbranding: 1,
      rel: 0,
      enablejsapi: 1,
      fs: 0
    },
    events: {
      onReady: (event) => {
        document.getElementById("player-controls").classList.remove("hidden");
        if (onReadyCallback) onReadyCallback(event);
      }
    }
  });
}

function initLocalVideoPlayer(videoFile) {
  isLocalVideo = true;
  if (ytPlayer && typeof ytPlayer.pauseVideo === 'function') {
    try { ytPlayer.pauseVideo(); } catch (e) {}
  }
  document.getElementById("player").classList.add("hidden");

  const placeholder = document.getElementById("youtube-player-placeholder");
  if (placeholder) placeholder.style.display = "none";

  const localPlayer = document.getElementById("local-video-player");
  localPlayer.classList.remove("hidden");
  if (localPlayer.src && localPlayer.src.startsWith("blob:")) {
    try { URL.revokeObjectURL(localPlayer.src); } catch (e) {}
  }
  localPlayer.src = URL.createObjectURL(videoFile);
  localPlayer.play();
  document.getElementById("player-controls").classList.remove("hidden");
}

function seekVideo(seconds) {
  if (isLocalVideo) {
    const localPlayer = document.getElementById("local-video-player");
    if (localPlayer) {
      localPlayer.currentTime = seconds;
      localPlayer.play();
    }
  } else {
    if (ytPlayer && typeof ytPlayer.seekTo === 'function') {
      ytPlayer.seekTo(seconds, true);
      if (typeof ytPlayer.playVideo === 'function') ytPlayer.playVideo();
    }
  }
  updateActiveSubtitle(seconds);
}

function parseTimeToSeconds(timeStr) {
  const parts = timeStr.trim().split(':').map(Number);
  if (parts.length === 2) {
    return parts[0] * 60 + parts[1];
  } else if (parts.length === 3) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2];
  }
  return 0;
}

function sanitizeHtml(html) {
  // AI 생성/붙여넣기 노트에 섞인 악성 HTML(스크립트, onerror 등) 제거
  if (window.DOMPurify) return DOMPurify.sanitize(html);
  // DOMPurify 로드 실패 시 안전하게 전부 텍스트로 처리
  const d = document.createElement("div");
  d.textContent = html;
  return d.innerHTML;
}

function processMarkdownHtml(html) {
  const tempDiv = document.createElement("div");
  tempDiv.innerHTML = sanitizeHtml(html);

  const timeRegex = /\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g;
  const timeTest = /\[(\d{1,2}:\d{2}(?::\d{2})?)\]/; // test() 용 (g 플래그의 lastIndex 부작용 방지)
  const walker = document.createTreeWalker(tempDiv, NodeFilter.SHOW_TEXT, null, false);
  const textNodes = [];
  while (walker.nextNode()) {
    textNodes.push(walker.currentNode);
  }

  for (const node of textNodes) {
    if (timeTest.test(node.nodeValue)) {
      const parent = node.parentNode;
      if (parent && parent.tagName !== 'CODE' && parent.tagName !== 'PRE') {
        const span = document.createElement('span');
        span.innerHTML = escapeHtmlStr(node.nodeValue).replace(timeRegex, (match, p1) => {
          const secs = parseTimeToSeconds(p1);
          return `<button type="button" class="timestamp-tag" data-seconds="${secs}" title="${p1} 구간으로 이동">${p1}</button>`;
        });
        parent.replaceChild(span, node);
      }
    }
  }

  const blockquotes = tempDiv.querySelectorAll("blockquote");
  blockquotes.forEach(bq => {
    const text = bq.innerText;
    if (text.includes("Deep Dive") || text.includes("지식 보충") || text.includes("심화 지식")) {
      bq.classList.add("deep-dive-box");
    } else if (text.includes("키워드 깊이 읽기") || text.includes("Keyword Deep Dive")) {
      bq.classList.add("keyword-dive-box");
    } else if (text.includes("치명적 실수") || text.includes("주의사항") || text.includes("Warning") || text.includes("Pro-Tip")) {
      bq.classList.add("warning-callout-box");
    }
  });

  return tempDiv.innerHTML;
}

function renderMarkdownNote(markdownText, engineInfo = "", noteId = null) {
  if (noteId) currentNoteId = noteId;
  const cleanMd = stripFrontmatter(markdownText);
  currentMarkdown = cleanMd;

  const rawHtml = marked.parse(cleanMd);
  const processedHtml = processMarkdownHtml(rawHtml);

  const container = document.getElementById("note-content");
  container.innerHTML = processedHtml;
  container.classList.remove("hidden");
  document.getElementById("empty-note-placeholder").classList.add("hidden");
  document.getElementById("status-tag").classList.remove("hidden");

  if (engineInfo) {
    const engineTag = document.getElementById("engine-tag");
    engineTag.textContent = engineInfo;
    engineTag.classList.remove("hidden");
  }

  // 집중 독서 팝업 모달이 켜져 있을 경우 본문, 목차 및 문서 제목 자동 갱신
  if (typeof isReaderPopupOpen !== 'undefined' && isReaderPopupOpen) {
    const docTitle = document.getElementById("reader-popup-title");
    if (docTitle) docTitle.textContent = currentVideoInfo?.title || "학습 노트 집중 독서";
    const popupArticle = document.getElementById("reader-popup-article");
    if (popupArticle) popupArticle.innerHTML = processedHtml;
    if (typeof generateReaderPopupToc === 'function') generateReaderPopupToc();
  }

  // 에디터에도 최신 내용 동기화
  document.getElementById("note-editor-textarea").value = cleanMd;

  // 타임스탬프 클릭 바인딩
  const timestampBtns = container.querySelectorAll(".timestamp-tag");
  timestampBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const seconds = parseFloat(btn.getAttribute("data-seconds"));
      seekVideo(seconds);
    });
  });
}

function displayVideoMetadata(info) {
  currentVideoInfo = info;
  document.getElementById("video-meta-card").classList.remove("hidden");
  document.getElementById("meta-channel").textContent = info.channel || "영상 정보";
  document.getElementById("meta-title").textContent = info.title || "제목 없음";
  document.getElementById("meta-duration").textContent = info.duration_str || "00:00";
  document.getElementById("meta-desc").textContent = info.description || "";
  
  const origLink = document.getElementById("meta-orig-link");
  if (info.video_type === 'local' || !info.video_id) {
    origLink.classList.add("hidden");
  } else {
    origLink.classList.remove("hidden");
    origLink.href = `https://www.youtube.com/watch?v=${info.video_id}`;
  }
}

// ==========================================
// 미디어 컨텍스트 전환 (영상/노트 전환 시 이전 작업 결과가 섞이는 문제 방지)
// ==========================================
let mediaGeneration = 0;

function switchMediaContext(videoId, noteId) {
  mediaGeneration++;
  // 이전 영상의 번역이 진행 중이면 중단 (완료 시 새 영상 자막을 덮어쓰는 사고 방지)
  if (isTranslatingSubtitles || transAbortController) {
    abortTranslation();
    const modal = document.getElementById("trans-progress-modal");
    if (modal) modal.classList.add("hidden");
  }
  currentVideoId = videoId || null;
  currentNoteId = noteId || null;
  refreshSyncBadge(true);
  return mediaGeneration;
}

function isCurrentMedia(gen) {
  return gen === mediaGeneration;
}

function localMediaKey(file, fallbackName) {
  // 같은 로컬 파일은 같은 키 → 싱크 보정값이 파일별로 유지됨
  if (file) return `local_${file.name}_${file.size}`;
  return `local_${fallbackName || "file"}`;
}

function setSubtitles(subs) {
  currentSubtitles = subs || [];
  activeSubtitleIndex = -1;
  const badge = document.getElementById("subtitle-badge");
  const countText = document.getElementById("sub-count-text");
  if (badge) {
    if (currentSubtitles.length > 0) {
      badge.textContent = currentSubtitles.length;
      badge.classList.remove("hidden");
    } else {
      badge.classList.add("hidden");
    }
  }
  if (countText) {
    countText.textContent = `${currentSubtitles.length}개 대사`;
  }
  const searchInput = document.getElementById("subtitle-search-input");
  renderSubtitlesList(searchInput ? searchInput.value : "");

  // 번역 요청 버튼 상태 동기화 (자동 프리페치는 제거하여 Gemini API 소모 방지)
  updateTranslationButtonState();
}

async function initLanguages() {
  try {
    const res = await fetch("/api/languages");
    if (res.ok) {
      const data = await res.json();
      if (Array.isArray(data.target_languages) && data.target_languages.length > 0) {
        supportedTargetLanguages = data.target_languages;
      }
    }
  } catch (e) {
    console.warn("Failed to load /api/languages, using fallbacks:", e);
  }
  if (!supportedTargetLanguages || supportedTargetLanguages.length === 0) {
    supportedTargetLanguages = FALLBACK_TARGET_LANGUAGES;
  }
  renderTargetLangSelect();
  renderSourceLangSelect();
  updateLangLabels();
}

function renderTargetLangSelect() {
  const sel = document.getElementById("sub-target-lang");
  if (!sel) return;
  const list = (supportedTargetLanguages && supportedTargetLanguages.length > 0) ? supportedTargetLanguages : FALLBACK_TARGET_LANGUAGES;
  const prefix = typeof t === "function" ? t("label_target_lang") : "번역";
  
  sel.innerHTML = list.map(item => {
    const isSel = item.code === currentTargetLang ? "selected" : "";
    return `<option value="${escapeHtmlStr(item.code)}" ${isSel}>${prefix}: ${escapeHtmlStr(item.name)}</option>`;
  }).join("");
}

function renderSourceLangSelect() {
  const sel = document.getElementById("sub-source-lang");
  if (!sel) return;
  const srcLabel = typeof t === "function" ? t("label_source_track") : "원문";

  if (isLocalVideo || !currentTracks || currentTracks.length === 0) {
    if (isLocalVideo) {
      sel.innerHTML = `<option value="">${srcLabel}: Local</option>`;
      sel.disabled = true;
    } else {
      sel.innerHTML = `<option value="">${srcLabel}: Auto</option>`;
      sel.disabled = false;
    }
    return;
  }

  sel.disabled = false;
  let html = `<option value="">${srcLabel}: Auto (${escapeHtmlStr(currentOriginalLang || "detect")})</option>`;
  currentTracks.forEach(t => {
    const isSel = (currentSourceLang && (currentSourceLang === t.value || currentSourceLang === t.code)) ? "selected" : "";
    html += `<option value="${escapeHtmlStr(t.value)}" ${isSel}>${escapeHtmlStr(t.name)}</option>`;
  });
  sel.innerHTML = html;
}

function updateLangLabels() {
  const targetName = getTargetLangName(currentTargetLang);
  const koLabel = document.getElementById("sub-lang-ko-label");
  const biLabel = document.getElementById("sub-lang-bi-label");
  const ctrlKo = document.getElementById("ctrl-sub-ko-label");

  if (koLabel) koLabel.textContent = typeof t === "function" ? t("mode_translated", { lang: targetName }) : `${targetName} 번역`;
  if (biLabel) biLabel.textContent = typeof t === "function" ? t("mode_bilingual", { lang: targetName }) : (targetName === "한국어" ? "한/영 병기" : `${targetName} 병기`);
  if (ctrlKo) ctrlKo.textContent = targetName.length > 3 ? targetName.slice(0, 3) : targetName;
}

function applyLanguageState(payload) {
  if (!payload) return;

  if (payload.target_lang) {
    currentTargetLang = payload.target_lang;
    try { localStorage.setItem("tubescholar_target_lang", currentTargetLang); } catch (e) {}
  }
  if (payload.source_lang) {
    currentSourceLang = payload.source_lang;
  } else if (payload.transcript_language) {
    currentSourceLang = payload.transcript_language;
  }
  if (payload.original_lang) {
    currentOriginalLang = payload.original_lang;
  }
  if (payload.translation_source !== undefined) {
    currentTranslationSource = payload.translation_source;
  }
  if (payload.translation_track !== undefined) {
    currentTranslationTrack = payload.translation_track;
  }
  if (Array.isArray(payload.tracks)) {
    currentTracks = payload.tracks;
  }

  // 동일 언어 판별: 명시적 "same" 이거나, 한국어 원문이면서 타겟이 한국어인 경우
  isSameLanguage = (currentTranslationSource === "same") || (payload.is_korean && currentTargetLang === "ko");
  isKoreanContent = isSameLanguage;

  // 원문과 번역 언어가 동일한 경우 자막 배열의 ko_text에 text를 복사하여 즉시 표시 지원
  if (isSameLanguage && Array.isArray(currentSubtitles)) {
    currentSubtitles.forEach(s => {
      if (!s.ko_text) s.ko_text = s.text;
    });
  }

  renderTargetLangSelect();
  renderSourceLangSelect();
  updateLangLabels();

  // 메타데이터 카드 자막 상태 라벨 갱신
  const metaLang = document.getElementById("meta-lang");
  if (metaLang) {
    const srcName = currentOriginalLang ? getTargetLangName(currentOriginalLang) : (payload.transcript_language || '원문');
    const genTag = payload.is_generated ? '(자동)' : '(공식)';
    const tgtName = getTargetLangName(currentTargetLang);

    if (isSameLanguage) {
      metaLang.textContent = `자막: ${srcName} ${genTag} (원문과 동일)`;
    } else if (currentTranslationSource === "youtube") {
      metaLang.textContent = `자막: ${srcName} ${genTag} → ${tgtName} (YouTube 공식)`;
    } else if (currentTranslationSource === "gemini") {
      metaLang.textContent = `자막: ${srcName} ${genTag} → ${tgtName} (Gemini 번역)`;
    } else {
      const hasKo = currentSubtitles && currentSubtitles.some(s => s.ko_text && s.ko_text.trim() !== "");
      if (hasKo) {
        metaLang.textContent = `자막: ${srcName} ${genTag} → ${tgtName} (번역됨)`;
      } else {
        metaLang.textContent = `자막: ${srcName} ${genTag} (번역 대기)`;
      }
    }
  }

  updateTranslationButtonState();
}

async function reloadSubtitles(opts = {}) {
  if (!currentVideoId || isLocalVideo) return;
  if (isTranslatingSubtitles) {
    alert("현재 번역 작업이 진행 중입니다. 완료되거나 취소된 후 언어를 변경해주세요.");
    return;
  }

  const gen = mediaGeneration;
  const newSource = opts.source_lang !== undefined ? opts.source_lang : currentSourceLang;
  const newTarget = opts.target_lang !== undefined ? opts.target_lang : currentTargetLang;

  const btn = document.getElementById("request-sub-translate-btn");
  const text = document.getElementById("trans-btn-text");
  if (text) text.textContent = "자막 조회 중...";

  try {
    const res = await fetch("/api/subtitles/reload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        video_id: currentVideoId,
        note_id: currentNoteId,
        source_lang: newSource,
        target_lang: newTarget
      })
    });
    const d = await res.json();
    if (!isCurrentMedia(gen)) return;

    if (!res.ok) {
      throw new Error(d.detail || "자막 갱신 실패");
    }

    if (d.success && Array.isArray(d.subtitles)) {
      const reloadHasTrans = d.subtitles.some(s => s.ko_text && s.ko_text.trim() !== "");
      if (reloadHasTrans && currentSubLang === "original") {
        currentSubLang = "bilingual";
        updateSubLangButtons(currentSubLang);
      }
      setSubtitles(d.subtitles);
      applyLanguageState(d);

      let curTime = -1;
      if (ytPlayer && typeof ytPlayer.getCurrentTime === 'function') {
        curTime = ytPlayer.getCurrentTime();
      }
      if (curTime >= 0) updateActiveSubtitle(curTime);
    }
  } catch (err) {
    alert("자막 언어 갱신 오류: " + err.message);
    updateTranslationButtonState();
  }
}

function updateTranslationButtonState() {
  const btn = document.getElementById("request-sub-translate-btn");
  if (!btn) return;
  const icon = document.getElementById("trans-btn-icon");
  const text = document.getElementById("trans-btn-text");
  const spinner = document.getElementById("trans-loading-spinner");
  const targetName = getTargetLangName(currentTargetLang);

  if (isTranslatingSubtitles) {
    btn.disabled = true;
    btn.className = "px-2.5 py-1 bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded-lg text-xs font-semibold cursor-wait flex items-center space-x-1.5 shadow-sm";
    if (text) text.textContent = `${targetName}...`;
    if (icon) icon.textContent = "⏳";
    if (spinner) spinner.classList.remove("hidden");
    return;
  }

  if (isSameLanguage || currentTranslationSource === "same") {
    btn.disabled = true;
    btn.className = "px-2.5 py-1 bg-sky-500/15 text-sky-400 border border-sky-500/30 rounded-lg text-xs font-semibold cursor-default flex items-center space-x-1.5 shadow-sm opacity-80";
    if (text) text.textContent = typeof t === "function" ? t("btn_translate_same") : "자막 준비 완료";
    if (icon) icon.textContent = "🆗";
    if (spinner) spinner.classList.add("hidden");
    btn.title = `원문과 번역 대상 언어가 ${targetName}(으)로 동일합니다.`;
    return;
  }

  if (!currentSubtitles || currentSubtitles.length === 0) {
    btn.disabled = true;
    btn.className = "px-2.5 py-1 bg-slate-800 text-slate-500 border border-slate-700 rounded-lg text-xs font-semibold cursor-not-allowed flex items-center space-x-1.5 shadow-sm opacity-60";
    if (text) text.textContent = typeof t === "function" ? t("no_subtitles_found") : "자막 없음";
    if (icon) icon.textContent = "⚡";
    if (spinner) spinner.classList.add("hidden");
    return;
  }

  if (currentTranslationSource === "youtube") {
    btn.disabled = false;
    btn.className = "px-2.5 py-1 bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border border-emerald-500/30 rounded-lg text-xs font-semibold transition flex items-center space-x-1.5 shadow-sm cursor-pointer";
    if (text) text.textContent = `📺 YouTube ${targetName}`;
    if (icon) icon.textContent = "📺";
    if (spinner) spinner.classList.add("hidden");
    btn.title = `YouTube 공식 ${targetName} 자막이 적용되었습니다. 클릭하면 Gemini로 다시 번역할 수 있습니다.`;
    return;
  }

  const hasKo = currentSubtitles.some(s => s.ko_text && s.ko_text.trim() !== "");
  if (hasKo || currentTranslationSource === "gemini") {
    btn.disabled = false;
    btn.className = "px-2.5 py-1 bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-400 border border-emerald-500/30 rounded-lg text-xs font-semibold transition flex items-center space-x-1.5 shadow-sm cursor-pointer";
    if (text) text.textContent = typeof t === "function" ? t("btn_translate_retranslate", { lang: targetName }) : `${targetName} 재번역`;
    if (icon) icon.textContent = "🔄";
    if (spinner) spinner.classList.add("hidden");
    btn.title = `${targetName} 번역이 완료된 상태입니다. 클릭하면 새로 다시 번역합니다.`;
  } else {
    btn.disabled = false;
    btn.className = "px-2.5 py-1 bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/40 rounded-lg text-xs font-semibold transition flex items-center space-x-1.5 shadow-sm cursor-pointer";
    if (text) text.textContent = typeof t === "function" ? t("btn_translate_request", { lang: targetName }) : `${targetName} 번역 요청`;
    if (icon) icon.textContent = "⚡";
    if (spinner) spinner.classList.add("hidden");
    btn.title = `Gemini를 호출하여 ${targetName} 번역을 명시적으로 생성합니다 (API 사용)`;
  }
}

function showTranslationModal() {
  const modal = document.getElementById("trans-progress-modal");
  if (!modal) return;
  modal.classList.remove("hidden");
  
  const bar = document.getElementById("trans-progress-bar");
  const percent = document.getElementById("trans-progress-percent");
  const label = document.getElementById("trans-progress-label");
  const logBox = document.getElementById("trans-log-container");
  const abortBtn = document.getElementById("abort-trans-btn");
  const cancelBtn = document.getElementById("cancel-trans-btn");
  const completeBtn = document.getElementById("complete-trans-btn");

  if (bar) bar.style.width = "0%";
  if (percent) percent.textContent = "0%";
  if (label) label.textContent = "번역 작업 초기화 중...";
  if (logBox) logBox.innerHTML = `<div class="text-slate-500">[시작] 번역 준비 중입니다...</div>`;
  if (abortBtn) abortBtn.classList.remove("hidden");
  if (cancelBtn) cancelBtn.classList.add("hidden");
  if (completeBtn) completeBtn.classList.add("hidden");
}

function closeTranslationModal() {
  if (isTranslatingSubtitles) {
    const confirmCancel = confirm("현재 번역 작업이 진행 중입니다.\n번역을 취소하고 창을 닫으시겠습니까?");
    if (confirmCancel) {
      abortTranslation();
    } else {
      return;
    }
  }
  const modal = document.getElementById("trans-progress-modal");
  if (modal) modal.classList.add("hidden");
}

function abortTranslation() {
  if (transAbortController) {
    try {
      transAbortController.abort();
    } catch (e) {}
    transAbortController = null;
  }
  appendTransLog("🛑 사용자에 의해 자막 번역 요청이 취소되었습니다.", "warn");
  isTranslatingSubtitles = false;
  updateTranslationButtonState();

  const abortBtn = document.getElementById("abort-trans-btn");
  const cancelBtn = document.getElementById("cancel-trans-btn");
  if (abortBtn) abortBtn.classList.add("hidden");
  if (cancelBtn) cancelBtn.classList.remove("hidden");

  const labelEl = document.getElementById("trans-progress-label");
  if (labelEl) labelEl.textContent = "번역 작업이 취소되었습니다.";
}

function appendTransLog(message, type = "info") {
  const logBox = document.getElementById("trans-log-container");
  if (!logBox) return;

  const now = new Date();
  const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;

  let colorClass = "text-slate-300";
  let prefix = "ℹ️";
  if (type === "success") {
    colorClass = "text-emerald-400 font-semibold";
    prefix = "✓";
  } else if (type === "warn") {
    colorClass = "text-amber-400";
    prefix = "⚠️";
  } else if (type === "error") {
    colorClass = "text-rose-400 font-semibold";
    prefix = "❌";
  } else if (type === "progress") {
    colorClass = "text-sky-300";
    prefix = "⚡";
  }

  const row = document.createElement("div");
  row.className = `${colorClass} text-[11px] leading-relaxed flex items-start space-x-1.5`;
  row.innerHTML = `<span class="text-slate-600 font-mono flex-shrink-0">[${timeStr}]</span> <span class="flex-shrink-0">${prefix}</span> <span class="break-words flex-1">${escapeHtml(message)}</span>`;
  
  logBox.appendChild(row);
  logBox.scrollTop = logBox.scrollHeight;
}

async function requestTranslation(force = false) {
  // 이 번역이 시작된 시점의 영상/노트 (도중에 전환되면 결과를 버림)
  const gen = mediaGeneration;
  const targetName = getTargetLangName(currentTargetLang);

  // 1. 자막 데이터 유무 확인 및 자동 복구 시도
  if (!currentSubtitles || currentSubtitles.length === 0) {
    if (currentNoteId || currentVideoId) {
      showTranslationModal();
      appendTransLog("현재 메모리에 자막이 없어 서버에서 자막 데이터를 조회합니다...", "info");
      try {
        const fetchRes = await fetch("/api/subtitles", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            video_id: currentVideoId,
            note_id: currentNoteId,
            target_lang: currentTargetLang
          })
        });
        const d = await fetchRes.json();
        if (!isCurrentMedia(gen)) return false;
        if (d.success && d.subtitles && d.subtitles.length > 0) {
          setSubtitles(d.subtitles);
          applyLanguageState(d);
          appendTransLog(`서버에서 자막 ${d.subtitles.length}개를 성공적으로 불러왔습니다.`, "success");
        } else {
          appendTransLog("해당 영상의 자막 데이터를 찾지 못했습니다.", "error");
          alert("번역할 자막 데이터가 없습니다. 먼저 영상을 분석하거나 자막을 불러와주세요.");
          closeTranslationModal();
          return false;
        }
      } catch (err) {
        appendTransLog("자막 조회 실패: " + err.message, "error");
        closeTranslationModal();
        return false;
      }
    } else {
      alert("번역할 자막 데이터가 없습니다. 먼저 영상이나 자막을 불러와주세요.");
      return false;
    }
  }

  if (isTranslatingSubtitles) {
    showTranslationModal();
    appendTransLog("이미 번역 작업이 진행 중입니다.", "warn");
    return false;
  }

  const hasKo = currentSubtitles.some(s => s.ko_text && s.ko_text.trim() !== "");
  if (hasKo && !force) {
    const retrans = confirm(`이미 ${targetName} 번역이 생성되어 있습니다.\nGemini에 다시 번역을 요청하시겠습니까? (API 사용량이 발생합니다)`);
    if (!retrans) return false;
  }

  isTranslatingSubtitles = true;
  updateTranslationButtonState();
  showTranslationModal();

  const myController = new AbortController();
  transAbortController = myController;

  const bar = document.getElementById("trans-progress-bar");
  const percentEl = document.getElementById("trans-progress-percent");
  const labelEl = document.getElementById("trans-progress-label");
  const completeBtn = document.getElementById("complete-trans-btn");

  try {
    appendTransLog(`Gemini [${targetName}] 자막 번역 스트리밍 연결을 시작합니다...`, "info");

    const res = await fetch("/api/subtitles/translate-stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: myController.signal,
      body: JSON.stringify({
        subtitles: currentSubtitles,
        translate_ko: true,
        note_id: currentNoteId,
        video_id: currentVideoId,
        title: currentVideoInfo?.title || "",
        target_lang: currentTargetLang
      })
    });

    if (!res.ok) {
      throw new Error(`서버 응답 오류 (HTTP ${res.status})`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let translationDone = false;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop(); // 미완성 청크 유지

      for (const block of parts) {
        if (!block.trim()) continue;
        const line = block.trim();
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.substring(6));
            // 번역 도중 다른 영상/노트로 전환됐다면 이 결과는 적용하지 않음
            if (!isCurrentMedia(gen)) continue;
            
            if (data.type === "start") {
              if (labelEl) labelEl.textContent = `총 ${data.total_count}개 대사 번역 준비 완료 (${data.total_batches}개 배치)`;
              appendTransLog(data.message, "info");
            } else if (data.type === "progress") {
              const p = data.percent || 0;
              if (bar) bar.style.width = `${p}%`;
              if (percentEl) percentEl.textContent = `${p}%`;
              if (labelEl) labelEl.textContent = `번역 진행 중: [${data.batch_index}/${data.total_batches} 배치]`;
              appendTransLog(data.message, "progress");
            } else if (data.type === "log") {
              appendTransLog(data.message, data.level || "info");
            } else if (data.type === "cancelled") {
              appendTransLog(data.message, "warn");
              if (labelEl) labelEl.textContent = "번역 작업이 취소되었습니다.";
              if (data.subtitles && data.subtitles.length > 0) {
                currentSubtitles = data.subtitles;
                const searchInput = document.getElementById("subtitle-search-input");
                renderSubtitlesList(searchInput ? searchInput.value : "");
              }
            } else if (data.type === "complete") {
              translationDone = true;
              currentTranslationSource = "gemini";
              if (bar) bar.style.width = "100%";
              if (percentEl) percentEl.textContent = "100%";
              if (labelEl) labelEl.textContent = "번역 완료!";
              appendTransLog(data.message, "success");

              if (data.subtitles && data.subtitles.length > 0) {
                currentSubtitles = data.subtitles;
                applyLanguageState({
                  target_lang: currentTargetLang,
                  translation_source: "gemini"
                });
                const searchInput = document.getElementById("subtitle-search-input");
                renderSubtitlesList(searchInput ? searchInput.value : "");

                let curTime = -1;
                if (isLocalVideo) {
                  const v = document.getElementById("local-video-player");
                  if (v) curTime = v.currentTime;
                } else if (ytPlayer && typeof ytPlayer.getCurrentTime === 'function') {
                  curTime = ytPlayer.getCurrentTime();
                }
                if (curTime >= 0) updateActiveSubtitle(curTime);

                // 현재 언어가 원문인 경우 자동으로 병기 모드로 전환해 결과 보여줌
                if (currentSubLang === "original") {
                  currentSubLang = "bilingual";
                  updateSubLangButtons("bilingual");
                  renderSubtitlesList(searchInput ? searchInput.value : "");
                  if (curTime >= 0) updateActiveSubtitle(curTime);
                }
              }

              if (completeBtn) completeBtn.classList.remove("hidden");
              const abortBtn = document.getElementById("abort-trans-btn");
              const cancelBtn = document.getElementById("cancel-trans-btn");
              if (abortBtn) abortBtn.classList.add("hidden");
              if (cancelBtn) cancelBtn.classList.remove("hidden");
            } else if (data.type === "error") {
              appendTransLog(data.message, "error");
              if (labelEl) labelEl.textContent = "오류 발생";
              alert(`${targetName} 자막 번역 중 오류: ` + data.message);
            }
          } catch (e) {
            console.error("SSE JSON 파싱 오류:", e, line);
          }
        }
      }
    }

    return translationDone;
  } catch (err) {
    if (err.name === "AbortError" || transAbortController === null) {
      appendTransLog("🛑 번역 요청이 취소되었습니다.", "warn");
    } else {
      appendTransLog("네트워크 또는 번역 처리 오류: " + err.message, "error");
      alert(`${targetName} 자막 번역 오류: ` + err.message);
    }
    return false;
  } finally {
    // 이 실행이 소유한 상태일 때만 정리 (영상 전환 후 새 번역이 시작된 경우 건드리지 않음)
    if (transAbortController === myController || transAbortController === null) {
      isTranslatingSubtitles = false;
      transAbortController = null;
      updateTranslationButtonState();
      const abortBtn = document.getElementById("abort-trans-btn");
      const cancelBtn = document.getElementById("cancel-trans-btn");
      if (abortBtn) abortBtn.classList.add("hidden");
      if (cancelBtn) cancelBtn.classList.remove("hidden");
    }
    if (isCurrentMedia(gen)) {
      const searchInput = document.getElementById("subtitle-search-input");
      renderSubtitlesList(searchInput ? searchInput.value : "");
    }
  }
}

// 하위 호환용 별칭
const requestKoreanTranslation = requestTranslation;

function applyCcFontSize() {
  const subKo = document.getElementById("video-sub-ko");
  const subOrig = document.getElementById("video-sub-orig");
  const badge = document.getElementById("cc-font-scale-badge");
  if (badge) badge.textContent = `${currentFontScale}%`;
  if (!subKo || !subOrig) return;

  const koPx = Math.round(15 * (currentFontScale / 100));
  const origPx = Math.round(13 * (currentFontScale / 100));
  subKo.style.fontSize = `${koPx}px`;
  subOrig.style.fontSize = `${origPx}px`;
}

function changeCcFontScale(delta) {
  currentFontScale = Math.min(160, Math.max(70, currentFontScale + delta));
  applyCcFontSize();
}

// ==========================================
// 자막 싱크 보정 (영상별 저장, +값 = 자막을 더 빨리 표시)
// ==========================================
const SYNC_STEP_SEC = 0.2;
const SYNC_MAX_SEC = 10;
const SYNC_STORAGE_KEY = "tubescholar_sync_offsets";
let syncOffsetMap = {};
try {
  syncOffsetMap = JSON.parse(localStorage.getItem(SYNC_STORAGE_KEY) || "{}") || {};
} catch (e) {
  syncOffsetMap = {};
}
let syncOsdTimer = null;
let lastSyncBadgeKey = null;

function getSyncKey() {
  return currentVideoId || "__default__";
}

function getSyncOffset() {
  const v = syncOffsetMap[getSyncKey()];
  return typeof v === "number" ? v : 0;
}

function formatSyncOffset(sec) {
  if (Math.abs(sec) < 0.05) return "싱크 0.0s";
  const abs = Math.abs(sec).toFixed(1);
  return sec > 0 ? `${abs}s 빠르게` : `${abs}s 늦게`;
}

function refreshSyncBadge(force = false) {
  const key = getSyncKey();
  if (!force && key === lastSyncBadgeKey) return;
  lastSyncBadgeKey = key;
  const badge = document.getElementById("sync-offset-badge");
  if (!badge) return;
  const off = getSyncOffset();
  badge.textContent = formatSyncOffset(off);
  badge.classList.toggle("text-sky-300", Math.abs(off) < 0.05);
  badge.classList.toggle("text-amber-300", Math.abs(off) >= 0.05);
}

function showSyncOsd(text) {
  const osd = document.getElementById("sync-osd");
  if (!osd) return;
  osd.textContent = `⏱ 자막 ${text}`;
  osd.classList.remove("hidden");
  if (syncOsdTimer) clearTimeout(syncOsdTimer);
  syncOsdTimer = setTimeout(() => osd.classList.add("hidden"), 1200);
}

function getPlayerCurrentTime() {
  if (isLocalVideo) {
    const v = document.getElementById("local-video-player");
    return v ? v.currentTime : -1;
  }
  if (ytPlayer && typeof ytPlayer.getCurrentTime === "function") {
    return ytPlayer.getCurrentTime();
  }
  return -1;
}

function setSyncOffset(sec) {
  sec = Math.round(Math.min(SYNC_MAX_SEC, Math.max(-SYNC_MAX_SEC, sec)) * 10) / 10;
  const key = getSyncKey();
  if (Math.abs(sec) < 0.05) {
    delete syncOffsetMap[key];
  } else {
    syncOffsetMap[key] = sec;
  }
  try {
    localStorage.setItem(SYNC_STORAGE_KEY, JSON.stringify(syncOffsetMap));
  } catch (e) {}
  refreshSyncBadge(true);
  showSyncOsd(formatSyncOffset(sec));
  // 일시정지 상태에서도 즉시 반영
  const t = getPlayerCurrentTime();
  if (t >= 0) updateActiveSubtitle(t);
}

function adjustSyncOffset(delta) {
  setSyncOffset(getSyncOffset() + delta);
}

function initSubtitleDraggable() {
  const overlay = document.getElementById("video-subtitle-overlay");
  const container = document.getElementById("video-subtitle-overlay-container");
  if (!overlay || !container) return;

  let isDragging = false;
  let startX = 0;
  let startY = 0;
  let startLeft = 0;
  let startTop = 0;

  function onPointerDown(e) {
    if (e.button && e.button !== 0) return;
    isDragging = true;

    const clientX = e.clientX || (e.touches && e.touches[0].clientX);
    const clientY = e.clientY || (e.touches && e.touches[0].clientY);

    startX = clientX;
    startY = clientY;

    const overlayRect = overlay.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();

    startLeft = overlayRect.left - containerRect.left;
    startTop = overlayRect.top - containerRect.top;

    overlay.style.bottom = "auto";
    overlay.style.right = "auto";
    overlay.style.transform = "none";
    overlay.style.left = `${startLeft}px`;
    overlay.style.top = `${startTop}px`;

    document.addEventListener("mousemove", onPointerMove);
    document.addEventListener("mouseup", onPointerUp);
    document.addEventListener("touchmove", onPointerMove, { passive: false });
    document.addEventListener("touchend", onPointerUp);
  }

  function onPointerMove(e) {
    if (!isDragging) return;
    if (e.cancelable && e.preventDefault) e.preventDefault();

    const clientX = e.clientX || (e.touches && e.touches[0].clientX);
    const clientY = e.clientY || (e.touches && e.touches[0].clientY);

    const deltaX = clientX - startX;
    const deltaY = clientY - startY;

    const containerRect = container.getBoundingClientRect();
    const overlayWidth = overlay.offsetWidth;
    const overlayHeight = overlay.offsetHeight;

    let newLeft = startLeft + deltaX;
    let newTop = startTop + deltaY;

    newLeft = Math.max(4, Math.min(newLeft, containerRect.width - overlayWidth - 4));
    newTop = Math.max(4, Math.min(newTop, containerRect.height - overlayHeight - 4));

    overlay.style.left = `${newLeft}px`;
    overlay.style.top = `${newTop}px`;
  }

  function onPointerUp() {
    isDragging = false;
    document.removeEventListener("mousemove", onPointerMove);
    document.removeEventListener("mouseup", onPointerUp);
    document.removeEventListener("touchmove", onPointerMove);
    document.removeEventListener("touchend", onPointerUp);
  }

  overlay.addEventListener("mousedown", onPointerDown);
  overlay.addEventListener("touchstart", onPointerDown, { passive: true });
  overlay.addEventListener("dblclick", resetSubtitlePosition);
}

function resetSubtitlePosition() {
  const overlay = document.getElementById("video-subtitle-overlay");
  if (!overlay) return;
  overlay.style.top = "auto";
  overlay.style.bottom = "16px";
  overlay.style.left = "50%";
  overlay.style.right = "auto";
  overlay.style.transform = "translateX(-50%)";
}

function isVideoFullscreen() {
  return !!(
    document.fullscreenElement ||
    document.webkitFullscreenElement ||
    document.mozFullScreenElement ||
    document.msFullscreenElement
  );
}

function toggleVideoFullscreen() {
  const wrapper = document.getElementById("video-player-wrapper");
  if (!wrapper) return;

  if (!isVideoFullscreen()) {
    if (wrapper.requestFullscreen) {
      wrapper.requestFullscreen().catch(err => {
        console.warn("Fullscreen request error:", err);
      });
    } else if (wrapper.webkitRequestFullscreen) {
      wrapper.webkitRequestFullscreen();
    } else if (wrapper.mozRequestFullScreen) {
      wrapper.mozRequestFullScreen();
    } else if (wrapper.msRequestFullscreen) {
      wrapper.msRequestFullscreen();
    }
  } else {
    if (document.exitFullscreen) {
      document.exitFullscreen().catch(err => {
        console.warn("Exit fullscreen error:", err);
      });
    } else if (document.webkitExitFullscreen) {
      document.webkitExitFullscreen();
    } else if (document.mozCancelFullScreen) {
      document.mozCancelFullScreen();
    } else if (document.msExitFullscreen) {
      document.msExitFullscreen();
    }
  }
}

function updateFullscreenUI() {
  const inFs = isVideoFullscreen();
  const floatBtn = document.getElementById("floating-fullscreen-btn");
  const playerFsBtn = document.getElementById("player-fullscreen-btn");

  const expandIcon = document.getElementById("floating-fs-expand-icon");
  const compressIcon = document.getElementById("floating-fs-compress-icon");

  if (expandIcon && compressIcon) {
    if (inFs) {
      expandIcon.classList.add("hidden");
      compressIcon.classList.remove("hidden");
    } else {
      expandIcon.classList.remove("hidden");
      compressIcon.classList.add("hidden");
    }
  }

  if (floatBtn) {
    floatBtn.title = inFs ? "기본 화면으로 복원 (단축키: ESC 또는 F)" : "자막과 함께 전체화면 전환 (단축키: F)";
    if (inFs) {
      floatBtn.classList.add("bg-sky-600/90", "border-sky-400");
    } else {
      floatBtn.classList.remove("bg-sky-600/90", "border-sky-400");
    }
  }

  if (playerFsBtn) {
    const icon = playerFsBtn.querySelector(".fullscreen-icon");
    const label = playerFsBtn.querySelector(".fullscreen-label");
    if (icon) icon.textContent = inFs ? "🗗" : "⛶";
    if (label) label.textContent = inFs ? "창 모드" : "전체화면";
    playerFsBtn.title = inFs ? "기본 화면으로 복원 (단축키: ESC 또는 F)" : "자막과 함께 전체화면 시청 (단축키: F)";
    if (inFs) {
      playerFsBtn.classList.add("bg-sky-700", "text-white");
    } else {
      playerFsBtn.classList.remove("bg-sky-700");
    }
  }

  if (!inFs) {
    applyCcFontSize();
  }
}

function updateActiveSubtitle(currentTime) {
  const overlay = document.getElementById("video-subtitle-overlay");
  const subKo = document.getElementById("video-sub-ko");
  const subOrig = document.getElementById("video-sub-orig");
  if (!overlay || !subKo || !subOrig) return;

  if (!isCcEnabled || !currentSubtitles || currentSubtitles.length === 0) {
    overlay.classList.add("hidden");
    clearActiveSubtitleHighlight();
    return;
  }

  // 사용자 싱크 보정 적용 (+값이면 자막을 더 일찍 표시)
  currentTime = currentTime + getSyncOffset();

  // [싱크 보정] 유튜브 자동 자막은 구간이 약 2초씩 겹치므로, '처음 일치하는' 자막이 아니라
  // '가장 최근에 시작된' 자막을 선택해야 다음 대사가 제때 표시됩니다. (이진 탐색)
  let lo = 0, hi = currentSubtitles.length - 1, cand = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if ((currentSubtitles[mid].start || 0) <= currentTime) {
      cand = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  let idx = -1;
  if (cand !== -1) {
    const s = currentSubtitles[cand];
    const start = s.start || 0;
    let end = s.end ? s.end : start + (s.duration || 3);
    const next = currentSubtitles[cand + 1];
    if (next && (next.start || 0) < end) end = next.start || 0;
    if (currentTime <= end + 0.2) idx = cand;
  }

  if (idx !== -1) {
    const sub = currentSubtitles[idx];
    const origText = sub.text || "";
    const koText = sub.ko_text || "";

    // 같은 자막·언어·문구가 이미 표시 중이면 DOM 갱신 생략 (120ms 주기 호출 최적화)
    const renderKey = `${idx}|${currentSubLang}|${koText}|${origText}`;
    if (renderKey === lastOverlayRenderKey && !overlay.classList.contains("hidden")) {
      if (activeSubtitleIndex !== idx) {
        activeSubtitleIndex = idx;
        highlightSubtitleRow(idx);
      }
      return;
    }
    lastOverlayRenderKey = renderKey;

    if (currentSubLang === "ko") {
      subKo.textContent = koText || origText;
      subKo.classList.remove("hidden");
      subOrig.textContent = "";
      subOrig.classList.add("hidden");
    } else if (currentSubLang === "bilingual") {
      if (koText) {
        subKo.textContent = koText;
        subKo.classList.remove("hidden");
        subOrig.textContent = origText;
        subOrig.classList.remove("hidden");
      } else {
        subKo.textContent = "";
        subKo.classList.add("hidden");
        subOrig.textContent = origText;
        subOrig.classList.remove("hidden");
      }
    } else {
      subKo.textContent = "";
      subKo.classList.add("hidden");
      subOrig.textContent = origText;
      subOrig.classList.remove("hidden");
    }

    applyCcFontSize();
    overlay.classList.remove("hidden");

    if (activeSubtitleIndex !== idx) {
      activeSubtitleIndex = idx;
      highlightSubtitleRow(idx);
    }
  } else {
    overlay.classList.add("hidden");
    clearActiveSubtitleHighlight();
  }
}

function updateSubtitleAutoScrollUI() {
  const btn = document.getElementById("sub-autoscroll-toggle-btn");
  const icon = document.getElementById("sub-autoscroll-icon");
  const text = document.getElementById("sub-autoscroll-text");
  if (!btn) return;

  if (isSubtitleAutoScroll) {
    btn.className = "px-2.5 py-1 bg-sky-500/20 hover:bg-sky-500/30 text-sky-300 border border-sky-500/50 rounded-lg text-xs font-semibold transition flex items-center space-x-1 shadow-sm";
    btn.title = "자동 스크롤이 켜져 있습니다 (클릭 시 끄기)";
    if (icon) icon.textContent = "📜";
    if (text) text.textContent = "자동 스크롤 ON";
  } else {
    btn.className = "px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-400 border border-slate-700 rounded-lg text-xs font-semibold transition flex items-center space-x-1 shadow-sm";
    btn.title = "자동 스크롤이 꺼져 있습니다 (자막 자유 탐색 중, 클릭 시 켜기)";
    if (icon) icon.textContent = "⏸️";
    if (text) text.textContent = "자동 스크롤 OFF";
  }
}

function toggleSubtitleAutoScroll() {
  isSubtitleAutoScroll = !isSubtitleAutoScroll;
  localStorage.setItem("tubescholar_sub_autoscroll", isSubtitleAutoScroll);
  updateSubtitleAutoScrollUI();

  // 켰을 때 현재 재생 중인 대사로 즉시 부드럽게 스크롤
  if (isSubtitleAutoScroll && activeSubtitleIndex >= 0) {
    scrollToActiveSubtitle(activeSubtitleIndex);
  }
}

// (subtitleRowByIdx / highlightedRowIdx 는 파일 상단에 선언)
const ROW_HIGHLIGHT_CLASSES = ["border-sky-400", "bg-sky-950/70", "ring-1", "ring-sky-400/60"];

function scrollToActiveSubtitle(idx) {
  if (currentActiveView !== 'subtitles') return;
  const row = subtitleRowByIdx.get(idx);
  if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function applyRowHighlight(idx, allowScroll = true) {
  if (highlightedRowIdx === idx) return;
  const prev = subtitleRowByIdx.get(highlightedRowIdx);
  if (prev) prev.classList.remove(...ROW_HIGHLIGHT_CLASSES);
  highlightedRowIdx = idx;
  const row = subtitleRowByIdx.get(idx);
  if (!row) return; // 검색 필터로 숨겨진 자막
  row.classList.add(...ROW_HIGHLIGHT_CLASSES);
  if (allowScroll && currentActiveView === 'subtitles' && isSubtitleAutoScroll) {
    const container = document.getElementById("subtitle-list");
    if (container) {
      const rowTop = row.offsetTop - container.offsetTop;
      const rowBottom = rowTop + row.clientHeight;
      const containerTop = container.scrollTop;
      const containerBottom = containerTop + container.clientHeight;
      if (rowTop < containerTop || rowBottom > containerBottom) {
        row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }
  }
}

function highlightSubtitleRow(idx) {
  applyRowHighlight(idx, true);
}

function clearActiveSubtitleHighlight() {
  // 자막 사이 공백 구간에서 0.12초마다 호출되므로, 이미 비어 있으면 즉시 반환
  if (activeSubtitleIndex === -1 && highlightedRowIdx === -1) return;
  activeSubtitleIndex = -1;
  const prev = subtitleRowByIdx.get(highlightedRowIdx);
  if (prev) prev.classList.remove(...ROW_HIGHLIGHT_CLASSES);
  highlightedRowIdx = -1;
}

function startTimeSync() {
  if (timeSyncTimer) clearInterval(timeSyncTimer);
  timeSyncTimer = setInterval(() => {
    refreshSyncBadge();
    let currentTime = -1;
    if (isLocalVideo) {
      const v = document.getElementById("local-video-player");
      if (v && !v.paused) currentTime = v.currentTime;
    } else if (ytPlayer && typeof ytPlayer.getCurrentTime === 'function' && typeof ytPlayer.getPlayerState === 'function') {
      const state = ytPlayer.getPlayerState();
      if (state === 1) {
        currentTime = ytPlayer.getCurrentTime();
      }
    }
    if (currentTime >= 0) {
      updateActiveSubtitle(currentTime);
    }
  }, 120);
}

function formatTimestampFromSeconds(sec) {
  if (!sec && sec !== 0) return "00:00";
  sec = Math.floor(sec);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function renderSubtitlesList(filterKeyword = "") {
  const container = document.getElementById("subtitle-list");
  if (!container) return;
  
  if (!currentSubtitles || currentSubtitles.length === 0) {
    container.innerHTML = `
      <div id="empty-subtitles-placeholder" class="h-full flex flex-col items-center justify-center text-center text-slate-500 py-16">
        <div class="w-14 h-14 rounded-2xl bg-slate-800/50 flex items-center justify-center mb-3 text-slate-600">
          <svg class="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z"></path></svg>
        </div>
        <h4 class="text-xs font-semibold text-slate-300 mb-1">자막이 없습니다</h4>
        <p class="text-[11px] text-slate-500 max-w-xs leading-relaxed">
          영상을 분석하거나 불러오면 인터랙티브 자막 목록이 표시됩니다. 자막을 클릭하면 해당 시간대로 즉시 이동합니다!
        </p>
      </div>`;
    return;
  }

  const keyword = (filterKeyword || "").trim().toLowerCase();
  let html = "";
  let matchedCount = 0;
  const targetName = getTargetLangName(currentTargetLang);

  const hasKo = currentSubtitles.some(s => s.ko_text && s.ko_text.trim() !== "");
  let noticeHtml = "";
  if ((currentSubLang === "ko" || currentSubLang === "bilingual") && !hasKo && !isSameLanguage) {
    const modeName = currentSubLang === "ko" ? `${targetName} 번역` : (targetName === "한국어" ? "한/영 병기" : `${targetName} 병기`);
    noticeHtml = `
      <div class="mb-3 p-3 rounded-xl bg-amber-950/40 border border-amber-500/40 text-amber-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 shadow-sm">
        <div class="flex items-center space-x-2">
          <span class="text-base">⚡</span>
          <div class="text-xs">
            <span class="font-bold">${modeName} 안내: ${targetName} 번역이 아직 요청되지 않았습니다.</span>
            <p class="text-[11px] text-amber-300/80 mt-0.5">Gemini API 사용량을 절약하기 위해 번역 요청 시에만 수동으로 번역합니다.</p>
          </div>
        </div>
        <button type="button" id="inline-request-trans-btn" class="px-3 py-1.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-lg text-xs transition flex-shrink-0 flex items-center space-x-1 shadow">
          <span>⚡ 지금 ${targetName} 번역 요청</span>
        </button>
      </div>
    `;
  }

  currentSubtitles.forEach((sub, subIdx) => {
    const origText = sub.text || "";
    const koText = sub.ko_text || "";
    const timeStr = escapeHtmlStr(sub.timestamp || formatTimestampFromSeconds(sub.start));
    const secs = Number(sub.start) || 0;

    if (keyword && !origText.toLowerCase().includes(keyword) && !koText.toLowerCase().includes(keyword)) {
      return;
    }
    matchedCount++;

    let displayTextHtml = "";
    if (currentSubLang === "ko") {
      if (koText) {
        displayTextHtml = `<div class="text-slate-100 text-xs leading-relaxed">${escapeHtml(koText)}</div>`;
      } else {
        displayTextHtml = `<div class="text-slate-300 text-xs leading-relaxed italic">${escapeHtml(origText)} <span class="text-[10px] text-amber-400/90 ml-1 font-sans not-italic bg-amber-500/10 px-1 py-0.2 rounded border border-amber-500/20">(번역 대기)</span></div>`;
      }
    } else if (currentSubLang === "bilingual") {
      if (koText) {
        displayTextHtml = `
          <div class="text-sky-300 font-semibold text-xs leading-relaxed mb-1">${escapeHtml(koText)}</div>
          <div class="text-slate-400 text-[11px] leading-relaxed">${escapeHtml(origText)}</div>
        `;
      } else {
        displayTextHtml = `
          <div class="text-slate-200 font-semibold text-xs leading-relaxed mb-1">${escapeHtml(origText)} <span class="text-[10px] text-amber-400/90 ml-1 font-sans font-normal bg-amber-500/10 px-1 py-0.2 rounded border border-amber-500/20">(${targetName} 번역 대기)</span></div>
        `;
      }
    } else {
      displayTextHtml = `<div class="text-slate-100 text-xs leading-relaxed">${escapeHtml(origText)}</div>`;
    }

    html += `
      <div 
        class="subtitle-row p-2.5 rounded-xl bg-slate-900/60 hover:bg-slate-800/90 border border-slate-800 hover:border-sky-500/50 cursor-pointer transition flex items-start space-x-3 group"
        data-seconds="${secs}"
        data-idx="${subIdx}"
        title="클릭하여 ${timeStr} 구간으로 이동"
      >
        <button type="button" class="flex-shrink-0 px-2 py-1 rounded-lg bg-sky-500/10 group-hover:bg-sky-500 text-sky-400 group-hover:text-white font-mono text-[11px] font-bold transition flex items-center space-x-1">
          <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
          <span>${timeStr}</span>
        </button>
        <div class="flex-1 min-w-0">
          ${displayTextHtml}
        </div>
      </div>
    `;
  });

  if (matchedCount === 0 && keyword) {
    container.innerHTML = noticeHtml + `
      <div class="text-center py-12 text-slate-500 text-xs">
        '${escapeHtml(keyword)}' 검색 결과가 없습니다.
      </div>`;
  } else {
    container.innerHTML = noticeHtml + html;
  }

  const inlineBtn = document.getElementById("inline-request-trans-btn");
  if (inlineBtn) {
    inlineBtn.addEventListener("click", () => requestKoreanTranslation(true));
  }

  // 자막 인덱스 → 행 요소 맵 (강조 표시 시 전체 행 순회 방지, 검색 필터 중에도 정확)
  subtitleRowByIdx = new Map();
  container.querySelectorAll(".subtitle-row").forEach(row => {
    subtitleRowByIdx.set(Number(row.dataset.idx), row);
  });
  highlightedRowIdx = -1;
  if (activeSubtitleIndex >= 0) applyRowHighlight(activeSubtitleIndex, false);

  // 클릭 이벤트는 컨테이너에 한 번만 위임 바인딩
  if (!container.dataset.clickBound) {
    container.dataset.clickBound = "1";
    container.addEventListener("click", (e) => {
      const row = e.target.closest(".subtitle-row");
      if (!row || !container.contains(row)) return;
      seekVideo(parseFloat(row.dataset.seconds));
    });
  }
}

function switchViewTab(tabName) {
  currentActiveView = tabName;
  const tabNoteBtn = document.getElementById("view-tab-note");
  const tabSubsBtn = document.getElementById("view-tab-subtitles");
  const noteContainer = document.getElementById("markdown-container");
  const subsContainer = document.getElementById("subtitle-container");
  const noteToolbar = document.getElementById("note-toolbar-buttons");
  const subsToolbar = document.getElementById("subtitle-toolbar-buttons");

  if (tabName === "subtitles") {
    tabSubsBtn.className = "px-3 py-1 bg-sky-600 text-white rounded-lg text-xs font-bold transition shadow-sm flex items-center space-x-1";
    tabNoteBtn.className = "px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-semibold transition flex items-center space-x-1";
    noteContainer.classList.add("hidden");
    const editor = document.getElementById("editor-container");
    if (editor) editor.classList.add("hidden");
    subsContainer.classList.remove("hidden");
    noteToolbar.classList.add("hidden");
    subsToolbar.classList.remove("hidden");
    const searchInput = document.getElementById("subtitle-search-input");
    renderSubtitlesList(searchInput ? searchInput.value : "");
    updateSubtitleAutoScrollUI();
    if (isSubtitleAutoScroll && activeSubtitleIndex >= 0) {
      setTimeout(() => scrollToActiveSubtitle(activeSubtitleIndex), 100);
    }
  } else {
    tabNoteBtn.className = "px-3 py-1 bg-sky-600 text-white rounded-lg text-xs font-bold transition shadow-sm flex items-center space-x-1";
    tabSubsBtn.className = "px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-semibold transition flex items-center space-x-1";
    subsContainer.classList.add("hidden");
    noteContainer.classList.remove("hidden");
    subsToolbar.classList.add("hidden");
    noteToolbar.classList.remove("hidden");
  }
}

function updateSubLangButtons(newLang) {
  const btnOrig = document.getElementById("sub-lang-original");
  const btnKo = document.getElementById("sub-lang-ko");
  const btnBi = document.getElementById("sub-lang-bilingual");

  [btnOrig, btnKo, btnBi].forEach(b => {
    if (b) b.className = "px-2.5 py-1 rounded-md font-semibold text-slate-400 hover:text-white transition flex items-center space-x-1";
  });

  const activeBtn = newLang === "ko" ? btnKo : (newLang === "bilingual" ? btnBi : btnOrig);
  if (activeBtn) activeBtn.className = "px-2.5 py-1 rounded-md font-bold transition bg-sky-600 text-white shadow flex items-center space-x-1";

  const cOrig = document.getElementById("ctrl-sub-lang-orig");
  const cKo = document.getElementById("ctrl-sub-lang-ko");
  const cBi = document.getElementById("ctrl-sub-lang-bi");
  [cOrig, cKo, cBi].forEach(b => {
    if (b) b.className = "px-2 py-0.5 rounded font-semibold text-slate-400 hover:text-white transition text-[11px]";
  });
  const cActive = newLang === "ko" ? cKo : (newLang === "bilingual" ? cBi : cOrig);
  if (cActive) cActive.className = "px-2 py-0.5 rounded font-bold transition bg-sky-600 text-white text-[11px]";
}

async function changeSubLanguage(newLang, fromPlayerBar = false) {
  const hasKo = currentSubtitles && currentSubtitles.some(s => s.ko_text && s.ko_text.trim() !== "");
  const targetName = getTargetLangName(currentTargetLang);

  // 영상 하단 플레이어 바에서 미번역 상태로 번역/병기 선택 시 명시적 확인창 제공
  if ((newLang === "ko" || newLang === "bilingual") && currentSubtitles.length > 0 && !hasKo && !isSameLanguage) {
    if (fromPlayerBar) {
      const modeLabel = newLang === "ko" ? `${targetName} 자막` : (targetName === "한국어" ? "한/영 병기 자막" : `${targetName} 병기 자막`);
      const wantTranslate = confirm(
        `[${modeLabel}]이 아직 생성되지 않았습니다.\n지금 Gemini에 ${targetName} 번역을 요청하시겠습니까? (API 사용량이 발생합니다)\n\n[확인]을 누르면 번역 후 표시되고, [취소]를 누르면 원문 자막이 유지됩니다.`
      );
      if (wantTranslate) {
        currentSubLang = newLang;
        updateSubLangButtons(newLang);
        await requestTranslation(true);
        return;
      } else {
        return; // 취소 시 원문 유지
      }
    }
  }

  // 자동 번역 API 호출은 배제하고 언어 모드만 전환 (명시적 요청 시에만 Gemini 호출)
  currentSubLang = newLang;
  updateSubLangButtons(newLang);

  const searchInput = document.getElementById("subtitle-search-input");
  renderSubtitlesList(searchInput ? searchInput.value : "");

  // 화면 위 실시간 자막도 변경된 언어로 즉각 갱신
  let curTime = -1;
  if (isLocalVideo) {
    const v = document.getElementById("local-video-player");
    if (v) curTime = v.currentTime;
  } else if (ytPlayer && typeof ytPlayer.getCurrentTime === 'function') {
    curTime = ytPlayer.getCurrentTime();
  }
  if (curTime >= 0) updateActiveSubtitle(curTime);
}

async function triggerSubtitleDownload(format) {
  if (!currentSubtitles || currentSubtitles.length === 0) {
    alert("다운로드할 자막 데이터가 없습니다. 먼저 영상을 분석하거나 불러와주세요.");
    return;
  }

  const hasKo = currentSubtitles.some(s => s.ko_text && s.ko_text.trim() !== "");
  const targetName = getTargetLangName(currentTargetLang);
  let downloadLangMode = currentSubLang;

  if ((downloadLangMode === "ko" || downloadLangMode === "bilingual") && !hasKo && !isSameLanguage) {
    const modeName = downloadLangMode === "ko" ? `${targetName} 번역` : (targetName === "한국어" ? "한/영 병기" : `${targetName} 병기`);
    const wantTranslate = confirm(
      `${modeName} 자막 데이터가 아직 없습니다.\n지금 Gemini 번역을 요청하여 생성한 후 다운로드하시겠습니까? (API 사용량이 발생합니다)\n\n[취소]를 누르면 번역 없이 원문 자막으로 다운로드합니다.`
    );
    if (wantTranslate) {
      const ok = await requestTranslation(true);
      if (!ok) return;
    } else {
      downloadLangMode = "original";
    }
  }

  const title = (currentVideoInfo ? currentVideoInfo.title : "subtitle");
  try {
    const res = await fetch("/api/subtitles/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        subtitles: currentSubtitles,
        format: format,
        lang_mode: downloadLangMode,
        title: title,
        target_lang: currentTargetLang,
        auto_translate: false,
        sync_offset: getSyncOffset()
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "자막 다운로드 생성 실패");

    const mime = format === "txt" ? "text/plain;charset=utf-8" : "application/x-subrip;charset=utf-8";
    const blob = new Blob([data.content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = data.filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    alert("자막 다운로드 오류: " + err.message);
  }
}

function setAnalysisStep(stepNum) {
  for (let i = 1; i <= 3; i++) {
    const el = document.getElementById(`step-${i}`);
    if (!el) continue;
    const icon = el.querySelector(".step-icon");

    if (i < stepNum) {
      el.className = "flex items-center space-x-2 text-emerald-400 font-medium";
      icon.className = "step-icon w-4 h-4 rounded-full bg-emerald-500/20 text-emerald-300 flex items-center justify-center text-[10px]";
      icon.textContent = "✓";
    } else if (i === stepNum) {
      el.className = "flex items-center space-x-2 text-sky-400 font-bold animate-pulse";
      icon.className = "step-icon w-4 h-4 rounded-full bg-sky-500 text-white flex items-center justify-center text-[10px]";
      icon.textContent = `${i}`;
    } else {
      el.className = "flex items-center space-x-2 text-slate-500";
      icon.className = "step-icon w-4 h-4 rounded-full bg-slate-800 text-slate-400 flex items-center justify-center text-[10px]";
      icon.textContent = `${i}`;
    }
  }
}

function abortCurrentAnalysis() {
  if (currentAbortController) {
    currentAbortController.abort();
    currentAbortController = null;
  }
  document.getElementById("loading-overlay").classList.add("hidden");
  document.getElementById("header-cancel-btn").classList.add("hidden");
  const submitBtn = document.getElementById("submit-btn");
  submitBtn.disabled = false;
  submitBtn.classList.remove("opacity-50");
  alert("🛑 분석 작업이 사용자에 의해 즉시 중단되었습니다.");
}

// 1. Gemini 자동 분석 실행
async function runGeminiAnalysis(url) {
  const loadingOverlay = document.getElementById("loading-overlay");
  const loadingTitle = document.getElementById("loading-title");
  const loadingDesc = document.getElementById("loading-desc");
  const submitBtn = document.getElementById("submit-btn");
  const headerCancelBtn = document.getElementById("header-cancel-btn");

  currentAbortController = new AbortController();
  loadingOverlay.classList.remove("hidden");
  headerCancelBtn.classList.remove("hidden");
  submitBtn.disabled = true;
  submitBtn.classList.add("opacity-50");

  setAnalysisStep(1);
  loadingTitle.textContent = "1단계: 자막 및 영상 정보 추출 중...";
  loadingDesc.textContent = "유튜브 서버에서 타임스탬프 자막을 가져오고 있습니다.";

  const stepTimer = setTimeout(() => {
    setAnalysisStep(2);
    loadingTitle.textContent = "2단계: Gemini가 문맥 오류 교정 및 Deep Dive 생성 중...";
    loadingDesc.textContent = "초대형 컨텍스트 윈도우로 전체 흐름을 정밀 분석하고 지식 해설을 작성합니다.";
  }, 1200);

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: currentAbortController.signal,
      body: JSON.stringify({
        url: url,
        engine: "gemini",
        source_lang: currentSourceLang,
        target_lang: currentTargetLang
      })
    });

    clearTimeout(stepTimer);
    setAnalysisStep(3);
    loadingTitle.textContent = "3단계: 문서 렌더링 및 로컬 저장 완료 중...";

    let data = null;
    try {
      data = await response.json();
    } catch (e) {}

    if (!response.ok) {
      throw new Error((data && data.detail) || "분석 요청에 실패했습니다.");
    }

    switchMediaContext(data.video_info.video_id, data.note_id);
    initYouTubePlayer(currentVideoId);
    displayVideoMetadata(data.video_info);
    renderMarkdownNote(data.markdown, `Gemini: ${data.model_used}`, data.note_id);
    const analyzeSubs = data.subtitles || [];
    const analyzeHasTrans = analyzeSubs.some(s => s.ko_text && s.ko_text.trim() !== "");
    if (analyzeHasTrans) {
      currentSubLang = "bilingual";
    } else {
      currentSubLang = "original";
    }
    updateSubLangButtons(currentSubLang);
    setSubtitles(analyzeSubs);
    applyLanguageState(data);
    loadLibrary();
  } catch (err) {
    if (err.name === 'AbortError') return;
    alert("오류: " + err.message);
  } finally {
    clearTimeout(stepTimer);
    currentAbortController = null;
    loadingOverlay.classList.add("hidden");
    headerCancelBtn.classList.add("hidden");
    submitBtn.disabled = false;
    submitBtn.classList.remove("opacity-50");
  }
}

// 2. 구독 AI용 프롬프트 복사 실행
async function runSubscriptionPrompt(url) {
  const submitBtn = document.getElementById("submit-btn");
  submitBtn.disabled = true;
  submitBtn.classList.add("opacity-50");

  try {
    const res = await fetch("/api/prompt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: url,
        source_lang: currentSourceLang,
        target_lang: currentTargetLang
      })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "프롬프트 생성 실패");

    await navigator.clipboard.writeText(data.prompt);
    
    const gen = switchMediaContext(data.video_info.video_id, null);
    initYouTubePlayer(currentVideoId);
    displayVideoMetadata(data.video_info);

    if (data.subtitles && data.subtitles.length > 0) {
      setSubtitles(data.subtitles);
      applyLanguageState(data);
    } else {
      setSubtitles([]);
      applyLanguageState(data);
      // 비동기로 자막 목록도 함께 로드 (그 사이 다른 영상으로 바뀌면 무시)
      fetch("/api/subtitles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          video_id: currentVideoId,
          source_lang: currentSourceLang,
          target_lang: currentTargetLang
        })
      }).then(r => r.json()).then(d => {
        if (isCurrentMedia(gen) && d.success && d.subtitles) {
          setSubtitles(d.subtitles);
          applyLanguageState(d);
        }
      }).catch(() => {});
    }

    const pasteCard = document.getElementById("inline-paste-card");
    const pasteTextarea = document.getElementById("inline-paste-textarea");
    pasteCard.classList.remove("hidden");
    pasteTextarea.value = "";
    pasteTextarea.focus();

    alert("✨ 완성된 심화 프롬프트가 클립보드에 복사되었습니다!\n\n1. 사용 중이신 ChatGPT 또는 Claude 대화창에 붙여넣고(Ctrl+V) 답변을 받으세요.\n2. 받은 답변을 우측 'ChatGPT / Claude 답변 붙여넣기' 창에 넣고 [노트 적용]을 누르면 즉시 연동됩니다.");
  } catch (e) {
    alert("오류: " + e.message);
  } finally {
    submitBtn.disabled = false;
    submitBtn.classList.remove("opacity-50");
  }
}

// 보관함 목록 로드 (동일 영상의 여러 버전도 모두 나열)
async function loadLibrary() {
  try {
    const res = await fetch("/api/notes");
    const data = await res.json();
    const notes = data.notes || [];

    document.getElementById("library-count-badge").textContent = notes.length;
    document.getElementById("drawer-count").textContent = `(${notes.length}개)`;

    const listEl = document.getElementById("library-list");
    listEl.innerHTML = "";

    if (notes.length === 0) {
      listEl.innerHTML = `<p class="text-xs text-slate-500 text-center py-8">아직 저장된 학습 노트가 없습니다.</p>`;
      return;
    }

    notes.forEach(item => {
      const card = document.createElement("div");
      card.className = "p-3 bg-slate-800/80 hover:bg-slate-800 border border-slate-700/80 rounded-xl cursor-pointer transition flex space-x-3 items-start group relative";
      const thumb = item.thumbnail || (item.video_id.startsWith('local_') ? '' : `https://i.ytimg.com/vi/${item.video_id}/hqdefault.jpg`);
      
      card.innerHTML = `
        <div class="w-20 h-14 bg-slate-900 rounded-lg border border-slate-700 flex-shrink-0 overflow-hidden flex items-center justify-center">
          ${thumb ? `<img src="${escapeHtmlStr(thumb)}" alt="thumb" class="w-full h-full object-cover">` : `<span class="text-xs text-amber-400 font-bold">📁 로컬</span>`}
        </div>
        <div class="flex-1 min-w-0 pr-6">
          <p class="text-xs font-semibold text-sky-400 truncate">${escapeHtmlStr(item.channel || 'YouTube')}</p>
          <h4 class="text-xs font-bold text-white truncate mt-0.5" title="${escapeHtmlStr(item.title)}">${escapeHtmlStr(item.title)}</h4>
          <p class="text-[10px] text-slate-400 mt-1">${escapeHtmlStr(item.created_at || '')}</p>
        </div>
        <button class="delete-note-btn absolute top-2 right-2 text-slate-500 hover:text-red-400 p-1 rounded opacity-0 group-hover:opacity-100 transition" title="삭제">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
        </button>
      `;

      card.addEventListener("click", (e) => {
        if (e.target.closest(".delete-note-btn")) return;
        loadSingleSavedNote(item.note_id || item.video_id);
        toggleDrawer(false);
      });

      const delBtn = card.querySelector(".delete-note-btn");
      delBtn.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (confirm(`'${item.title}' 학습 노트를 삭제하시겠습니까?`)) {
          await fetch(`/api/notes/${item.note_id || item.video_id}`, { method: "DELETE" });
          loadLibrary();
        }
      });

      listEl.appendChild(card);
    });
  } catch (err) {
    console.error("보관함 로드 실패:", err);
  }
}

async function loadSingleSavedNote(noteIdOrVid) {
  try {
    const res = await fetch(`/api/notes/${noteIdOrVid}`);
    if (!res.ok) throw new Error("노트를 불러올 수 없습니다.");
    const data = await res.json();

    const gen = switchMediaContext(data.metadata.video_id, data.note_id);

    if (data.metadata.video_type !== 'local') {
      initYouTubePlayer(currentVideoId);
    } else {
      // 로컬 영상 노트: 원본 파일이 없으므로 이전 영상 재생을 멈춤
      if (ytPlayer && typeof ytPlayer.pauseVideo === 'function') {
        try { ytPlayer.pauseVideo(); } catch (e) {}
      }
      const lp = document.getElementById("local-video-player");
      if (lp) lp.pause();
    }
    displayVideoMetadata(data.metadata);
    renderMarkdownNote(data.markdown, "저장된 보관 노트", currentNoteId);
    document.getElementById("inline-paste-card").classList.add("hidden");

    const meta = data.metadata || {};
    const savedSubs = (meta.subtitles && Array.isArray(meta.subtitles)) ? meta.subtitles : [];
    const hasTranslation = savedSubs.some(s => s.ko_text && s.ko_text.trim() !== "");

    // 1. 번역된 자막이 존재하는 경우 사용자가 즉시 번역문을 볼 수 있도록 'bilingual'(병기) 모드로 전환
    if (hasTranslation) {
      currentSubLang = "bilingual";
    } else {
      currentSubLang = "original";
    }
    updateSubLangButtons(currentSubLang);

    // 2. 자막 목록 등록 (setSubtitles 내부에서 renderSubtitlesList가 최신 currentSubLang 기준으로 렌더링)
    if (savedSubs.length > 0) {
      setSubtitles(savedSubs);
    } else if (meta.video_type !== 'local' && currentVideoId && !currentVideoId.startsWith('custom_')) {
      setSubtitles([]);
      fetch("/api/subtitles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          video_id: currentVideoId,
          note_id: currentNoteId,
          source_lang: currentSourceLang,
          target_lang: currentTargetLang
        })
      }).then(r => r.json()).then(d => {
        if (isCurrentMedia(gen) && d.success && d.subtitles) {
          const fetchHasTrans = d.subtitles.some(s => s.ko_text && s.ko_text.trim() !== "");
          if (fetchHasTrans && currentSubLang === "original") {
            currentSubLang = "bilingual";
            updateSubLangButtons(currentSubLang);
          }
          setSubtitles(d.subtitles);
          applyLanguageState(d);
        }
      }).catch(() => {});
    } else {
      setSubtitles([]);
    }

    // 3. 자막이 메모리에 등록된 상태에서 언어 상태 복원 (hasKo가 정확히 계산되어 '재번역' 버튼 및 뱃지 정상 동기화)
    applyLanguageState({
      target_lang: meta.target_lang || "ko",
      source_lang: meta.source_lang || null,
      original_lang: meta.original_lang || null,
      translation_source: meta.translation_source || (hasTranslation ? "gemini" : null),
      translation_track: meta.translation_track || null,
      is_korean: meta.is_korean || false,
      transcript_language: meta.transcript_language || null,
      is_generated: meta.is_generated || false
    });

    // 4. 화면 재생 위치에 따른 자막 동기화
    let curTime = -1;
    if (isLocalVideo) {
      const v = document.getElementById("local-video-player");
      if (v) curTime = v.currentTime;
    } else if (ytPlayer && typeof ytPlayer.getCurrentTime === 'function') {
      curTime = ytPlayer.getCurrentTime();
    }
    if (curTime >= 0) updateActiveSubtitle(curTime);

    // 유튜브 트랙 목록 비동기 보강 (원문 드롭다운에 모든 트랙 옵션 채우기)
    if (meta.video_type !== 'local' && currentVideoId && !currentVideoId.startsWith('custom_')) {
      fetch(`/api/subtitles/tracks?video_id=${encodeURIComponent(currentVideoId)}`)
        .then(r => r.json())
        .then(d => {
          if (isCurrentMedia(gen) && d.success && Array.isArray(d.tracks)) {
            currentTracks = d.tracks;
            renderSourceLangSelect();
          }
        }).catch(() => {});
    }
    
    // 편집 모드 종료 상태로 복원
    if (isEditing) toggleEditor(false);
  } catch (err) {
    alert("노트 로드 실패: " + err.message);
  }
}

// 편집기 토글
function toggleEditor(forceState) {
  isEditing = typeof forceState === 'boolean' ? forceState : !isEditing;
  const editorContainer = document.getElementById("editor-container");
  const markdownContainer = document.getElementById("markdown-container");
  const editBtnText = document.getElementById("edit-btn-text");

  if (isEditing) {
    editorContainer.classList.remove("hidden");
    markdownContainer.classList.add("hidden");
    editBtnText.textContent = "👁️ 미리보기";
    document.getElementById("note-editor-textarea").value = currentMarkdown;
    document.getElementById("note-editor-textarea").focus();
  } else {
    editorContainer.classList.add("hidden");
    markdownContainer.classList.remove("hidden");
    editBtnText.textContent = "✏️ 편집";
  }
}

function switchMode(mode) {
  currentMode = mode;
  const tabGemini = document.getElementById("tab-gemini");
  const tabSub = document.getElementById("tab-subscription");
  const submitText = document.getElementById("submit-btn-text");
  const inlinePasteCard = document.getElementById("inline-paste-card");

  if (mode === "gemini") {
    tabGemini.className = "px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center space-x-1.5 bg-sky-600 text-white shadow";
    tabSub.className = "px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center space-x-1.5 text-slate-400 hover:text-white";
    submitText.textContent = typeof t === "function" ? t("btn_analyze") : "⚡ 분석 및 생성";
    inlinePasteCard.classList.add("hidden");
  } else {
    tabSub.className = "px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center space-x-1.5 bg-indigo-600 text-white shadow";
    tabGemini.className = "px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center space-x-1.5 text-slate-400 hover:text-white";
    submitText.textContent = typeof t === "function" ? t("btn_copy_prompt") : "📋 프롬프트 복사";
    inlinePasteCard.classList.remove("hidden");
  }
}

function toggleDrawer(open) {
  const drawer = document.getElementById("library-drawer");
  if (open) drawer.classList.remove("translate-x-full");
  else drawer.classList.add("translate-x-full");
}

async function checkConfig() {
  try {
    const res = await fetch("/api/config");
    const data = await res.json();
    if (data.has_api_key) {
      document.getElementById("api-key-input").placeholder = `현재 설정됨 (${data.masked_key})`;
    }
    const groqInput = document.getElementById("groq-api-key-input");
    if (groqInput) {
      if (data.has_groq_key) {
        groqInput.placeholder = `현재 설정됨 (${data.masked_groq_key})`;
      } else {
        groqInput.placeholder = "gsk_...";
      }
    }
  } catch (e) {}
}

document.addEventListener("DOMContentLoaded", () => {
  // UI 다국어 언어 선택 셀렉트박스 바인딩
  const uiLangSelect = document.getElementById("ui-lang-select");
  if (uiLangSelect && typeof getUiLang === "function") {
    uiLangSelect.value = getUiLang();
    uiLangSelect.addEventListener("change", (e) => {
      const newLang = e.target.value;
      if (typeof setUiLang === "function") {
        setUiLang(newLang);
      }
    });
  }

  window.addEventListener("tubescholar:lang_change", (e) => {
    const lang = e.detail?.lang || "ko";
    if (uiLangSelect) uiLangSelect.value = lang;
    switchMode(currentMode);
    updateLangLabels();
    renderTargetLangSelect();
    renderSourceLangSelect();
    updateTranslationButtonState();
    loadTtsVoices();
  });

  const form = document.getElementById("analyze-form");
  const tabGemini = document.getElementById("tab-gemini");
  const tabSub = document.getElementById("tab-subscription");

  tabGemini.addEventListener("click", () => switchMode("gemini"));
  tabSub.addEventListener("click", () => switchMode("subscription"));

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const url = document.getElementById("url-input").value.trim();
    if (!url) return;

    if (url.includes("/@") || url.includes("/channel/") || url.includes("/c/")) {
      document.getElementById("channel-modal").classList.remove("hidden");
      document.getElementById("channel-url-input").value = url;
      fetchChannelVideos(url);
    } else {
      if (currentMode === "gemini") {
        runGeminiAnalysis(url);
      } else {
        runSubscriptionPrompt(url);
      }
    }
  });

  // 편집 토글 버튼
  document.getElementById("toggle-edit-btn").addEventListener("click", () => toggleEditor());

  // 편집 내용 저장 버튼
  document.getElementById("save-edited-note-btn").addEventListener("click", async () => {
    const editedMd = document.getElementById("note-editor-textarea").value;
    if (!currentNoteId) {
      // 새 임의 저장
      currentNoteId = `note_${Date.now()}`;
    }

    try {
      const res = await fetch(`/api/notes/${currentNoteId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ markdown: editedMd })
      });
      const data = await res.json();
      if (!res.ok) throw new Error("저장 실패");

      renderMarkdownNote(editedMd, "수정 및 저장됨", currentNoteId);
      toggleEditor(false);
      loadLibrary();
      alert("💾 수정된 내용이 성공적으로 저장되었습니다!");
    } catch (e) {
      // 만약 note_id가 없어서 PUT 실패 시 manual-save로 fallback
      try {
        const res2 = await fetch("/api/manual-save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ 
            title: currentVideoInfo ? currentVideoInfo.title : "수정된 학습 노트", 
            markdown: editedMd,
            note_id: currentNoteId,
            subtitles: currentSubtitles,
            source_lang: currentSourceLang,
            target_lang: currentTargetLang,
            translation_source: currentTranslationSource
          })
        });
        const d2 = await res2.json();
        currentNoteId = d2.note_id;
        renderMarkdownNote(editedMd, "수정 및 저장됨", currentNoteId);
        toggleEditor(false);
        loadLibrary();
        alert("💾 수정된 내용이 성공적으로 저장되었습니다!");
      } catch (err2) {
        alert("저장 오류: " + err2.message);
      }
    }
  });

  // 인라인 붙여넣기 적용 버튼
  document.getElementById("inline-paste-apply-btn").addEventListener("click", async () => {
    const url = document.getElementById("url-input").value.trim() || (currentVideoInfo ? currentVideoInfo.url : "");
    const rawMd = document.getElementById("inline-paste-textarea").value.trim();
    if (!rawMd) {
      alert("붙여넣을 마크다운 내용을 입력해 주세요.");
      return;
    }

    try {
      const res = await fetch("/api/manual-save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          url: url, 
          markdown: rawMd,
          title: currentVideoInfo ? currentVideoInfo.title : "",
          subtitles: currentSubtitles,
          source_lang: currentSourceLang,
          target_lang: currentTargetLang,
          translation_source: currentTranslationSource
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "저장 실패");

      const newVid = (data.video_info.video_id && !data.video_info.video_id.startsWith('custom_')) ? data.video_info.video_id : null;
      if (newVid && newVid !== currentVideoId) {
        switchMediaContext(newVid, data.note_id);
        initYouTubePlayer(currentVideoId);
      } else {
        currentNoteId = data.note_id;
      }
      displayVideoMetadata(data.video_info);
      renderMarkdownNote(data.markdown, "구독 AI 연동 노트", data.note_id);
      loadLibrary();
      document.getElementById("inline-paste-textarea").value = "";
      alert("✅ 구독 AI 학습 노트가 독립된 새 노트로 영구 저장되었습니다!");
    } catch (e) {
      alert("오류: " + e.message);
    }
  });

  // 로컬 비디오 모달 열기/닫기
  document.getElementById("local-file-btn").addEventListener("click", () => {
    document.getElementById("local-file-modal").classList.remove("hidden");
  });
  document.getElementById("close-local-modal-btn").addEventListener("click", () => {
    document.getElementById("local-file-modal").classList.add("hidden");
  });

  // 로컬 파일 처리 (Gemini 분석 또는 프롬프트 복사)
  async function handleLocalFileAction(isPromptOnly) {
    const videoFile = document.getElementById("local-video-input").files[0];
    const subFile = document.getElementById("local-subtitle-input").files[0];
    const title = document.getElementById("local-title-input").value.trim() || (videoFile ? videoFile.name.replace(/\.[^/.]+$/, "") : "로컬 비디오");

    if (!subFile) {
      alert("자막 파일(.srt 또는 .vtt)을 선택해 주세요.");
      return;
    }

    const subText = await subFile.text();

    // 로컬 파일용 새 컨텍스트 (이전 YouTube 영상 ID·싱크값·번역이 섞이지 않도록)
    const gen = switchMediaContext(localMediaKey(videoFile, title), null);
    isKoreanContent = false;
    isSameLanguage = false;
    currentTracks = [];
    currentSourceLang = null;
    currentTranslationSource = null;
    renderSourceLangSelect();
    setSubtitles([]);

    if (videoFile) {
      initLocalVideoPlayer(videoFile);
      displayVideoMetadata({
        title: title,
        channel: "내 로컬 PC 파일",
        video_type: "local",
        duration_str: "로컬 영상"
      });
    }

    document.getElementById("local-file-modal").classList.add("hidden");

    if (isPromptOnly) {
      // 구독 AI 프롬프트 복사
      try {
        const res = await fetch("/api/local/prompt", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: title, subtitle_text: subText })
        });
        const d = await res.json();
        await navigator.clipboard.writeText(d.prompt);
        switchMode("subscription");
        alert("✨ 로컬 자막으로 완성된 심화 프롬프트가 복사되었습니다!\nChatGPT/Claude에 붙여넣은 뒤 우측 '답변 붙여넣기'에 넣어주세요.");
      } catch (e) {
        alert("프롬프트 복사 오류: " + e.message);
      }
    } else {
      // Gemini 분석
      const loadingOverlay = document.getElementById("loading-overlay");
      loadingOverlay.classList.remove("hidden");
      setAnalysisStep(2);
      try {
        const res = await fetch("/api/local/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title: title, subtitle_text: subText, engine: "gemini" })
        });
        let d = null;
        try {
          d = await res.json();
        } catch (e) {}
        if (!res.ok) throw new Error((d && d.detail) || "분석 실패");
        if (!isCurrentMedia(gen)) return;
        renderMarkdownNote(d.markdown, `Gemini: ${d.model_used}`, d.note_id);
        if (d.subtitles) setSubtitles(d.subtitles);
        loadLibrary();
      } catch (e) {
        alert("분석 오류: " + e.message);
      } finally {
        loadingOverlay.classList.add("hidden");
      }
    }
  }

  document.getElementById("local-analyze-btn").addEventListener("click", () => handleLocalFileAction(false));
  document.getElementById("local-prompt-btn").addEventListener("click", () => handleLocalFileAction(true));

  // 자막 없는 로컬 비디오 -> 영상에서 오디오 추출 후 Gemini 멀티모달 직접 분석
  document.getElementById("local-audio-direct-btn").addEventListener("click", async () => {
    const videoFile = document.getElementById("local-video-input").files[0];
    if (!videoFile) {
      alert("분석할 로컬 비디오 파일(.mp4, .webm, .mkv 등)을 먼저 선택해 주세요.");
      return;
    }

    const title = document.getElementById("local-title-input").value.trim() || videoFile.name.replace(/\.[^/.]+$/, "");
    
    // 로컬 비디오 플레이어 바로 준비 및 재생 (새 컨텍스트)
    const gen = switchMediaContext(localMediaKey(videoFile, title), null);
    isKoreanContent = false;
    isSameLanguage = false;
    currentTracks = [];
    currentSourceLang = null;
    currentTranslationSource = null;
    renderSourceLangSelect();
    setSubtitles([]);
    initLocalVideoPlayer(videoFile);
    displayVideoMetadata({
      title: title,
      channel: "내 로컬 PC 영상 (음성 직접 청취)",
      video_type: "local",
      duration_str: "로컬 음성 분석"
    });

    document.getElementById("local-file-modal").classList.add("hidden");

    const loadingOverlay = document.getElementById("loading-overlay");
    const loadingTitle = document.getElementById("loading-title");
    const loadingDesc = document.getElementById("loading-desc");
    const headerCancelBtn = document.getElementById("header-cancel-btn");

    currentAbortController = new AbortController();
    loadingOverlay.classList.remove("hidden");
    headerCancelBtn.classList.remove("hidden");

    setAnalysisStep(1);
    loadingTitle.textContent = "1단계: 영상에서 오디오 추출 중...";
    loadingDesc.textContent = "FFmpeg를 통해 영상에서 고압축 음성 트랙(MP3)을 신속하게 추출하고 있습니다.";

    const stepTimer = setTimeout(() => {
      setAnalysisStep(2);
      loadingTitle.textContent = "2단계: Groq Whisper 0.1초 칼싱크 자막 & Gemini 지식 노트 생성 중...";
      loadingDesc.textContent = "초고속 음성인식으로 정밀 자막을 생성하고, Gemini AI가 심층 학습 노트를 구성합니다.";
    }, 2200);

    const formData = new FormData();
    formData.append("video", videoFile);
    formData.append("title", title);

    try {
      const res = await fetch("/api/local/video-analyze", {
        method: "POST",
        signal: currentAbortController.signal,
        body: formData
      });
      let data = null;
      try {
        data = await res.json();
      } catch (e) {}
      if (!res.ok) throw new Error((data && data.detail) || "로컬 영상 음성 분석 실패");
      if (!isCurrentMedia(gen)) return;

      clearTimeout(stepTimer);
      setAnalysisStep(3);
      loadingTitle.textContent = "3단계: 노트 렌더링 및 보관함 저장 완료!";

      renderMarkdownNote(data.markdown, `분석 엔진: ${data.model_used}`, data.note_id);
      if (data.subtitles) {
        setSubtitles(data.subtitles);
      }
      loadLibrary();
    } catch (e) {
      if (e.name === 'AbortError') return;
      alert("분석 오류: " + e.message);
    } finally {
      clearTimeout(stepTimer);
      currentAbortController = null;
      loadingOverlay.classList.add("hidden");
      headerCancelBtn.classList.add("hidden");
    }
  });

  // 플레이어 버튼
  document.getElementById("seek-back-btn").addEventListener("click", () => {
    if (isLocalVideo) {
      const v = document.getElementById("local-video-player");
      if (v) seekVideo(Math.max(0, v.currentTime - 10));
    } else if (ytPlayer && typeof ytPlayer.getCurrentTime === 'function') {
      seekVideo(Math.max(0, ytPlayer.getCurrentTime() - 10));
    }
  });

  document.getElementById("seek-forward-btn").addEventListener("click", () => {
    if (isLocalVideo) {
      const v = document.getElementById("local-video-player");
      if (v) seekVideo(v.currentTime + 10);
    } else if (ytPlayer && typeof ytPlayer.getCurrentTime === 'function') {
      seekVideo(ytPlayer.getCurrentTime() + 10);
    }
  });

  document.getElementById("play-pause-btn").addEventListener("click", () => {
    if (isLocalVideo) {
      const v = document.getElementById("local-video-player");
      if (v) {
        if (v.paused) v.play();
        else v.pause();
      }
    } else if (ytPlayer && typeof ytPlayer.getPlayerState === 'function') {
      const state = ytPlayer.getPlayerState();
      if (state === 1) ytPlayer.pauseVideo();
      else ytPlayer.playVideo();
    }
  });

  document.querySelectorAll(".speed-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const speed = parseFloat(btn.dataset.speed);
      if (isLocalVideo) {
        const v = document.getElementById("local-video-player");
        if (v) v.playbackRate = speed;
      } else if (ytPlayer && typeof ytPlayer.setPlaybackRate === 'function') {
        ytPlayer.setPlaybackRate(speed);
      }
      document.querySelectorAll(".speed-btn").forEach(b => b.classList.remove("bg-sky-600", "text-white"));
      btn.classList.add("bg-sky-600", "text-white");
    });
  });

  // 복사 및 다운로드
  document.getElementById("copy-markdown-btn").addEventListener("click", () => {
    if (!currentMarkdown) return;
    navigator.clipboard.writeText(currentMarkdown).then(() => {
      alert("학습 노트 내용이 클립보드에 복사되었습니다!");
    });
  });

  document.getElementById("download-markdown-btn").addEventListener("click", () => {
    if (!currentMarkdown) return;
    const blob = new Blob([currentMarkdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const safeTitle = (currentVideoInfo ? currentVideoInfo.title : "study_note").replace(/[/\\?%*:|"<>]/g, '_');
    a.href = url;
    a.download = `${safeTitle}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });

  // 중단 버튼
  document.getElementById("cancel-analysis-btn").addEventListener("click", abortCurrentAnalysis);
  document.getElementById("header-cancel-btn").addEventListener("click", abortCurrentAnalysis);

  // 보관함 / 채널 / 설정
  document.getElementById("library-toggle-btn").addEventListener("click", () => toggleDrawer(true));
  document.getElementById("close-drawer-btn").addEventListener("click", () => toggleDrawer(false));
  document.getElementById("channel-btn").addEventListener("click", () => document.getElementById("channel-modal").classList.remove("hidden"));
  document.getElementById("close-channel-modal-btn").addEventListener("click", () => document.getElementById("channel-modal").classList.add("hidden"));
  document.getElementById("fetch-channel-videos-btn").addEventListener("click", () => {
    const url = document.getElementById("channel-url-input").value.trim();
    if (url) fetchChannelVideos(url);
  });

  document.getElementById("settings-btn").addEventListener("click", () => document.getElementById("settings-modal").classList.remove("hidden"));
  document.getElementById("close-settings-modal-btn").addEventListener("click", () => document.getElementById("settings-modal").classList.add("hidden"));
  document.getElementById("save-settings-btn").addEventListener("click", async () => {
    const key = document.getElementById("api-key-input").value.trim();
    const groqKeyInput = document.getElementById("groq-api-key-input");
    const groqKey = groqKeyInput ? groqKeyInput.value.trim() : "";

    const payload = {};
    if (key) payload.api_key = key;
    if (groqKey) payload.groq_api_key = groqKey;

    if (Object.keys(payload).length > 0) {
      const res = await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (res.ok) alert("API 키가 성공적으로 저장되었습니다.");
    }
    document.getElementById("settings-modal").classList.add("hidden");
    checkConfig();
  });

  // 탭 전환 (학습 노트 vs 자막 스크립트)
  document.getElementById("view-tab-note").addEventListener("click", () => switchViewTab("note"));
  document.getElementById("view-tab-subtitles").addEventListener("click", () => switchViewTab("subtitles"));

  // 자막 언어 변경 (원문, 한국어, 한영병기)
  document.getElementById("sub-lang-original").addEventListener("click", () => changeSubLanguage("original"));
  document.getElementById("sub-lang-ko").addEventListener("click", () => changeSubLanguage("ko"));
  document.getElementById("sub-lang-bilingual").addEventListener("click", () => changeSubLanguage("bilingual"));

  // 번역 대상 언어 셀렉트 박스 변경 시
  const subTargetSelect = document.getElementById("sub-target-lang");
  if (subTargetSelect) {
    subTargetSelect.addEventListener("change", async (e) => {
      const newTarget = e.target.value;
      if (newTarget === currentTargetLang) return;

      if (isTranslatingSubtitles) {
        alert("현재 번역 작업이 진행 중입니다. 번역 완료 또는 취소 후 언어를 변경해주세요.");
        subTargetSelect.value = currentTargetLang;
        return;
      }

      currentTargetLang = newTarget;
      try { localStorage.setItem("tubescholar_target_lang", currentTargetLang); } catch (err) {}
      updateLangLabels();

      // 자막이 있고 YouTube 영상이 로드되어 있는 경우 즉시 새 언어로 리로드
      if (currentVideoId && !isLocalVideo) {
        await reloadSubtitles({ target_lang: newTarget });
      } else {
        updateTranslationButtonState();
      }
    });
  }

  // 원문 자막 트랙 셀렉트 박스 변경 시
  const subSourceSelect = document.getElementById("sub-source-lang");
  if (subSourceSelect) {
    subSourceSelect.addEventListener("change", async (e) => {
      const newSource = e.target.value;
      if (newSource === currentSourceLang) return;

      if (isTranslatingSubtitles) {
        alert("현재 번역 작업이 진행 중입니다. 번역 완료 또는 취소 후 원문 트랙을 변경해주세요.");
        subSourceSelect.value = currentSourceLang || "";
        return;
      }

      currentSourceLang = newSource;
      if (currentVideoId && !isLocalVideo) {
        await reloadSubtitles({ source_lang: newSource });
      }
    });
  }

  // 명시적 번역 요청 버튼 (Gemini API 쿼터 보호)
  const reqTransBtn = document.getElementById("request-sub-translate-btn");
  if (reqTransBtn) {
    reqTransBtn.addEventListener("click", () => requestTranslation());
  }

  // 자동 스크롤 토글 버튼 이벤트 바인딩
  const autoScrollBtn = document.getElementById("sub-autoscroll-toggle-btn");
  if (autoScrollBtn) {
    autoScrollBtn.addEventListener("click", toggleSubtitleAutoScroll);
    updateSubtitleAutoScrollUI();
  }

  // 번역 상태 모달 닫기 버튼 이벤트 바인딩
  const closeTransModalBtn = document.getElementById("close-trans-modal-btn");
  if (closeTransModalBtn) closeTransModalBtn.addEventListener("click", closeTranslationModal);
  const cancelTransBtn = document.getElementById("cancel-trans-btn");
  if (cancelTransBtn) cancelTransBtn.addEventListener("click", closeTranslationModal);
  const completeTransBtn = document.getElementById("complete-trans-btn");
  if (completeTransBtn) completeTransBtn.addEventListener("click", closeTranslationModal);
  const abortTransBtn = document.getElementById("abort-trans-btn");
  if (abortTransBtn) abortTransBtn.addEventListener("click", abortTranslation);

  // 자막 실시간 검색 필터링 (입력이 멈춘 뒤 200ms 후 1회만 재렌더링)
  let subtitleSearchTimer = null;
  document.getElementById("subtitle-search-input").addEventListener("input", (e) => {
    const value = e.target.value;
    clearTimeout(subtitleSearchTimer);
    subtitleSearchTimer = setTimeout(() => renderSubtitlesList(value), 200);
  });

  // 자막 파일 다운로드 및 재번역
  const retransBtn = document.getElementById("retranslate-sub-btn");
  if (retransBtn) {
    retransBtn.addEventListener("click", () => requestKoreanTranslation(true));
  }
  document.getElementById("download-srt-btn").addEventListener("click", () => triggerSubtitleDownload("srt"));
  document.getElementById("download-txt-btn").addEventListener("click", () => triggerSubtitleDownload("txt"));

  // CC 자막 토글 버튼 (ON / OFF)
  const toggleCcBtn = document.getElementById("toggle-cc-btn");
  const ccBtnText = document.getElementById("cc-btn-text");
  if (toggleCcBtn) {
    toggleCcBtn.addEventListener("click", () => {
      isCcEnabled = !isCcEnabled;
      if (isCcEnabled) {
        toggleCcBtn.className = "px-2.5 py-1 bg-sky-600 hover:bg-sky-500 text-xs font-semibold rounded-lg text-white transition flex items-center space-x-1 shadow-sm";
        if (ccBtnText) ccBtnText.textContent = "CC ON";
      } else {
        toggleCcBtn.className = "px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-xs font-semibold rounded-lg text-slate-400 transition flex items-center space-x-1 border border-slate-700";
        if (ccBtnText) ccBtnText.textContent = "CC OFF";
        const overlay = document.getElementById("video-subtitle-overlay");
        if (overlay) overlay.classList.add("hidden");
      }
    });
  }

  // 영상 하단 플레이어 바 자막 언어 변경 버튼
  const ctrlSubOrig = document.getElementById("ctrl-sub-lang-orig");
  const ctrlSubKo = document.getElementById("ctrl-sub-lang-ko");
  const ctrlSubBi = document.getElementById("ctrl-sub-lang-bi");
  if (ctrlSubOrig) ctrlSubOrig.addEventListener("click", () => changeSubLanguage("original", true));
  if (ctrlSubKo) ctrlSubKo.addEventListener("click", () => changeSubLanguage("ko", true));
  if (ctrlSubBi) ctrlSubBi.addEventListener("click", () => changeSubLanguage("bilingual", true));

  // CC 자막 글자 크기 조절 버튼 (A- / A+)
  const btnFontDec = document.getElementById("btn-font-dec");
  const btnFontInc = document.getElementById("btn-font-inc");
  if (btnFontDec) btnFontDec.addEventListener("click", () => changeCcFontScale(-15));
  if (btnFontInc) btnFontInc.addEventListener("click", () => changeCcFontScale(15));

  // 자막 위치 복원 버튼
  const btnResetPos = document.getElementById("btn-reset-pos");
  if (btnResetPos) btnResetPos.addEventListener("click", resetSubtitlePosition);

  // 자막 싱크 보정 버튼 (⏪ 늦게 / 배지 클릭 초기화 / ⏩ 빠르게)
  const btnSyncLater = document.getElementById("btn-sync-later");
  const btnSyncEarlier = document.getElementById("btn-sync-earlier");
  const syncBadge = document.getElementById("sync-offset-badge");
  if (btnSyncLater) btnSyncLater.addEventListener("click", () => adjustSyncOffset(-SYNC_STEP_SEC));
  if (btnSyncEarlier) btnSyncEarlier.addEventListener("click", () => adjustSyncOffset(SYNC_STEP_SEC));
  if (syncBadge) syncBadge.addEventListener("click", () => setSyncOffset(0));
  refreshSyncBadge(true);

  // 자막 일체형 비디오 전체화면 제어 바인딩
  const floatingFsBtn = document.getElementById("floating-fullscreen-btn");
  const playerFsBtn = document.getElementById("player-fullscreen-btn");
  if (floatingFsBtn) floatingFsBtn.addEventListener("click", toggleVideoFullscreen);
  if (playerFsBtn) playerFsBtn.addEventListener("click", toggleVideoFullscreen);

  document.addEventListener("fullscreenchange", updateFullscreenUI);
  document.addEventListener("webkitfullscreenchange", updateFullscreenUI);
  document.addEventListener("mozfullscreenchange", updateFullscreenUI);
  document.addEventListener("MSFullscreenChange", updateFullscreenUI);

  // 비디오 영역 더블클릭 시 전체화면 토글 (단, 자막/버튼 클릭 제외)
  const playerWrapper = document.getElementById("video-player-wrapper");
  if (playerWrapper) {
    playerWrapper.addEventListener("dblclick", (e) => {
      if (e.target.closest("#video-subtitle-overlay") || e.target.closest("button") || e.target.closest("a")) {
        return;
      }
      toggleVideoFullscreen();
    });
  }

  // 드래그 앤 드롭 자막 위치 이동 초기화 및 초기 폰트 크기 적용
  initSubtitleDraggable();
  applyCcFontSize();

  // 로컬 비디오 플레이어 실시간 이벤트 바인딩
  const localVideoEl = document.getElementById("local-video-player");
  if (localVideoEl) {
    localVideoEl.addEventListener("timeupdate", () => {
      updateActiveSubtitle(localVideoEl.currentTime);
    });
    localVideoEl.addEventListener("seeked", () => {
      updateActiveSubtitle(localVideoEl.currentTime);
    });
    localVideoEl.addEventListener("ended", () => {
      const overlay = document.getElementById("video-subtitle-overlay");
      if (overlay) overlay.classList.add("hidden");
      clearActiveSubtitleHighlight();
    });
  }

  // 실시간 재생 위치 추적 엔진 가동
  startTimeSync();

  // 🎧 edge-tts 오디오북 엔진 초기화
  initTtsEvents();

  // 📖 집중 읽기 모드 (Zen Focus View) 엔진 초기화
  initZenModeEvents();

  checkConfig();
  initLanguages();
  loadLibrary();
});

// ============================================================
// 🎧 edge-tts 오디오북 재생 및 관리 엔진
// ============================================================
let isGeneratingAudio = false;

async function triggerAudiobookPlay() {
  if (isGeneratingAudio) return;

  const mdText = currentMarkdown || document.getElementById("note-editor-textarea")?.value || "";
  if (!mdText.trim()) {
    alert("오디오북으로 변환할 학습 노트가 없습니다. 먼저 영상을 분석해주세요.");
    return;
  }

  const btn = document.getElementById("tts-audiobook-btn");
  const icon = document.getElementById("tts-btn-icon");
  const text = document.getElementById("tts-btn-text");
  const spinner = document.getElementById("tts-btn-spinner");
  const card = document.getElementById("tts-player-card");
  const badge = document.getElementById("tts-status-badge");
  const audio = document.getElementById("tts-audio-element");
  const dlBtn = document.getElementById("tts-download-btn");
  const voiceSelect = document.getElementById("tts-voice-select");
  const speedSelect = document.getElementById("tts-speed-select");

  isGeneratingAudio = true;
  if (btn) btn.disabled = true;
  if (icon) icon.classList.add("hidden");
  if (spinner) spinner.classList.remove("hidden");
  if (text) text.textContent = "생성 중...";

  if (card) card.classList.remove("hidden");
  if (badge) {
    badge.textContent = "음성 생성 중...";
    badge.className = "px-2 py-0.5 bg-amber-500/20 text-amber-300 rounded text-[10px] font-mono animate-pulse";
  }

  const selectedVoice = voiceSelect ? voiceSelect.value : "injoon";

  try {
    const res = await fetch("/api/tts/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        note_id: currentNoteId || "current_note",
        markdown: mdText,
        voice: selectedVoice,
        speed: "+0%"
      })
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `서버 오류 (${res.status})`);
    }

    const data = await res.json();
    const audioUrl = `/api/tts/audio/${data.filename}`;

    if (audio) {
      audio.src = audioUrl;
      const curSpeed = speedSelect ? parseFloat(speedSelect.value) : 1.0;
      audio.playbackRate = curSpeed;
      audio.play().catch(e => console.log("자동 재생 대기:", e));
    }

    if (dlBtn) {
      dlBtn.href = audioUrl;
      dlBtn.download = `${currentVideoInfo?.title || 'study_note'}_audiobook.mp3`;
      dlBtn.classList.remove("hidden");
    }

    if (badge) {
      badge.textContent = data.cached ? "재생 중 (캐시)" : "재생 중 (새 생성)";
      badge.className = "px-2 py-0.5 bg-emerald-500/20 text-emerald-300 rounded text-[10px] font-mono";
    }
  } catch (err) {
    alert("오디오북 음성 생성 실패: " + err.message);
    if (badge) {
      badge.textContent = "오류 발생";
      badge.className = "px-2 py-0.5 bg-rose-500/20 text-rose-300 rounded text-[10px] font-mono";
    }
  } finally {
    isGeneratingAudio = false;
    if (btn) btn.disabled = false;
    if (icon) icon.classList.remove("hidden");
    if (spinner) spinner.classList.add("hidden");
    if (text) text.textContent = "오디오북";
  }
}

function initTtsEvents() {
  const ttsBtn = document.getElementById("tts-audiobook-btn");
  if (ttsBtn) ttsBtn.addEventListener("click", triggerAudiobookPlay);

  const closeTtsBtn = document.getElementById("close-tts-player-btn");
  const ttsCard = document.getElementById("tts-player-card");
  const audioEl = document.getElementById("tts-audio-element");
  if (closeTtsBtn) {
    closeTtsBtn.addEventListener("click", () => {
      if (audioEl) audioEl.pause();
      if (ttsCard) ttsCard.classList.add("hidden");
    });
  }

  const speedSelect = document.getElementById("tts-speed-select");
  if (speedSelect && audioEl) {
    speedSelect.addEventListener("change", (e) => {
      audioEl.playbackRate = parseFloat(e.target.value);
    });
  }

  const voiceSelect = document.getElementById("tts-voice-select");
  if (voiceSelect) {
    voiceSelect.addEventListener("change", (e) => {
      try { localStorage.setItem("tubescholar_tts_voice", e.target.value); } catch (err) {}
      if (audioEl && audioEl.src) {
        triggerAudiobookPlay();
      }
    });
  }

  loadTtsVoices();
}

async function loadTtsVoices() {
  const voiceSelect = document.getElementById("tts-voice-select");
  if (!voiceSelect) return;
  try {
    const res = await fetch("/api/tts/voices");
    if (!res.ok) return;
    const data = await res.json();
    if (data.voices && Array.isArray(data.voices)) {
      const savedVoice = localStorage.getItem("tubescholar_tts_voice");
      voiceSelect.innerHTML = "";

      const langGroups = {
        ko: "🇰🇷 한국어 (Korean)",
        en: "🇺🇸 English",
        ja: "🇯🇵 日本語 (Japanese)",
        zh: "🇨🇳 中文 (Chinese)",
        es: "🇪🇸 Español",
        fr: "🇫🇷 Français",
        de: "🇩🇪 Deutsch"
      };

      const groups = {};
      data.voices.forEach(v => {
        const grp = v.lang || "ko";
        if (!groups[grp]) groups[grp] = [];
        groups[grp].push(v);
      });

      for (const [lang, gVoices] of Object.entries(groups)) {
        const optgroup = document.createElement("optgroup");
        optgroup.label = langGroups[lang] || lang.toUpperCase();
        gVoices.forEach(v => {
          const opt = document.createElement("option");
          opt.value = v.key;
          opt.textContent = v.name;
          if (savedVoice === v.key) opt.selected = true;
          optgroup.appendChild(opt);
        });
        voiceSelect.appendChild(optgroup);
      }

      if (!savedVoice) {
        const uiLang = typeof getUiLang === "function" ? getUiLang() : "ko";
        if (uiLang === "en") voiceSelect.value = "christopher";
        else if (uiLang === "ja") voiceSelect.value = "keita";
        else voiceSelect.value = "injoon";
      }
    }
  } catch (e) {
    console.warn("Failed to load TTS voices:", e);
  }
}

// ============================================================
// 📖 2단계 집중 독서 팝업 모달 (Reader Popup Modal) & 테마 & 목차(TOC) 엔진
// ============================================================
let isReaderPopupOpen = false;
let currentReadingTheme = localStorage.getItem("tubescholar_reading_theme") || "dark";
let currentZenFontScale = parseInt(localStorage.getItem("tubescholar_zen_font_scale") || "100");
let isReaderTocOpen = false;

function applyReadingTheme(theme) {
  currentReadingTheme = theme;
  const popup = document.getElementById("reader-popup-modal");
  if (popup) {
    popup.classList.remove("theme-sepia", "theme-light");
    if (theme === "sepia") popup.classList.add("theme-sepia");
    else if (theme === "light") popup.classList.add("theme-light");
  }
  localStorage.setItem("tubescholar_reading_theme", theme);

  // 버튼 스타일 업데이트
  const darkBtn = document.getElementById("reader-theme-dark");
  const sepiaBtn = document.getElementById("reader-theme-sepia");
  const lightBtn = document.getElementById("reader-theme-light");
  if (darkBtn) {
    darkBtn.className = theme === "dark" 
      ? "px-2.5 py-1 rounded-lg text-xs font-bold text-white bg-slate-700 transition shadow-sm" 
      : "px-2.5 py-1 rounded-lg text-xs font-medium text-slate-400 hover:text-white transition";
  }
  if (sepiaBtn) {
    sepiaBtn.className = theme === "sepia" 
      ? "px-2.5 py-1 rounded-lg text-xs font-bold text-amber-900 bg-amber-200 transition shadow-sm" 
      : "px-2.5 py-1 rounded-lg text-xs font-medium text-amber-300/70 hover:text-amber-200 transition";
  }
  if (lightBtn) {
    lightBtn.className = theme === "light" 
      ? "px-2.5 py-1 rounded-lg text-xs font-bold text-slate-900 bg-slate-100 transition shadow-sm" 
      : "px-2.5 py-1 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 transition";
  }
}

function applyZenFontScale(scale) {
  currentZenFontScale = Math.max(70, Math.min(180, scale));
  const article = document.getElementById("reader-popup-article");
  if (article) {
    article.style.fontSize = `${(currentZenFontScale / 100) * 1.05}rem`;
    article.style.lineHeight = `${1.85 + (currentZenFontScale - 100) * 0.003}`;
  }
  const badge = document.getElementById("reader-font-badge");
  if (badge) badge.textContent = `${currentZenFontScale}%`;
  localStorage.setItem("tubescholar_zen_font_scale", currentZenFontScale.toString());
}

// 좌측 고정 목차 기본 상태: 저장된 값이 없으면 기본 true (열림)
let isSidebarPinned = (function() {
  try {
    const saved = localStorage.getItem("tubescholar_reader_sidebar_pinned");
    return saved === null ? true : saved === "1";
  } catch (e) {
    return true;
  }
})();

function generateReaderPopupToc() {
  const article = document.getElementById("reader-popup-article");
  const sidebarList = document.getElementById("reader-sidebar-toc-list");
  const tocBadge = document.getElementById("reader-toc-badge");

  if (!article) return;

  const headings = article.querySelectorAll("h1, h2, h3, h4");
  const count = headings ? headings.length : 0;

  if (tocBadge) {
    if (count > 0) {
      tocBadge.textContent = count.toString();
      tocBadge.classList.remove("hidden");
    } else {
      tocBadge.classList.add("hidden");
    }
  }

  const emptyHtml = `<div class="text-center py-6 text-slate-500 text-xs space-y-1">
    <div>📑 감지된 제목(Heading)이 없습니다.</div>
    <div class="text-[10px] text-slate-600">노트에 # 또는 ## 제목 태그가 있으면 목차가 자동 생성됩니다.</div>
  </div>`;

  if (!headings || count === 0) {
    if (sidebarList) sidebarList.innerHTML = emptyHtml;
    return;
  }

  const itemsData = [];
  headings.forEach((h, idx) => {
    if (!h.id) {
      h.id = `reader-heading-${idx}`;
    }
    const tag = h.tagName.toLowerCase();
    const rawText = h.textContent.trim();
    const cleanText = rawText.replace(/^[#\s]+/, '').trim() || rawText;

    let indentClass = "pl-2 font-bold text-white text-xs py-1.5";
    let icon = "📌";
    if (tag === "h1") {
      indentClass = "pl-2 font-bold text-sky-300 text-xs py-1.5 border-l-2 border-sky-400";
      icon = "🏷️";
    } else if (tag === "h2") {
      indentClass = "pl-3.5 font-semibold text-slate-200 text-xs py-1.5 border-l-2 border-slate-700 hover:border-sky-400";
      icon = "🔹";
    } else if (tag === "h3") {
      indentClass = "pl-6 text-slate-300 text-[11px] py-1 border-l-2 border-slate-800 hover:border-sky-400";
      icon = "▫️";
    } else if (tag === "h4") {
      indentClass = "pl-8 text-slate-400 text-[10px] py-0.5 border-l-2 border-slate-800";
      icon = "▪️";
    }

    itemsData.push({
      id: h.id,
      tag: tag,
      title: cleanText,
      fullText: rawText,
      indentClass: indentClass,
      icon: icon,
      headingEl: h
    });
  });

  if (!sidebarList) return;
  sidebarList.innerHTML = "";
  itemsData.forEach((item) => {
    const a = document.createElement("a");
    a.className = `block px-2.5 rounded-lg text-left transition truncate cursor-pointer hover:bg-slate-800/90 hover:text-sky-300 ${item.indentClass}`;
    a.title = item.fullText;
    a.innerHTML = `<span class="mr-1.5 text-[10px] opacity-75">${item.icon}</span><span>${escapeHtmlStr(item.title)}</span>`;

    a.addEventListener("click", (e) => {
      e.preventDefault();
      item.headingEl.scrollIntoView({ behavior: "smooth", block: "start" });
      
      // 도착 지점 헤딩 강조 점프 애니메이션
      item.headingEl.classList.remove("section-jump-flash");
      void item.headingEl.offsetWidth; // trigger reflow
      item.headingEl.classList.add("section-jump-flash");
      setTimeout(() => item.headingEl.classList.remove("section-jump-flash"), 1800);

      // 하이라이트 활성화 표시
      sidebarList.querySelectorAll("a").forEach(el => el.classList.remove("bg-sky-600/20", "text-sky-300", "font-bold"));
      a.classList.add("bg-sky-600/20", "text-sky-300", "font-bold");
    });

    sidebarList.appendChild(a);
  });
}

function updateSidebarPinUI() {
  const sidebar = document.getElementById("reader-popup-toc-panel");
  const tocBtn = document.getElementById("reader-toc-toggle-btn");

  if (sidebar) {
    if (isSidebarPinned) {
      sidebar.classList.remove("hidden");
    } else {
      sidebar.classList.add("hidden");
    }
  }

  if (tocBtn) {
    if (isSidebarPinned) {
      tocBtn.className = "px-2.5 py-1.5 bg-sky-600 hover:bg-sky-500 text-white border border-sky-400 rounded-xl transition flex items-center space-x-1.5 font-bold shadow-md ring-2 ring-sky-400/30 active:scale-95";
    } else {
      tocBtn.className = "px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 rounded-xl transition flex items-center space-x-1.5 font-semibold shadow-sm active:scale-95";
    }
  }
}

function toggleSidebarPin(forceState) {
  if (typeof forceState === "boolean") {
    isSidebarPinned = forceState;
  } else {
    isSidebarPinned = !isSidebarPinned;
  }

  try {
    localStorage.setItem("tubescholar_reader_sidebar_pinned", isSidebarPinned ? "1" : "0");
  } catch (e) {}

  updateSidebarPinUI();

  if (isSidebarPinned) {
    generateReaderPopupToc();
  }
}

function openReaderPopup() {
  const noteContent = document.getElementById("note-content");
  const editorText = document.getElementById("note-editor-textarea")?.value?.trim() || "";
  const mdSource = (currentMarkdown && currentMarkdown.trim()) || editorText;
  const hasContent = (noteContent && noteContent.innerHTML.trim() && !noteContent.classList.contains("hidden")) || !!mdSource;

  if (!hasContent) {
    alert("읽기 모드를 열기 위한 학습 노트가 없습니다. 먼저 영상을 분석하거나 보관함에서 노트를 불러와주세요.");
    return;
  }

  const popup = document.getElementById("reader-popup-modal");
  const popupTitle = document.getElementById("reader-popup-title");
  const popupArticle = document.getElementById("reader-popup-article");

  if (popupTitle) {
    popupTitle.textContent = currentVideoInfo?.title || document.getElementById("video-title")?.textContent || "학습 노트 집중 독서";
  }

  if (popupArticle) {
    if (noteContent && noteContent.innerHTML.trim() && !noteContent.classList.contains("hidden")) {
      popupArticle.innerHTML = noteContent.innerHTML;
    } else if (mdSource) {
      const cleanMd = stripFrontmatter(mdSource);
      const rawHtml = marked.parse(cleanMd);
      popupArticle.innerHTML = typeof processMarkdownHtml === 'function' ? processMarkdownHtml(rawHtml) : rawHtml;
    }

    // 팝업 내부 타임스탬프 클릭 시 영상 탐색 연동
    const tsBtns = popupArticle.querySelectorAll(".timestamp-tag");
    tsBtns.forEach(btn => {
      btn.addEventListener("click", () => {
        const secs = parseFloat(btn.getAttribute("data-seconds"));
        if (!isNaN(secs)) seekVideo(secs);
      });
    });
  }

  try {
    applyReadingTheme(currentReadingTheme);
    applyZenFontScale(currentZenFontScale);
    updateSidebarPinUI();
    generateReaderPopupToc();
  } catch (err) {
    console.warn("Reader popup initialization error:", err);
  }

  if (popup) {
    popup.classList.remove("hidden");
    isReaderPopupOpen = true;
  }
}

function closeReaderPopup() {
  const popup = document.getElementById("reader-popup-modal");
  if (popup) {
    popup.classList.add("hidden");
    isReaderPopupOpen = false;
  }
}

function toggleZenMode() {
  if (isReaderPopupOpen) {
    closeReaderPopup();
  } else {
    openReaderPopup();
  }
}

function initZenModeEvents() {
  if (window._hasZenEventsInitialized) return;
  window._hasZenEventsInitialized = true;

  const zenToggleBtn = document.getElementById("zen-mode-toggle-btn");
  if (zenToggleBtn) {
    zenToggleBtn.addEventListener("click", () => openReaderPopup());
  }

  const closeBtn = document.getElementById("close-reader-popup-btn");
  if (closeBtn) {
    closeBtn.addEventListener("click", () => closeReaderPopup());
  }

  // 테마 스위처 바인딩
  const darkBtn = document.getElementById("reader-theme-dark");
  const sepiaBtn = document.getElementById("reader-theme-sepia");
  const lightBtn = document.getElementById("reader-theme-light");
  if (darkBtn) darkBtn.addEventListener("click", () => applyReadingTheme("dark"));
  if (sepiaBtn) sepiaBtn.addEventListener("click", () => applyReadingTheme("sepia"));
  if (lightBtn) lightBtn.addEventListener("click", () => applyReadingTheme("light"));

  // 폰트 크기 바인딩
  const fontDec = document.getElementById("reader-font-dec");
  const fontInc = document.getElementById("reader-font-inc");
  if (fontDec) fontDec.addEventListener("click", () => applyZenFontScale(currentZenFontScale - 10));
  if (fontInc) fontInc.addEventListener("click", () => applyZenFontScale(currentZenFontScale + 10));

  // 📑 목차 버튼 클릭 -> 좌측 고정 목차 사이드바 열기/닫기
  const tocBtn = document.getElementById("reader-toc-toggle-btn");
  if (tocBtn) {
    tocBtn.addEventListener("click", () => {
      toggleSidebarPin();
    });
  }

  // 좌측 사이드바 닫기 버튼 (✕)
  const closeSidebarBtn = document.getElementById("close-reader-toc-panel-btn");
  if (closeSidebarBtn) {
    closeSidebarBtn.addEventListener("click", () => {
      toggleSidebarPin(false);
    });
  }

  // 인쇄/PDF 저장 버튼
  const printBtn = document.getElementById("reader-print-btn");
  if (printBtn) {
    printBtn.addEventListener("click", () => window.print());
  }

  // 오디오북 재생 바로가기
  const audioBtn = document.getElementById("reader-audio-btn");
  if (audioBtn) {
    audioBtn.addEventListener("click", () => triggerAudiobookPlay());
  }

  // 단축키: F (자막 일체형 비디오 전체화면), Z (독서 팝업 열기/닫기), Esc (전체화면 또는 팝업 닫기)
  window.addEventListener("keydown", (e) => {
    const activeEl = document.activeElement;
    const isInput = activeEl && (activeEl.tagName === "INPUT" || activeEl.tagName === "TEXTAREA" || activeEl.tagName === "SELECT" || activeEl.isContentEditable);
    if (isInput) return;
    // Ctrl+F(찾기)·Ctrl+Z 등 브라우저/OS 조합키는 가로채지 않음
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    if (e.key === "f" || e.key === "F") {
      e.preventDefault();
      toggleVideoFullscreen();
    } else if (e.key === "z" || e.key === "Z") {
      e.preventDefault();
      toggleZenMode();
    } else if (e.code === "BracketLeft" || e.key === "[") {
      e.preventDefault();
      adjustSyncOffset(-SYNC_STEP_SEC);
    } else if (e.code === "BracketRight" || e.key === "]") {
      e.preventDefault();
      adjustSyncOffset(SYNC_STEP_SEC);
    } else if (e.code === "Backslash" || e.key === "\\") {
      e.preventDefault();
      setSyncOffset(0);
    } else if (e.key === "Escape") {
      if (isVideoFullscreen()) {
        e.preventDefault();
        toggleVideoFullscreen();
      } else if (isReaderPopupOpen) {
        e.preventDefault();
        closeReaderPopup();
      }
    }
  });

  // 프로그램 안전 종료 버튼
  const shutdownBtn = document.getElementById("shutdown-btn");
  if (shutdownBtn) {
    shutdownBtn.addEventListener("click", async () => {
      const msg = typeof t === "function" ? t("shutdown_confirm") : "TubeScholar 프로그램을 종료하시겠습니까?";
      if (confirm(msg)) {
        try {
          await fetch("/api/system/shutdown", { method: "POST" });
        } catch (e) {}
        document.body.innerHTML = `
          <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;background:#0f172a;color:#94a3b8;font-family:sans-serif;text-align:center;">
            <h1 style="color:#f8fafc;font-size:24px;margin-bottom:12px;">👋 TubeScholar</h1>
            <p style="font-size:14px;">Server stopped. You may close this tab.</p>
          </div>
        `;
      }
    });
  }

  // 브라우저 탭/창 종료 시 백그라운드 프로세스 즉각 종료 신호 전송
  const sendCloseSignal = () => {
    try {
      fetch("/api/system/browser-close", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-tubescholar": "1" },
        keepalive: true
      }).catch(() => {});
    } catch (e) {}
  };
  window.addEventListener("pagehide", sendCloseSignal);
  window.addEventListener("beforeunload", sendCloseSignal);

  // 브라우저 탭 활성 생존 신호 (주기적으로 서버에 신호를 보내 비정상 종료 시에도 워치독으로 자동 종료)
  function initHeartbeat() {
    const ping = () => {
      fetch("/api/system/heartbeat", { method: "POST" }).catch(() => {});
    };
    setInterval(ping, 3000);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) ping();
    });
    ping();
  }
  initHeartbeat();
}



