# 🎓 TubeScholar - YouTube & Local Video LLM Deep Study Studio

[🇰🇷 한국어 설명서](README.md) | **English**

**TubeScholar** is an AI-powered interactive learning workstation designed for mastering technical talks, academic lectures, and knowledge-dense videos. Powered by **Google Gemini LLM**, it goes beyond simple translation to deliver **[subtitle error correction + timestamped summaries + Deep Dive knowledge expansion + technical glossaries + comprehension self-checks]**.

---

## 🌟 Key Features

### 1. ⏱️ Interactive Timestamped Split-View
- **Left Panel**: Integrated video player supporting both YouTube streams and offline local video files (`.mp4`, `.webm`, `.mkv`) with `.srt` subtitle tracks.
- **Right Panel**: Structured Markdown study note. Clicking any timestamp (e.g. `[03:25]`) instantly jumps playback to that exact moment.
- **Draggable CC Subtitle Overlay**: Real-time subtitles rendered directly over the video with custom font sizing, sync adjustment (`[` and `]`), and full-screen view.

### 2. 🧠 LLM Deep Knowledge Expansion (Deep Dive)
- **Contextual Correction**: Auto-corrects terminology, proper nouns, and speech-to-text misrecognitions in video transcripts.
- **Deep Dive Callouts**: Explains background theories, equations, architecture patterns, and prerequisites referenced in passing.
- **Technical Glossary**: Comprehensive table of key terms and context-specific meanings.
- **Comprehension Check**: Interactive self-study quiz questions reinforcing core concepts.
- **Multi-language Generation**: Generates study notes in 17 world languages.

### 3. 💬 Interactive Subtitle Studio
- **3 Reading Modes**: `Original`, `Translated`, and `Both` (bilingual display).
- **Synchronized Auto-Scroll**: Highlights and scrolls automatically to the currently playing subtitle line (with a compact `📜` toggle).
- **Instant Search & Export**: Full-text keyword search across lines; export to `.SRT` and `.TXT`.

### 4. 🎧 AI Neural Audiobook (edge-tts)
- Listen to study notes like an audiobook with high-quality Microsoft Neural voices (`edge-tts`).
- Configurable narration speed and voice models with one-click MP3 download.

### 5. 📖 Zen Reader View
- Distraction-free full reading view with Dark, Sepia, and Light paper themes, adjustable typography, and an automatic floating Table of Contents (TOC).

### 6. 🌐 Clean Bilingual UI & Persistent Storage
- Streamlined modern interface available in **Korean** and **English**.
- All study notes are stored permanently on your machine in standard Markdown (`data/notes/`), ready to be synced with **Obsidian**, **Logseq**, or **Notion**.
- Built-in library drawer for lightning-fast search and management of previously analyzed videos.

---

## 🚀 Quick Start

### Installation & Launch

#### Option A: Windows Installer (Recommended for non-developers)
Download and run `TubeScholar-Setup-v1.0.0.exe` from the [Latest Release](https://github.com/makopss/TubeScholar/releases). It includes everything required—no Python installation needed!

#### Option B: Run from Source
1. **Clone the repository:**
   ```bash
   git clone https://github.com/makopss/TubeScholar.git
   cd TubeScholar
   ```

2. **Set up Python Virtual Environment:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate      # Windows
   # source .venv/bin/activate # macOS/Linux
   pip install -r requirements.txt
   ```

3. **Compile Frontend Styles (Optional if modified):**
   ```bash
   npm install
   npm run build:css
   ```

4. **Launch TubeScholar:**
   ```bash
   python run.py
   ```
   The browser will automatically open to `http://127.0.0.1:8000`.

---

## ⚙️ Configuration

Click the ⚙️ **Settings** icon in the top header:
- **Gemini API Key**: Enter your free [Google AI Studio API key](https://aistudio.google.com/). Stored locally and securely in `.env`.
- **Model Selection**: Choose between `Gemini 2.5 Flash` (default, ultrafast) or `Gemini 2.5 Pro` (deep reasoning).
- **Groq API Key (Optional)**: For ultra-fast transcript Whisper processing.

---

## 🛠️ Tech Stack

- **Backend**: FastAPI, Python 3.12, Uvicorn, yt-dlp, youtube-transcript-api, edge-tts
- **Frontend**: Vanilla JavaScript (ES6+), Tailwind CSS (Standalone build), Marked.js, DOMPurify
- **Packaging**: PyInstaller, Inno Setup 6 (Windows Setup Wizard)

---

## 📄 License

This project is licensed under the MIT License. Contributions and PRs from the open-source community are warmly welcome!
