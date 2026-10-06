import asyncio
import base64
import json
import os
import subprocess
import time
import urllib.request
import websockets

TARGET_URL = "http://127.0.0.1:8000"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "tubescholar_neutral_shot")

from test_demo_data import SAMPLE_NOTE_KO, SAMPLE_NOTE_EN, SUBTITLES_DATA, LIBRARY_ITEMS

async def capture_neutral_all():
    chrome_proc = subprocess.Popen([
        CHROME_PATH,
        "--headless=new",
        "--remote-debugging-port=9222",
        "--window-size=1920,1080",
        f"--user-data-dir={USER_DATA}",
        TARGET_URL
    ])
    
    msg_id = 0
    
    try:
        # Wait for Chrome
        for _ in range(25):
            try:
                with urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=1) as resp:
                    targets = json.loads(resp.read().decode())
                    if targets:
                        break
            except Exception:
                time.sleep(0.3)
        
        target = next((t for t in targets if "127.0.0.1:8000" in t.get("url", "")), None)
        if not target:
            target = targets[0]
            
        ws_url = target["webSocketDebuggerUrl"]
        print(f"Connecting to {ws_url}...")
        
        async with websockets.connect(ws_url, max_size=50*1024*1024) as ws:
            async def send(method, params=None):
                nonlocal msg_id
                msg_id += 1
                cur_id = msg_id
                req = {"id": cur_id, "method": method, "params": params or {}}
                await ws.send(json.dumps(req))
                while True:
                    resp = json.loads(await ws.recv())
                    if resp.get("id") == cur_id:
                        return resp

            await send("Page.enable")
            await send("Runtime.enable")
            await asyncio.sleep(1.5)

            async def eval_js(code):
                wrapped = f"(() => {{ {code} }})()"
                res = await send("Runtime.evaluate", {
                    "expression": wrapped,
                    "awaitPromise": True,
                    "returnByValue": True
                })
                if "exceptionDetails" in res.get("result", {}):
                    print(f"JS Exception: {res['result']['exceptionDetails']}")
                return res

            async def take_screenshot(filename):
                res = await send("Page.captureScreenshot", {"format": "png"})
                img_data = base64.b64decode(res["result"]["data"])
                out_path = os.path.join(OUTPUT_DIR, filename)
                with open(out_path, "wb") as f:
                    f.write(img_data)
                print(f"Captured {filename} ({len(img_data):,} bytes)")

            # Setup Mock Video Player & Subtitles & Metadata & Note
            setup_script = f"""
                setUiLang('ko');
                applyI18n();

                // 1. Hide placeholder and real player
                const ph = document.getElementById('youtube-player-placeholder');
                if (ph) ph.style.display = 'none';
                const yp = document.getElementById('player');
                if (yp) yp.style.display = 'none';
                const lp = document.getElementById('local-video-player');
                if (lp) lp.style.display = 'none';

                // 2. Inject sleek mock video canvas
                let mockCanvas = document.getElementById('mock-video-canvas');
                if (!mockCanvas) {{
                    mockCanvas = document.createElement('div');
                    mockCanvas.id = 'mock-video-canvas';
                    mockCanvas.className = 'absolute inset-0 w-full h-full flex flex-col justify-between p-5 select-none';
                    mockCanvas.style.background = 'radial-gradient(circle at 70% 30%, #1e1b4b 0%, #0f172a 50%, #020617 100%)';
                    mockCanvas.innerHTML = `
                        <!-- Top Bar: Channel & Badge -->
                        <div style="display: flex; align-items: center; justify-content: space-between; z-index: 10;">
                            <div style="display: flex; align-items: center; gap: 9px; background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(8px); padding: 6px 14px; border-radius: 9999px; border: 1px solid rgba(99, 102, 241, 0.4); box-shadow: 0 4px 12px rgba(0,0,0,0.4);">
                                <span style="display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 9999px; background: linear-gradient(135deg, #6366f1, #38bdf8); font-size: 11px;">🎓</span>
                                <span style="font-size: 12px; font-weight: 700; color: #f1f5f9; letter-spacing: -0.01em;">TubeScholar Academy</span>
                                <span style="width: 6px; height: 6px; border-radius: 9999px; background: #10b981; box-shadow: 0 0 8px #10b981;"></span>
                                <span style="font-size: 10px; font-weight: 700; color: #34d399; font-family: monospace;">1080p HD</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 6px; background: rgba(15, 23, 42, 0.85); backdrop-filter: blur(8px); padding: 5px 12px; border-radius: 9999px; border: 1px solid rgba(51, 65, 85, 0.6); font-size: 11px; font-family: monospace; color: #cbd5e1;">
                                <span>⏱️ 05:30 / 14:20</span>
                            </div>
                        </div>

                        <!-- Center: Attention Mechanism Graphic & Red Play Button -->
                        <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; margin: auto; z-index: 10; text-align: center; gap: 14px;">
                            <div style="position: relative; display: flex; align-items: center; justify-content: center;">
                                <svg width="240" height="90" viewBox="0 0 240 90" fill="none" style="filter: drop-shadow(0 0 14px rgba(99, 102, 241, 0.35));">
                                    <path d="M 40 20 L 120 45" stroke="#6366f1" stroke-width="1.5" stroke-dasharray="3 3" opacity="0.6"/>
                                    <path d="M 40 45 L 120 45" stroke="#818cf8" stroke-width="2.5" opacity="0.9"/>
                                    <path d="M 40 70 L 120 45" stroke="#6366f1" stroke-width="1.5" stroke-dasharray="3 3" opacity="0.6"/>
                                    <path d="M 120 45 L 200 25" stroke="#38bdf8" stroke-width="2" opacity="0.85"/>
                                    <path d="M 120 45 L 200 65" stroke="#34d399" stroke-width="2" opacity="0.85"/>
                                    <circle cx="40" cy="20" r="10" fill="#1e293b" stroke="#3b82f6" stroke-width="2"/>
                                    <text x="40" y="24" fill="#93c5fd" font-size="10" font-weight="bold" text-anchor="middle" font-family="sans-serif">Q</text>
                                    <circle cx="40" cy="45" r="10" fill="#1e293b" stroke="#6366f1" stroke-width="2.5"/>
                                    <text x="40" y="49" fill="#c7d2fe" font-size="10" font-weight="bold" text-anchor="middle" font-family="sans-serif">K</text>
                                    <circle cx="40" cy="70" r="10" fill="#1e293b" stroke="#8b5cf6" stroke-width="2"/>
                                    <text x="40" y="74" fill="#ddd6fe" font-size="10" font-weight="bold" text-anchor="middle" font-family="sans-serif">V</text>
                                    <rect x="105" y="32" width="30" height="26" rx="6" fill="#312e81" stroke="#a5b4fc" stroke-width="2"/>
                                    <text x="120" y="49" fill="#e0e7ff" font-size="11" font-weight="bold" text-anchor="middle" font-family="sans-serif">Attn</text>
                                    <circle cx="200" cy="25" r="10" fill="#1e293b" stroke="#38bdf8" stroke-width="2"/>
                                    <text x="200" y="29" fill="#7dd3fc" font-size="10" font-weight="bold" text-anchor="middle" font-family="sans-serif">O₁</text>
                                    <circle cx="200" cy="65" r="10" fill="#1e293b" stroke="#34d399" stroke-width="2"/>
                                    <text x="200" y="69" fill="#6ee7b7" font-size="10" font-weight="bold" text-anchor="middle" font-family="sans-serif">O₂</text>
                                </svg>
                                <div style="position: absolute; width: 68px; height: 46px; background-color: #ef4444; border-radius: 14px; box-shadow: 0 8px 24px rgba(239, 68, 68, 0.55); display: flex; align-items: center; justify-content: center; cursor: pointer; border: 1.5px solid rgba(255, 255, 255, 0.35);">
                                    <svg style="width: 24px; height: 24px; fill: white; margin-left: 3px;" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                                </div>
                            </div>
                            <div>
                                <h2 style="font-size: 19px; font-weight: 800; color: #ffffff; letter-spacing: -0.01em; text-shadow: 0 2px 8px rgba(0,0,0,0.8); margin: 0;">Transformer Architecture & Self-Attention</h2>
                                <p style="font-size: 12px; color: #a5b4fc; font-family: monospace; margin-top: 4px; font-weight: 600;">Attention(Q, K, V) = softmax(QKᵀ / √dₖ) V</p>
                            </div>
                        </div>

                        <!-- Bottom Spacer -->
                        <div style="height: 50px;"></div>
                    `;
                    const wrapper = document.getElementById('video-player-wrapper');
                    wrapper.insertBefore(mockCanvas, wrapper.firstChild);
                }}

                // 3. Setup Subtitle Overlay
                const overlay = document.getElementById('video-subtitle-overlay');
                if (overlay) {{
                    overlay.classList.remove('hidden');
                    overlay.style.bottom = '16px';
                    overlay.style.left = '50%';
                    overlay.style.transform = 'translateX(-50%)';
                    const subKo = document.getElementById('video-sub-ko');
                    if (subKo) subKo.textContent = '어텐션 메커니즘은 문장 내 각 단어가 서로 어떤 연관성을 가지는지 가중치를 계산합니다.';
                    const subOrig = document.getElementById('video-sub-orig');
                    if (subOrig) subOrig.textContent = 'The attention mechanism computes relational weights between words in context.';
                }}

                // 4. Show Player Controls
                const controls = document.getElementById('player-controls');
                if (controls) {{
                    controls.classList.remove('hidden');
                }}

                // 5. Setup Video Metadata Card
                const metaCard = document.getElementById('video-meta-card');
                if (metaCard) metaCard.classList.remove('hidden');
                const metaChannel = document.getElementById('meta-channel');
                if (metaChannel) metaChannel.textContent = 'TUBESCHOLAR ACADEMY';
                const metaTitle = document.getElementById('meta-title');
                if (metaTitle) metaTitle.textContent = 'AI & Deep Learning: Transformer & Attention Mechanism Explained';
                const metaDuration = document.getElementById('meta-duration');
                if (metaDuration) metaDuration.textContent = '14:20';
                const metaDesc = document.getElementById('meta-desc');
                if (metaDesc) metaDesc.textContent = '자막: 원문 (공식) → 한국어 (Gemini 번역)';
                const origLink = document.getElementById('meta-orig-link');
                if (origLink) origLink.classList.add('hidden');

                // 6. Render Study Note
                currentNoteId = 'demo_transformer';
                renderMarkdownNote({json.dumps(SAMPLE_NOTE_KO)}, {{ key: "note_status_saved" }}, currentNoteId);

                // 7. Store Subtitles Data in App State
                const subs = {json.dumps(SUBTITLES_DATA)};
                currentSubtitles = subs;
                const subCountBadge = document.getElementById('sub-count-badge');
                if (subCountBadge) subCountBadge.textContent = subs.length;
            """

            print("Applying neutral demo setup...")
            await eval_js(setup_script)
            await asyncio.sleep(2.0)

            # 1. Main Split View (Korean)
            print("1. Capturing Neutral Main Split View (KO)...")
            await eval_js("switchViewTab('note');")
            await asyncio.sleep(1.0)
            await take_screenshot("tubescholar_main_splitview.png")

            # 2. Main Split View (English)
            print("2. Capturing Neutral Main Split View (EN)...")
            await eval_js(f"""
                setUiLang('en');
                applyI18n();
                renderMarkdownNote({json.dumps(SAMPLE_NOTE_EN)}, {{ key: "note_status_saved" }}, 'demo_transformer');
                const subKo = document.getElementById('video-sub-ko');
                if (subKo) subKo.textContent = 'The attention mechanism computes relational weights between words in context.';
                const subOrig = document.getElementById('video-sub-orig');
                if (subOrig) subOrig.textContent = 'Query, Key, and Value vectors map inputs to contextual distributions.';
                const metaDesc = document.getElementById('meta-desc');
                if (metaDesc) metaDesc.textContent = 'Subtitles: Official English → Korean (Gemini Translation)';
            """)
            await asyncio.sleep(1.5)
            await take_screenshot("tubescholar_main_splitview_en.png")

            # Switch back to KO for feature views
            await eval_js(f"""
                setUiLang('ko');
                applyI18n();
                renderMarkdownNote({json.dumps(SAMPLE_NOTE_KO)}, {{ key: "note_status_saved" }}, 'demo_transformer');
                const subKo = document.getElementById('video-sub-ko');
                if (subKo) subKo.textContent = '어텐션 메커니즘은 문장 내 각 단어가 서로 어떤 연관성을 가지는지 가중치를 계산합니다.';
                const subOrig = document.getElementById('video-sub-orig');
                if (subOrig) subOrig.textContent = 'The attention mechanism computes relational weights between words in context.';
                const metaDesc = document.getElementById('meta-desc');
                if (metaDesc) metaDesc.textContent = '자막: 원문 (공식) → 한국어 (Gemini 번역)';
            """)
            await asyncio.sleep(1.0)

            # 3. Interactive Subtitles Studio (Bilingual)
            print("3. Capturing Neutral Subtitles Studio...")
            await eval_js(f"""
                switchViewTab('subtitles');
                currentSubLang = 'bilingual';
                currentSubtitles = {json.dumps(SUBTITLES_DATA)};
                renderSubtitlesList();

                // Highlight both toggle button
                const btnBi = document.getElementById('sub-lang-bilingual');
                if (btnBi) btnBi.className = 'px-2.5 py-1 rounded-md text-xs font-semibold bg-sky-600 text-white shadow-sm transition';
                const btnOrig = document.getElementById('sub-lang-original');
                if (btnOrig) btnOrig.className = 'px-2.5 py-1 rounded-md text-xs font-semibold text-slate-400 hover:text-white transition';
                const btnKo = document.getElementById('sub-lang-ko');
                if (btnKo) btnKo.className = 'px-2.5 py-1 rounded-md text-xs font-semibold text-slate-400 hover:text-white transition';
            """)
            await asyncio.sleep(1.2)
            await take_screenshot("tubescholar_subtitles_studio.png")

            # 4. Neural Audiobook & Dubbing Player
            print("4. Capturing Neutral Audiobook Player...")
            await eval_js("""
                switchViewTab('note');
                const card = document.getElementById('tts-player-card');
                if (card) {
                    card.classList.remove('hidden');
                    const badge = document.getElementById('tts-status-badge');
                    if (badge) {
                        badge.textContent = '낭독 중 (Playing)';
                        badge.className = 'px-2 py-0.5 bg-emerald-500/20 text-emerald-300 rounded text-[10px] font-mono flex-shrink-0 animate-pulse';
                    }
                }
            """)
            await asyncio.sleep(1.0)
            await take_screenshot("tubescholar_audiobook_player.png")

            # Hide TTS player card
            await eval_js("""
                const card = document.getElementById('tts-player-card');
                if (card) card.classList.add('hidden');
            """)
            await asyncio.sleep(0.5)

            # 5. Zen Reader View
            print("5. Capturing Neutral Zen Reader View...")
            await eval_js("toggleZenMode();")
            await asyncio.sleep(1.8)
            await take_screenshot("tubescholar_zen_reader.png")
            
            # Close Zen mode
            await eval_js("toggleZenMode();")
            await asyncio.sleep(1.0)

            # 6. Library Drawer with Clean Educational Items
            print("6. Capturing Neutral Library Drawer...")
            await eval_js(f"""
                toggleDrawer(true);
                const libItems = {json.dumps(LIBRARY_ITEMS)};
                const libContainer = document.getElementById('library-list');
                if (libContainer) {{
                    libContainer.innerHTML = '';
                    libItems.forEach(item => {{
                        const card = document.createElement('div');
                        card.className = 'p-3 bg-slate-900/90 hover:bg-slate-800/90 rounded-xl border border-slate-800 hover:border-sky-500/40 transition cursor-pointer flex items-center space-x-3 group shadow-md';
                        card.innerHTML = `
                            <div style="width: 44px; height: 44px; border-radius: 10px; background: linear-gradient(135deg, #1e1b4b, #0f172a); border: 1px solid rgba(99, 102, 241, 0.3); display: flex; align-items: center; justify-content: center; font-size: 20px; flex-shrink: 0; box-shadow: inset 0 2px 4px rgba(0,0,0,0.4);">
                                ${{item.icon}}
                            </div>
                            <div class="flex-1 min-w-0">
                                <h4 class="text-xs font-bold text-slate-200 group-hover:text-sky-300 transition truncate leading-snug">${{item.title}}</h4>
                                <div class="flex items-center space-x-2 mt-1">
                                    <span class="text-[10px] text-indigo-400 font-medium">${{item.channel}}</span>
                                    <span class="text-[10px] text-slate-500">•</span>
                                    <span class="text-[10px] text-slate-500 font-mono">${{item.date.split(' ')[0]}}</span>
                                </div>
                            </div>
                        `;
                        libContainer.appendChild(card);
                    }});
                }}
                const drawerCount = document.getElementById('drawer-count');
                if (drawerCount) drawerCount.textContent = '(6개)';
            """)
            await asyncio.sleep(1.5)
            await take_screenshot("tubescholar_library_drawer.png")
            await eval_js("toggleDrawer(false);")
            await asyncio.sleep(0.5)

            # 7. Settings Modal
            print("7. Capturing Neutral Settings Modal...")
            await eval_js("""
                const modal = document.getElementById('settings-modal');
                if (modal) modal.classList.remove('hidden');
            """)
            await asyncio.sleep(1.0)
            await take_screenshot("tubescholar_settings_modal.png")
            await eval_js("""
                const modal = document.getElementById('settings-modal');
                if (modal) modal.classList.add('hidden');
            """)

            print("Done! All neutral screenshots successfully saved to docs/images.")

    finally:
        chrome_proc.terminate()

if __name__ == "__main__":
    asyncio.run(capture_neutral_all())
