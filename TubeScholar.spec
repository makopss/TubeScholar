# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# 번들링할 프론트엔드 정적 파일 및 아이콘
datas = [
    ('frontend', 'frontend'),
    ('app_icon.ico', '.'),
]
binaries = []
hiddenimports = [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'uvicorn.lifespan.off',
    'fastapi',
    'fastapi.staticfiles',
    'fastapi.responses',
    'starlette',
    'pydantic',
    'pydantic_core',
    'edge_tts',
    'groq',
    'google.genai',
    'google.auth',
    'youtube_transcript_api',
    'yt_dlp',
    'imageio_ffmpeg',
]

# imageio_ffmpeg, edge_tts, uvicorn, yt_dlp 데이터 및 서브모듈 수집
for pkg in ['imageio_ffmpeg', 'edge_tts', 'uvicorn', 'yt_dlp']:
    try:
        pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hiddenimports
    except Exception as e:
        print(f"Warning collecting {pkg}: {e}")

a = Analysis(
    ['run.py'],
    pathex=['backend'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'notebook', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TubeScholar',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 실행 로그 확인 및 안정적인 구동을 위해 콘솔 활성화
    icon='app_icon.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TubeScholar',
)
